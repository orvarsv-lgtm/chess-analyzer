"""
Analysis routes – Trigger background analysis, get results.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_user
from app.db.models import AnalysisJob, Game, GameAnalysis, MoveEvaluation, User
from app.db.session import get_db, async_session

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class AnalyzeRequest(BaseModel):
    game_ids: Optional[list[int]] = None  # None = analyze all unanalyzed games
    depth: int = 12


class JobStatusResponse(BaseModel):
    job_id: int
    status: str
    total_games: int
    games_completed: int
    error: Optional[str] = None


class MoveEvalOut(BaseModel):
    move_number: int
    color: str
    san: str
    cp_loss: int
    phase: Optional[str]
    move_quality: Optional[str]
    blunder_subtype: Optional[str]
    eval_before: Optional[int]
    eval_after: Optional[int]

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.post("/start", response_model=JobStatusResponse)
async def start_analysis(
    body: AnalyzeRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Queue a background analysis job.
    Returns a job ID to poll for status.
    """
    # Find games to analyze
    query = select(Game).where(Game.user_id == user.id)

    if body.game_ids:
        query = query.where(Game.id.in_(body.game_ids))

    # Only games without existing analysis
    query = query.outerjoin(GameAnalysis).where(GameAnalysis.id.is_(None))
    result = await db.execute(query)
    games = result.scalars().all()

    if not games:
        raise HTTPException(status_code=400, detail="No unanalyzed games found")

    # Create a job record
    job = AnalysisJob(
        user_id=user.id,
        job_type="full_analysis" if body.game_ids is None else "single_game",
        status="pending",
        total_games=len(games),
        games_completed=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue arq background task
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from app.config import get_settings

        settings = get_settings()
        if settings.redis_url:
            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await pool.enqueue_job(
                "run_analysis", job.id, [g.id for g in games], body.depth
            )
            await pool.close()
    except Exception:
        # If Redis/arq not available, mark the job for manual processing
        pass

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        total_games=job.total_games,
        games_completed=job.games_completed,
    )


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll analysis job status."""
    result = await db.execute(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        total_games=job.total_games,
        games_completed=job.games_completed,
        error=job.error,
    )


@router.post("/run")
async def run_analysis_sync(
    body: AnalyzeRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run Stockfish analysis synchronously via SSE stream.
    No Redis/arq required — analyses games directly and streams progress.
    """
    import json
    import chess
    import chess.engine
    import chess.pgn as cpgn
    from io import StringIO
    from fastapi.responses import StreamingResponse
    from app.config import get_settings

    # Find games to analyze
    query = select(Game).where(Game.user_id == user.id)

    if body.game_ids:
        query = query.where(Game.id.in_(body.game_ids))

    # Only games without existing analysis
    query = query.outerjoin(GameAnalysis).where(GameAnalysis.id.is_(None))
    result = await db.execute(query)
    games_to_analyze = result.scalars().all()

    if not games_to_analyze:
        raise HTTPException(status_code=400, detail="No unanalyzed games found")

    # Eagerly read game data before closing session context
    game_data = []
    for g in games_to_analyze:
        game_data.append({
            "id": g.id,
            "moves_pgn": g.moves_pgn,
            "color": g.color,
            "white_player": g.white_player,
            "black_player": g.black_player,
            "opening_name": g.opening_name,
        })

    total = len(game_data)

    async def analysis_stream():
        settings = get_settings()
        depth = min(body.depth, 16)

        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        try:
            transport, engine = await chess.engine.popen_uci(settings.stockfish_path)

            for idx, gd in enumerate(game_data):
                game_id = gd["id"]

                try:
                    pgn_game = cpgn.read_game(StringIO(gd["moves_pgn"]))
                    if not pgn_game:
                        continue

                    board = pgn_game.board()
                    move_evals = []
                    player_cp_losses = []  # only player's moves
                    phase_losses = {"opening": [], "middlegame": [], "endgame": []}
                    blunders = 0
                    mistakes = 0
                    inaccuracies = 0
                    best_moves_count = 0
                    move_num = 0
                    prev_score_cp = 0
                    prev_is_mate = False
                    castled_white = False
                    castled_black = False

                    player_color = gd["color"]  # "white" or "black"

                    for move in pgn_game.mainline_moves():
                        move_num += 1
                        mv_color = "white" if board.turn == chess.WHITE else "black"
                        san = board.san(move)
                        is_player_move = (mv_color == player_color)

                        # Track piece moved BEFORE push
                        from_sq = move.from_square
                        piece_obj = board.piece_at(from_sq)
                        piece_symbol = piece_obj.symbol().upper() if piece_obj else None

                        # Track castling
                        if board.is_castling(move):
                            if mv_color == "white":
                                castled_white = True
                            else:
                                castled_black = True

                        board.push(move)

                        info = await engine.analyse(board, chess.engine.Limit(depth=depth))

                        score = info.get("score")
                        score_cp = 0
                        is_mate = False
                        if score:
                            pov = score.pov(chess.WHITE)
                            if pov.is_mate():
                                is_mate = True
                                mate_val = pov.mate()
                                # Cap mate scores at ±1500 to avoid wild CPL spikes
                                score_cp = 1500 if (mate_val and mate_val > 0) else -1500
                            else:
                                score_cp = max(-1500, min(1500, pov.score() or 0))

                        # Skip cp_loss for transitions involving mates on both sides
                        if prev_is_mate and is_mate:
                            cp_loss = 0
                        elif mv_color == "white":
                            cp_loss = max(0, prev_score_cp - score_cp)
                        else:
                            cp_loss = max(0, score_cp - prev_score_cp)

                        # Cap individual cp_loss to prevent outliers
                        cp_loss = min(cp_loss, 800)

                        if cp_loss == 0:
                            quality = "Best"
                        elif cp_loss <= 10:
                            quality = "Excellent"
                        elif cp_loss <= 25:
                            quality = "Good"
                        elif cp_loss <= 100:
                            quality = "Inaccuracy"
                        elif cp_loss <= 300:
                            quality = "Mistake"
                        else:
                            quality = "Blunder"

                        # Only count player's move quality stats
                        if is_player_move:
                            if quality == "Best":
                                best_moves_count += 1
                            elif quality == "Inaccuracy":
                                inaccuracies += 1
                            elif quality == "Mistake":
                                mistakes += 1
                            elif quality == "Blunder":
                                blunders += 1
                            player_cp_losses.append(cp_loss)

                        # Multi-factor phase detection
                        phase = _detect_phase(board, move_num, castled_white, castled_black)

                        # Only accumulate player's phase losses
                        if is_player_move:
                            phase_losses[phase].append(cp_loss)

                        move_evals.append({
                            "game_id": game_id,
                            "move_number": move_num,
                            "color": mv_color,
                            "san": san,
                            "piece": piece_symbol,
                            "cp_loss": cp_loss,
                            "phase": phase,
                            "move_quality": quality,
                            "eval_before": prev_score_cp,
                            "eval_after": score_cp,
                            "is_mate_before": prev_is_mate,
                            "is_mate_after": is_mate,
                        })

                        prev_score_cp = score_cp
                        prev_is_mate = is_mate

                    # CPL = average of player's moves only
                    overall_cpl = round(sum(player_cp_losses) / len(player_cp_losses), 2) if player_cp_losses else 0

                    # Save to DB
                    async with async_session() as save_db:
                        analysis_row = GameAnalysis(
                            game_id=game_id,
                            overall_cpl=overall_cpl,
                            phase_opening_cpl=_avg(phase_losses["opening"]),
                            phase_middlegame_cpl=_avg(phase_losses["middlegame"]),
                            phase_endgame_cpl=_avg(phase_losses["endgame"]),
                            blunders_count=blunders,
                            mistakes_count=mistakes,
                            inaccuracies_count=inaccuracies,
                            best_moves_count=best_moves_count,
                            analysis_depth=depth,
                        )
                        save_db.add(analysis_row)
                        for me in move_evals:
                            save_db.add(MoveEvaluation(**me))
                        await save_db.commit()

                    # Progress event
                    wp = gd.get("white_player", "?")
                    bp = gd.get("black_player", "?")
                    yield f"data: {json.dumps({'type': 'progress', 'completed': idx + 1, 'total': total, 'game_id': game_id, 'game_label': f'{wp} vs {bp}', 'overall_cpl': overall_cpl, 'blunders': blunders, 'mistakes': mistakes})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'game_error', 'game_id': game_id, 'message': str(e)[:200]})}\n\n"
                    continue

            await engine.quit()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:300]})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'complete', 'analyzed': total})}\n\n"

    return StreamingResponse(
        analysis_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/game/{game_id}")
async def get_game_analysis(
    game_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full analysis for a single game: summary + per-move evaluations."""
    # Verify game ownership
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id, Game.user_id == user.id)
        .options(selectinload(Game.analysis), selectinload(Game.move_evals))
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if not game.analysis:
        raise HTTPException(status_code=404, detail="Game has not been analyzed yet")

    a = game.analysis
    moves = [
        MoveEvalOut(
            move_number=m.move_number,
            color=m.color,
            san=m.san,
            cp_loss=m.cp_loss,
            phase=m.phase,
            move_quality=m.move_quality,
            blunder_subtype=m.blunder_subtype,
            eval_before=m.eval_before,
            eval_after=m.eval_after,
        )
        for m in sorted(game.move_evals, key=lambda x: x.move_number)
    ]

    return {
        "game_id": game.id,
        "summary": {
            "overall_cpl": a.overall_cpl,
            "phase_opening_cpl": a.phase_opening_cpl,
            "phase_middlegame_cpl": a.phase_middlegame_cpl,
            "phase_endgame_cpl": a.phase_endgame_cpl,
            "blunders": a.blunders_count,
            "mistakes": a.mistakes_count,
            "inaccuracies": a.inaccuracies_count,
            "best_moves": a.best_moves_count,
            "depth": a.analysis_depth,
            "analyzed_at": a.analyzed_at.isoformat() if a.analyzed_at else None,
        },
        "moves": moves,
    }


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _count_material(board) -> int:
    """Count non-pawn material value (for phase detection)."""
    import chess as _chess
    values = {_chess.KNIGHT: 3, _chess.BISHOP: 3, _chess.ROOK: 5, _chess.QUEEN: 9}
    total = 0
    for piece_type, value in values.items():
        total += len(board.pieces(piece_type, _chess.WHITE)) * value
        total += len(board.pieces(piece_type, _chess.BLACK)) * value
    return total


def _count_developed_minors(board) -> int:
    """Count how many minor pieces (N/B) have left their starting squares."""
    import chess as _chess
    starting = {
        _chess.WHITE: {
            _chess.KNIGHT: [_chess.B1, _chess.G1],
            _chess.BISHOP: [_chess.C1, _chess.F1],
        },
        _chess.BLACK: {
            _chess.KNIGHT: [_chess.B8, _chess.G8],
            _chess.BISHOP: [_chess.C8, _chess.F8],
        },
    }
    developed = 0
    for color in [_chess.WHITE, _chess.BLACK]:
        for piece_type, home_squares in starting[color].items():
            for sq in home_squares:
                piece = board.piece_at(sq)
                if not piece or piece.piece_type != piece_type or piece.color != color:
                    developed += 1
    return developed


def _queens_on_board(board) -> bool:
    """Check if any queens remain on the board."""
    import chess as _chess
    return bool(board.pieces(_chess.QUEEN, _chess.WHITE) or board.pieces(_chess.QUEEN, _chess.BLACK))


def _detect_phase(board, move_num: int, castled_white: bool, castled_black: bool) -> str:
    """
    Multi-factor game phase detection:
    - Opening: move ≤ 15 AND high material AND few pieces developed
    - Endgame: low material OR no queens with reduced material OR only pawns + kings
    - Middlegame: everything else
    """
    material = _count_material(board)
    developed = _count_developed_minors(board)
    has_queens = _queens_on_board(board)

    # Endgame detection (takes priority — once you're in endgame, you stay there)
    if material == 0:
        return "endgame"
    if material <= 13:
        return "endgame"
    if not has_queens and material <= 20:
        return "endgame"

    # Opening detection
    if move_num <= 15 and material > 26 and developed < 6:
        return "opening"

    # Everything else is middlegame
    return "middlegame"


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)
