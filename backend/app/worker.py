"""
Background worker – arq task definitions.

Run with: arq app.worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AnalysisJob, Game, GameAnalysis, MoveEvaluation
from app.db.session import async_session


async def run_analysis(ctx: dict, job_id: int, game_ids: List[int], depth: int = 12):
    """
    Background task: Run Stockfish analysis on a list of games.
    Updates the AnalysisJob row with progress.
    """
    import chess
    import chess.engine
    import chess.pgn
    from io import StringIO

    settings = get_settings()

    async with async_session() as db:
        # Mark job as processing
        result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.add(job)
        await db.commit()

        try:
            # Open Stockfish engine
            transport, engine = await chess.engine.popen_uci(settings.stockfish_path)

            for game_id in game_ids:
                game_result = await db.execute(select(Game).where(Game.id == game_id))
                game = game_result.scalar_one_or_none()
                if not game:
                    continue

                # Parse PGN
                pgn_game = chess.pgn.read_game(StringIO(game.moves_pgn))
                if not pgn_game:
                    continue

                board = pgn_game.board()
                move_evals = []
                total_cp_loss = 0
                phase_losses = {"opening": [], "middlegame": [], "endgame": []}
                blunders = 0
                mistakes = 0
                inaccuracies = 0
                best_moves = 0
                move_num = 0

                prev_score_cp = 0

                for move in pgn_game.mainline_moves():
                    move_num += 1
                    color = "white" if board.turn == chess.WHITE else "black"
                    san = board.san(move)

                    board.push(move)

                    # Adaptive depth: deeper for positions with big eval swings
                    current_depth = depth

                    info = await engine.analyse(board, chess.engine.Limit(depth=current_depth))

                    # Extract score
                    score = info.get("score")
                    score_cp = 0
                    is_mate = False
                    if score:
                        pov = score.pov(chess.WHITE)
                        if pov.is_mate():
                            is_mate = True
                            mate_val = pov.mate()
                            score_cp = 10000 if (mate_val and mate_val > 0) else -10000
                        else:
                            score_cp = pov.score() or 0

                    # CP loss (from the player's perspective)
                    if color == "white":
                        cp_loss = max(0, prev_score_cp - score_cp)
                    else:
                        cp_loss = max(0, score_cp - prev_score_cp)

                    # Move quality classification
                    if cp_loss == 0:
                        quality = "Best"
                        best_moves += 1
                    elif cp_loss <= 10:
                        quality = "Excellent"
                    elif cp_loss <= 25:
                        quality = "Good"
                    elif cp_loss <= 100:
                        quality = "Inaccuracy"
                        inaccuracies += 1
                    elif cp_loss <= 300:
                        quality = "Mistake"
                        mistakes += 1
                    else:
                        quality = "Blunder"
                        blunders += 1

                    # Phase classification (simplified)
                    total_material = _count_material(board)
                    if move_num <= 10:
                        phase = "opening"
                    elif total_material <= 13:
                        phase = "endgame"
                    else:
                        phase = "middlegame"

                    phase_losses[phase].append(cp_loss)
                    total_cp_loss += cp_loss

                    move_evals.append(MoveEvaluation(
                        game_id=game_id,
                        move_number=move_num,
                        color=color,
                        san=san,
                        cp_loss=cp_loss,
                        phase=phase,
                        move_quality=quality,
                        eval_before=prev_score_cp,
                        eval_after=score_cp,
                        is_mate_before=False,
                        is_mate_after=is_mate,
                    ))

                    prev_score_cp = score_cp

                # Save analysis
                overall_cpl = total_cp_loss / move_num if move_num > 0 else 0

                analysis = GameAnalysis(
                    game_id=game_id,
                    overall_cpl=round(overall_cpl, 2),
                    phase_opening_cpl=_avg(phase_losses["opening"]),
                    phase_middlegame_cpl=_avg(phase_losses["middlegame"]),
                    phase_endgame_cpl=_avg(phase_losses["endgame"]),
                    blunders_count=blunders,
                    mistakes_count=mistakes,
                    inaccuracies_count=inaccuracies,
                    best_moves_count=best_moves,
                    analysis_depth=depth,
                )

                db.add(analysis)
                for me in move_evals:
                    db.add(me)

                # Update job progress
                job.games_completed += 1
                db.add(job)
                await db.commit()

            await engine.quit()

            # Mark job complete
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.add(job)
            await db.commit()

        except Exception as e:
            job.status = "failed"
            job.error = str(e)[:500]
            job.completed_at = datetime.utcnow()
            db.add(job)
            await db.commit()
            raise


def _count_material(board) -> int:
    """Count non-pawn material value (for phase detection)."""
    import chess
    values = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    total = 0
    for piece_type, value in values.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total += len(board.pieces(piece_type, chess.BLACK)) * value
    return total


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)


class WorkerSettings:
    """arq worker settings."""
    functions = [run_analysis]
    redis_settings = None  # Set at runtime from config

    @staticmethod
    def on_startup(ctx):
        from app.config import get_settings
        settings = get_settings()
        # arq will use redis_settings from here
        pass
