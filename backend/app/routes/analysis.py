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
from app.db.models import AnalysisJob, Game, GameAnalysis, MoveEvaluation, Puzzle, User
from app.db.session import get_db, async_session
from app.analysis_core import (
    win_probability,
    move_accuracy,
    compute_game_accuracy,
    classify_move,
    detect_phase,
    count_material,
    count_developed_minors,
    queens_on_board,
    generate_puzzle_data,
    compute_solution_line,
    avg,
    parse_clock_comment,
    classify_blunder_subtype,
)

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
    fen_before: Optional[str] = None
    best_move_san: Optional[str] = None
    best_move_uci: Optional[str] = None
    win_prob_before: Optional[float] = None
    win_prob_after: Optional[float] = None
    accuracy: Optional[float] = None

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
            "player_elo": g.player_elo,
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
                    player_cp_losses = []
                    player_accuracies = []  # per-move accuracy for player
                    phase_losses = {"opening": [], "middlegame": [], "endgame": []}
                    blunders = 0
                    mistakes = 0
                    inaccuracies = 0
                    best_moves_count = 0
                    great_moves_count = 0
                    brilliant_moves_count = 0
                    missed_wins_count = 0
                    move_num = 0
                    prev_score_cp = 0
                    prev_is_mate = False
                    prev_mate_in = None
                    castled_white = False
                    castled_black = False
                    puzzle_candidates = []

                    player_color = gd["color"]  # "white" or "black"

                    prev_clock = None  # track clock for move time deltas
                    move_times = []  # player move times in seconds
                    time_trouble_blunders_count = 0

                    for node in pgn_game.mainline():
                        move = node.move
                        move_num += 1
                        mv_color = "white" if board.turn == chess.WHITE else "black"
                        san = board.san(move)
                        is_player_move = (mv_color == player_color)
                        fen_before = board.fen()

                        # ── Clock parsing ──
                        clock_remaining = parse_clock_comment(node.comment)
                        move_time_sec = None
                        if clock_remaining is not None and prev_clock is not None:
                            # Move time = previous clock - current clock (same color alternates)
                            # We track per-color, so delta is prev_clock_this_color - current
                            # Since prev_clock is set per-color below, this works
                            pass  # computed below after color check

                        # Track per-color clocks
                        time_remaining_val = clock_remaining

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

                        # ── Pre-move engine query (for player moves) ──
                        best_move_san = None
                        best_move_uci = None
                        best_move_obj = None
                        best_second_gap_cp = None
                        is_only_legal = (board.legal_moves.count() == 1)

                        if is_player_move:
                            multi_info = await engine.analyse(
                                board, chess.engine.Limit(depth=depth),
                                multipv=2, info=chess.engine.INFO_ALL
                            )
                            pre_info = multi_info[0] if multi_info else {}
                            pv = pre_info.get("pv")
                            if pv and len(pv) > 0:
                                best_move_obj = pv[0]
                                best_move_uci = pv[0].uci()
                                best_move_san = board.san(pv[0])

                            # Compute gap between best and 2nd-best move
                            # for puzzle quality filtering
                            if len(multi_info) >= 2:
                                s1 = multi_info[0].get("score")
                                s2 = multi_info[1].get("score")
                                if s1 and s2:
                                    pov1 = s1.pov(board.turn)
                                    pov2 = s2.pov(board.turn)
                                    cp1 = 10000 if pov1.is_mate() and (pov1.mate() or 0) > 0 else (-10000 if pov1.is_mate() else (pov1.score() or 0))
                                    cp2 = 10000 if pov2.is_mate() and (pov2.mate() or 0) > 0 else (-10000 if pov2.is_mate() else (pov2.score() or 0))
                                    best_second_gap_cp = cp1 - cp2

                        board.push(move)

                        info = await engine.analyse(board, chess.engine.Limit(depth=depth))

                        score = info.get("score")
                        score_cp = 0
                        is_mate = False
                        mate_in = None
                        if score:
                            pov = score.pov(chess.WHITE)
                            if pov.is_mate():
                                is_mate = True
                                mate_in = pov.mate()
                                score_cp = 1500 if (mate_in and mate_in > 0) else -1500
                            else:
                                score_cp = max(-1500, min(1500, pov.score() or 0))

                        # CP loss calculation
                        if prev_is_mate and is_mate:
                            cp_loss = 0
                        elif mv_color == "white":
                            cp_loss = max(0, prev_score_cp - score_cp)
                        else:
                            cp_loss = max(0, score_cp - prev_score_cp)
                        cp_loss = min(cp_loss, 800)

                        # ── Win probability ──
                        wp_before = win_probability(prev_score_cp, prev_is_mate, prev_mate_in)
                        wp_after = win_probability(score_cp, is_mate, mate_in)

                        # ── Per-move accuracy ──
                        mv_accuracy = move_accuracy(wp_before, wp_after, mv_color)

                        # ── Phase detection ──
                        phase = detect_phase(board, move_num, castled_white, castled_black)

                        # ── Move classification ──
                        # For opponent moves, use simple cp_loss classification
                        if is_player_move:
                            # Undo the push temporarily for classification context
                            board.pop()
                            quality = classify_move(
                                cp_loss=cp_loss,
                                win_prob_before=wp_before,
                                win_prob_after=wp_after,
                                color=mv_color,
                                board_before=board,
                                move=move,
                                best_move=best_move_obj,
                                is_only_legal=is_only_legal,
                                eval_before_cp=prev_score_cp,
                                eval_after_cp=score_cp,
                                is_mate_before=prev_is_mate,
                                is_mate_after=is_mate,
                                mate_before=prev_mate_in,
                                mate_after=mate_in,
                                player_elo=gd.get("player_elo"),
                            )
                            board.push(move)  # re-push
                        else:
                            # Simple classification for opponent moves
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
                        blunder_sub = None
                        if is_player_move:
                            player_accuracies.append(mv_accuracy)
                            player_cp_losses.append(cp_loss)

                            if quality == "Best":
                                best_moves_count += 1
                            elif quality == "Great":
                                great_moves_count += 1
                            elif quality == "Brilliant":
                                brilliant_moves_count += 1
                            elif quality == "Missed Win":
                                missed_wins_count += 1
                            elif quality == "Inaccuracy":
                                inaccuracies += 1
                            elif quality == "Mistake":
                                mistakes += 1
                            elif quality == "Blunder":
                                blunders += 1

                            phase_losses[phase].append(cp_loss)

                            # ── Blunder subtype classification ──
                            blunder_sub = None
                            if quality == "Blunder":
                                board.pop()  # undo for classification context
                                blunder_sub = classify_blunder_subtype(board, move, best_move_obj, phase)
                                board.push(move)  # re-push
                                # Track time-trouble blunders
                                if time_remaining_val is not None and time_remaining_val < 30:
                                    time_trouble_blunders_count += 1

                            # ── Track move time for player moves ──
                            if clock_remaining is not None and prev_clock is not None:
                                mt = prev_clock - clock_remaining
                                if mt > 0:
                                    move_times.append(mt)

                            if is_player_move and clock_remaining is not None:
                                prev_clock = clock_remaining

                            # Collect puzzle candidates
                            puzzle_data = generate_puzzle_data(
                                fen_before=fen_before,
                                san=san,
                                best_move_san=best_move_san,
                                best_move_uci=best_move_uci,
                                cp_loss=cp_loss,
                                phase=phase,
                                move_quality=quality,
                                move_number=move_num,
                                best_second_gap_cp=best_second_gap_cp,
                                eval_before_cp=prev_score_cp,
                            )
                            if puzzle_data:
                                # Compute multi-move solution line
                                sol_line = await compute_solution_line(
                                    fen_before, engine, depth=depth, max_moves=6
                                )
                                puzzle_data["solution_line"] = sol_line
                                puzzle_candidates.append(puzzle_data)

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
                            "fen_before": fen_before,
                            "best_move_san": best_move_san if is_player_move else None,
                            "best_move_uci": best_move_uci if is_player_move else None,
                            "win_prob_before": round(wp_before, 4),
                            "win_prob_after": round(wp_after, 4),
                            "accuracy": round(mv_accuracy, 1),
                            "is_mate_before": prev_is_mate,
                            "is_mate_after": is_mate,
                            "time_remaining": time_remaining_val,
                            "blunder_subtype": blunder_sub if is_player_move else None,
                        })

                        prev_score_cp = score_cp
                        prev_is_mate = is_mate
                        prev_mate_in = mate_in

                    # CPL = average of player's moves only
                    overall_cpl = round(sum(player_cp_losses) / len(player_cp_losses), 2) if player_cp_losses else 0
                    game_acc = compute_game_accuracy(player_accuracies)

                    # Save to DB
                    async with async_session() as save_db:
                        analysis_row = GameAnalysis(
                            game_id=game_id,
                            overall_cpl=overall_cpl,
                            phase_opening_cpl=avg(phase_losses["opening"]),
                            phase_middlegame_cpl=avg(phase_losses["middlegame"]),
                            phase_endgame_cpl=avg(phase_losses["endgame"]),
                            blunders_count=blunders,
                            mistakes_count=mistakes,
                            inaccuracies_count=inaccuracies,
                            best_moves_count=best_moves_count,
                            great_moves_count=great_moves_count,
                            brilliant_moves_count=brilliant_moves_count,
                            missed_wins_count=missed_wins_count,
                            accuracy=game_acc,
                            analysis_depth=depth,
                            average_move_time=round(sum(move_times) / len(move_times), 1) if move_times else None,
                            time_trouble_blunders=time_trouble_blunders_count,
                        )
                        save_db.add(analysis_row)
                        for me in move_evals:
                            save_db.add(MoveEvaluation(**me))

                        # ── Generate puzzles ──
                        for pd in puzzle_candidates:
                            pd["source_game_id"] = game_id
                            pd["source_user_id"] = user.id
                            # Skip duplicates
                            existing = await save_db.execute(
                                select(Puzzle).where(Puzzle.puzzle_key == pd["puzzle_key"])
                            )
                            if not existing.scalar_one_or_none():
                                save_db.add(Puzzle(**pd))

                        await save_db.commit()

                    # Progress event
                    wp = gd.get("white_player", "?")
                    bp = gd.get("black_player", "?")
                    yield f"data: {json.dumps({'type': 'progress', 'completed': idx + 1, 'total': total, 'game_id': game_id, 'game_label': f'{wp} vs {bp}', 'overall_cpl': overall_cpl, 'accuracy': game_acc, 'blunders': blunders, 'mistakes': mistakes})}\n\n"

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
            fen_before=m.fen_before,
            best_move_san=m.best_move_san,
            best_move_uci=m.best_move_uci,
            win_prob_before=m.win_prob_before,
            win_prob_after=m.win_prob_after,
            accuracy=m.accuracy,
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
            "great_moves": a.great_moves_count,
            "brilliant_moves": a.brilliant_moves_count,
            "missed_wins": a.missed_wins_count,
            "accuracy": a.accuracy,
            "depth": a.analysis_depth,
            "analyzed_at": a.analyzed_at.isoformat() if a.analyzed_at else None,
        },
        "moves": moves,
    }


# ═══════════════════════════════════════════════════════════
# Helpers (phase detection + utility now in analysis_core.py)
# ═══════════════════════════════════════════════════════════
