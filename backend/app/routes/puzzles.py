"""
Puzzle routes – List puzzles, record attempts, spaced repetition queue.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import Game, GameAnalysis, MoveEvaluation, Puzzle, PuzzleAttempt, User
from app.db.session import get_db

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class PuzzleOut(BaseModel):
    id: int
    fen: str
    side_to_move: str
    best_move_san: str
    best_move_uci: Optional[str]
    eval_loss_cp: int
    phase: str
    puzzle_type: str
    explanation: Optional[str]
    solution_line: list[str] = []
    themes: list[str] = []

    class Config:
        from_attributes = True


class AttemptRequest(BaseModel):
    correct: bool
    time_taken: Optional[float] = None


class AttemptResponse(BaseModel):
    puzzle_id: int
    correct: bool
    streak: int
    next_review_at: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.get("", response_model=list[PuzzleOut])
async def list_puzzles(
    tactic: Optional[str] = None,
    phase: Optional[str] = None,
    puzzle_type: Optional[str] = None,
    game_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List puzzles generated from the user's games. Optionally filter by game_id."""
    # Exclude all puzzles the user has already attempted
    attempted_sq = (
        select(PuzzleAttempt.puzzle_id)
        .where(PuzzleAttempt.user_id == user.id)
        .distinct()
        .subquery()
    )
    query = select(Puzzle).where(
        Puzzle.source_user_id == user.id,
        Puzzle.id.notin_(select(attempted_sq)),
    )

    if game_id:
        query = query.where(Puzzle.source_game_id == game_id)

    if tactic:
        # Filter by tactic tag in JSONB themes array
        query = query.where(Puzzle.themes.contains([tactic]))
    if phase:
        query = query.where(Puzzle.phase == phase)
    if puzzle_type:
        query = query.where(Puzzle.puzzle_type == puzzle_type)

    query = query.order_by(Puzzle.created_at.desc()).limit(limit)
    result = await db.execute(query)
    puzzles = result.scalars().all()

    return [
        PuzzleOut(
            id=p.id,
            fen=p.fen,
            side_to_move=p.side_to_move,
            best_move_san=p.best_move_san,
            best_move_uci=p.best_move_uci,
            eval_loss_cp=p.eval_loss_cp,
            phase=p.phase,
            puzzle_type=p.puzzle_type,
            explanation=p.explanation,
            solution_line=p.solution_line or [],
            themes=p.themes or [],
        )
        for p in puzzles
    ]


@router.get("/global", response_model=list[PuzzleOut])
async def global_puzzles(
    tactic: Optional[str] = None,
    phase: Optional[str] = None,
    puzzle_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List puzzles from ALL users' games (community puzzles). Excludes already-attempted."""
    # Subquery: puzzle IDs the user has already attempted (any result)
    attempted_sq = (
        select(PuzzleAttempt.puzzle_id)
        .where(PuzzleAttempt.user_id == user.id)
        .distinct()
        .subquery()
    )

    query = select(Puzzle).where(Puzzle.id.notin_(select(attempted_sq)))

    if tactic:
        query = query.where(Puzzle.themes.contains([tactic]))
    if phase:
        query = query.where(Puzzle.phase == phase)
    if puzzle_type:
        query = query.where(Puzzle.puzzle_type == puzzle_type)

    # Random ordering for variety, dedup by puzzle_key
    query = query.group_by(Puzzle.id).order_by(func.random()).limit(limit)
    result = await db.execute(query)
    puzzles = result.scalars().all()

    return [
        PuzzleOut(
            id=p.id,
            fen=p.fen,
            side_to_move=p.side_to_move,
            best_move_san=p.best_move_san,
            best_move_uci=p.best_move_uci,
            eval_loss_cp=p.eval_loss_cp,
            phase=p.phase,
            puzzle_type=p.puzzle_type,
            explanation=p.explanation,
            solution_line=p.solution_line or [],
            themes=p.themes or [],
        )
        for p in puzzles
    ]


@router.get("/review-queue", response_model=list[PuzzleOut])
async def get_review_queue(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get puzzles due for spaced-repetition review."""
    from datetime import datetime

    # Subquery: latest attempt per puzzle for this user
    latest_attempt = (
        select(
            PuzzleAttempt.puzzle_id,
            func.max(PuzzleAttempt.attempted_at).label("last_attempt"),
        )
        .where(PuzzleAttempt.user_id == user.id)
        .group_by(PuzzleAttempt.puzzle_id)
        .subquery()
    )

    query = (
        select(Puzzle)
        .join(PuzzleAttempt, PuzzleAttempt.puzzle_id == Puzzle.id)
        .where(
            PuzzleAttempt.user_id == user.id,
            PuzzleAttempt.next_review_at <= datetime.utcnow(),
        )
        .order_by(PuzzleAttempt.next_review_at.asc())
        .limit(limit)
    )

    result = await db.execute(query)
    puzzles = result.scalars().unique().all()

    return [
        PuzzleOut(
            id=p.id,
            fen=p.fen,
            side_to_move=p.side_to_move,
            best_move_san=p.best_move_san,
            best_move_uci=p.best_move_uci,
            eval_loss_cp=p.eval_loss_cp,
            phase=p.phase,
            puzzle_type=p.puzzle_type,
            explanation=p.explanation,
            solution_line=p.solution_line or [],
            themes=p.themes or [],
        )
        for p in puzzles
    ]


@router.post("/{puzzle_id}/attempt", response_model=AttemptResponse)
async def record_attempt(
    puzzle_id: int,
    body: AttemptRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a puzzle attempt and update spaced repetition schedule."""
    # Verify puzzle exists
    result = await db.execute(select(Puzzle).where(Puzzle.id == puzzle_id))
    puzzle = result.scalar_one_or_none()
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    # Get previous attempt for SM-2
    prev_result = await db.execute(
        select(PuzzleAttempt)
        .where(PuzzleAttempt.puzzle_id == puzzle_id, PuzzleAttempt.user_id == user.id)
        .order_by(PuzzleAttempt.attempted_at.desc())
        .limit(1)
    )
    prev = prev_result.scalar_one_or_none()

    rep_num = (prev.repetition_number + 1) if prev else 0
    ef = prev.easiness_factor if prev else 2.5

    if body.correct:
        quality = 4
    else:
        quality = 0
        rep_num = 0

    # SM-2 easiness factor update
    ef = max(1.3, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

    # Interval calculation
    if rep_num == 0:
        interval_days = 1
    elif rep_num == 1:
        interval_days = 6
    else:
        interval_days = int(6 * (ef ** (rep_num - 1)))

    from datetime import datetime, timedelta

    next_review = datetime.utcnow() + timedelta(days=interval_days)

    attempt = PuzzleAttempt(
        puzzle_id=puzzle_id,
        user_id=user.id,
        correct=body.correct,
        time_taken=body.time_taken,
        next_review_at=next_review,
        repetition_number=rep_num,
        easiness_factor=ef,
    )
    db.add(attempt)
    await db.commit()

    # Count current streak
    streak_result = await db.execute(
        select(PuzzleAttempt)
        .where(PuzzleAttempt.user_id == user.id)
        .order_by(PuzzleAttempt.attempted_at.desc())
        .limit(50)
    )
    recent = streak_result.scalars().all()
    streak = 0
    for a in recent:
        if a.correct:
            streak += 1
        else:
            break

    return AttemptResponse(
        puzzle_id=puzzle_id,
        correct=body.correct,
        streak=streak,
        next_review_at=next_review.isoformat(),
    )


@router.get("/daily-warmup")
async def get_daily_warmup(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Daily Warmup: 5 puzzle mix — 2 spaced-repetition review, 2 from weak areas, 1 random.
    Returns warmup status + puzzle list.
    """
    from datetime import datetime, timedelta, date

    today = date.today()
    already_done = (
        user.daily_warmup_completed_at is not None
        and user.daily_warmup_completed_at.date() == today
    )

    puzzles_out: list[dict] = []

    def puzzle_dict(p: Puzzle, source: str) -> dict:
        return {
            "id": p.id,
            "fen": p.fen,
            "side_to_move": p.side_to_move,
            "best_move_san": p.best_move_san,
            "best_move_uci": p.best_move_uci,
            "eval_loss_cp": p.eval_loss_cp,
            "phase": p.phase,
            "puzzle_type": p.puzzle_type,
            "themes": p.themes or [],
            "source": source,
        }

    seen_ids: set[int] = set()

    # ── 1. Two spaced-repetition review puzzles ──
    review_q = (
        select(Puzzle)
        .join(PuzzleAttempt, PuzzleAttempt.puzzle_id == Puzzle.id)
        .where(
            PuzzleAttempt.user_id == user.id,
            PuzzleAttempt.next_review_at <= datetime.utcnow(),
        )
        .order_by(PuzzleAttempt.next_review_at.asc())
        .limit(2)
    )
    review_res = await db.execute(review_q)
    for p in review_res.scalars().unique().all():
        if p.id not in seen_ids:
            puzzles_out.append(puzzle_dict(p, "review"))
            seen_ids.add(p.id)

    # ── 2. Two weak-area puzzles (phases with highest avg CPL) ──
    # Find weakest phase
    phase_stats_q = (
        select(
            func.avg(GameAnalysis.phase_opening_cpl).label("opening"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    phase_row = (await db.execute(phase_stats_q)).one_or_none()
    weak_phases: list[str] = []
    if phase_row:
        phase_map = {
            "opening": phase_row.opening or 0,
            "middlegame": phase_row.middlegame or 0,
            "endgame": phase_row.endgame or 0,
        }
        weak_phases = sorted(phase_map, key=phase_map.get, reverse=True)[:2]

    if weak_phases:
        # Get puzzles the user hasn't attempted from their weak phases
        attempted_sq = (
            select(PuzzleAttempt.puzzle_id)
            .where(PuzzleAttempt.user_id == user.id)
            .distinct()
            .subquery()
        )
        weak_q = (
            select(Puzzle)
            .where(
                Puzzle.phase.in_(weak_phases),
                Puzzle.id.notin_(select(attempted_sq)),
                Puzzle.id.notin_(seen_ids) if seen_ids else True,
            )
            .order_by(func.random())
            .limit(2)
        )
        weak_res = await db.execute(weak_q)
        for p in weak_res.scalars().all():
            if p.id not in seen_ids:
                puzzles_out.append(puzzle_dict(p, "weakness"))
                seen_ids.add(p.id)

    # ── 3. Fill remaining slots with random unattempted puzzles ──
    remaining = 5 - len(puzzles_out)
    if remaining > 0:
        attempted_sq2 = (
            select(PuzzleAttempt.puzzle_id)
            .where(PuzzleAttempt.user_id == user.id)
            .distinct()
            .subquery()
        )
        random_q = (
            select(Puzzle)
            .where(
                Puzzle.id.notin_(select(attempted_sq2)),
                Puzzle.id.notin_(seen_ids) if seen_ids else True,
            )
            .order_by(func.random())
            .limit(remaining)
        )
        random_res = await db.execute(random_q)
        for p in random_res.scalars().all():
            if p.id not in seen_ids:
                puzzles_out.append(puzzle_dict(p, "random"))
                seen_ids.add(p.id)

    return {
        "completed_today": already_done,
        "total_puzzles": len(puzzles_out),
        "puzzles": puzzles_out,
    }


@router.get("/advantage-positions")
async def get_advantage_positions(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Advantage Capitalization: find positions from the user's games where
    they had a significant advantage (eval > +200 cp from their perspective)
    but ended up losing or drawing the game. These are "missed win" training positions.
    """

    # Find move evaluations from lost/drawn games where player had big advantage
    # Only include the player's own moves (not opponent's)
    # Require best_move_san so we have a real answer for the puzzle
    q = (
        select(MoveEvaluation, Game.color)
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result.in_(["loss", "draw"]),
            MoveEvaluation.move_quality.in_(["Blunder", "Mistake", "Inaccuracy"]),
            MoveEvaluation.best_move_san.isnot(None),
            MoveEvaluation.fen_before.isnot(None),
        )
        .order_by(MoveEvaluation.cp_loss.desc())
        .limit(limit * 5)  # fetch more to filter
    )
    result = await db.execute(q)
    rows = result.all()

    positions: list[dict] = []
    seen_games: set[int] = set()

    for m, game_color in rows:
        if m.game_id in seen_games:
            continue
        # Only include the player's own moves
        if m.color != game_color:
            continue
        # Check if position was winning for the player
        eb = m.eval_before or 0
        # Positive eval = good for white; if player is black, flip
        player_advantage = eb if game_color == "white" else -eb
        if player_advantage < 200:
            continue

        # Derive side_to_move from FEN (who moves in this position)
        fen_parts = (m.fen_before or "").split()
        fen_side = "white" if len(fen_parts) > 1 and fen_parts[1] == "w" else "black"

        seen_games.add(m.game_id)
        positions.append({
            "id": m.id,
            "game_id": m.game_id,
            "fen": m.fen_before,
            "side_to_move": fen_side,
            "best_move_san": m.best_move_san,
            "best_move_uci": m.best_move_uci,
            "played_move_san": m.san,
            "cp_loss": m.cp_loss,
            "eval_before": m.eval_before,
            "phase": m.phase,
            "move_number": m.move_number,
            "advantage_cp": player_advantage,
        })
        if len(positions) >= limit:
            break

    # ── Global fallback: if user has fewer than `limit` positions, fill from global pool ──
    remaining = limit - len(positions)
    if remaining > 0:
        seen_game_ids = seen_games
        global_q = (
            select(MoveEvaluation, Game.color)
            .join(Game, Game.id == MoveEvaluation.game_id)
            .where(
                Game.user_id != user.id,
                Game.result.in_(["loss", "draw"]),
                MoveEvaluation.move_quality.in_(["Blunder", "Mistake"]),
                MoveEvaluation.cp_loss >= 200,
                MoveEvaluation.fen_before.isnot(None),
                MoveEvaluation.best_move_san.isnot(None),
            )
            .order_by(func.random())
            .limit(remaining * 5)
        )
        global_res = await db.execute(global_q)
        global_rows = global_res.all()

        for m, game_color2 in global_rows:
            if m.game_id in seen_game_ids:
                continue
            # Only include the player's own moves
            if m.color != game_color2:
                continue
            eb2 = m.eval_before or 0
            adv = eb2 if game_color2 == "white" else -eb2
            if adv < 200:
                continue

            fen_parts = (m.fen_before or "").split()
            fen_side = "white" if len(fen_parts) > 1 and fen_parts[1] == "w" else "black"

            seen_game_ids.add(m.game_id)
            positions.append({
                "id": m.id,
                "game_id": m.game_id,
                "fen": m.fen_before,
                "side_to_move": fen_side,
                "best_move_san": m.best_move_san,
                "best_move_uci": m.best_move_uci,
                "played_move_san": m.san,
                "cp_loss": m.cp_loss,
                "eval_before": m.eval_before,
                "phase": m.phase,
                "move_number": m.move_number,
                "advantage_cp": adv,
            })
            if len(positions) >= limit:
                break

    return {"positions": positions, "total": len(positions)}


@router.post("/daily-warmup/complete")
async def complete_daily_warmup(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark today's daily warmup as complete."""
    from datetime import datetime

    user.daily_warmup_completed_at = datetime.utcnow()
    await db.commit()
    return {"status": "completed", "completed_at": user.daily_warmup_completed_at.isoformat()}


@router.get("/intuition-challenge")
async def get_intuition_challenge(
    count: int = Query(5, ge=1, le=20),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Intuition Trainer: return `count` challenges.
    Each challenge is 4 consecutive moves from a game, one of which is a blunder.
    The user must identify which move is the blunder.
    """
    # Find blunder moves — first from user's games, then globally if needed
    blunder_q = (
        select(MoveEvaluation)
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.fen_before.isnot(None),
        )
        .order_by(func.random())
        .limit(count * 2)  # fetch extra to handle failures
    )
    result = await db.execute(blunder_q)
    blunders = list(result.scalars().all())

    # If not enough user blunders, supplement from global pool
    if len(blunders) < count * 2:
        global_blunder_q = (
            select(MoveEvaluation)
            .join(Game, Game.id == MoveEvaluation.game_id)
            .where(
                Game.user_id != user.id,
                MoveEvaluation.move_quality == "Blunder",
                MoveEvaluation.fen_before.isnot(None),
            )
            .order_by(func.random())
            .limit((count * 2) - len(blunders))
        )
        global_res = await db.execute(global_blunder_q)
        blunders.extend(global_res.scalars().all())

    challenges: list[dict] = []
    seen_games: set[int] = set()

    for blunder in blunders:
        if len(challenges) >= count:
            break
        if blunder.game_id in seen_games:
            continue
        seen_games.add(blunder.game_id)

        bm_num = blunder.move_number
        # Get surrounding same-color moves (wider window since same-color moves
        # are every other half-move). We need 4 options total.
        window_start = max(1, bm_num - 8)
        window_end = bm_num + 8

        moves_q = (
            select(MoveEvaluation)
            .where(
                MoveEvaluation.game_id == blunder.game_id,
                MoveEvaluation.move_number >= window_start,
                MoveEvaluation.move_number <= window_end,
                MoveEvaluation.color == blunder.color,
                MoveEvaluation.fen_before.isnot(None),
            )
            .order_by(MoveEvaluation.move_number.asc())
        )
        moves_res = await db.execute(moves_q)
        window_moves = list(moves_res.scalars().all())

        if len(window_moves) < 4:
            continue

        # Build exactly 4 options: always include the blunder + 3 others
        blunder_in_window = [m for m in window_moves if m.move_number == bm_num]
        others = [m for m in window_moves if m.move_number != bm_num]

        if not blunder_in_window:
            continue

        # Pick 3 non-blunder moves closest to the blunder
        others.sort(key=lambda m: abs(m.move_number - bm_num))
        picked_others = others[:3]

        if len(picked_others) < 3:
            continue

        options = picked_others + blunder_in_window
        # Shuffle so blunder isn't always last
        import random
        random.shuffle(options)

        challenge = {
            "game_id": blunder.game_id,
            "blunder_move_number": bm_num,
            "color": blunder.color,
            "options": [
                {
                    "move_number": m.move_number,
                    "san": m.san,
                    "fen_before": m.fen_before,
                    "is_blunder": m.move_quality == "Blunder",
                    "cp_loss": m.cp_loss,
                    "phase": m.phase,
                }
                for m in options
            ],
        }
        challenges.append(challenge)

    return {"challenges": challenges, "total": len(challenges)}


@router.get("/history")
async def get_puzzle_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated puzzle attempt history with stats summary."""
    from sqlalchemy.orm import selectinload

    # Total attempts
    total_q = (
        select(func.count())
        .select_from(PuzzleAttempt)
        .where(PuzzleAttempt.user_id == user.id)
    )
    total = (await db.execute(total_q)).scalar() or 0

    # Overall stats
    stats_q = (
        select(
            func.count().label("total_attempts"),
            func.sum(func.cast(PuzzleAttempt.correct, Integer)).label("correct_count"),
            func.avg(PuzzleAttempt.time_taken).label("avg_time"),
        )
        .where(PuzzleAttempt.user_id == user.id)
    )
    stats = (await db.execute(stats_q)).one_or_none()
    total_attempts = stats.total_attempts if stats else 0
    correct_count = stats.correct_count if stats else 0
    avg_time = round(stats.avg_time, 1) if stats and stats.avg_time else None

    # Recent attempts with puzzle data
    attempts_q = (
        select(PuzzleAttempt)
        .options(selectinload(PuzzleAttempt.puzzle))
        .where(PuzzleAttempt.user_id == user.id)
        .order_by(PuzzleAttempt.attempted_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(attempts_q)
    attempts = result.scalars().all()

    # Best streak (longest consecutive correct)
    streak_q = (
        select(PuzzleAttempt.correct)
        .where(PuzzleAttempt.user_id == user.id)
        .order_by(PuzzleAttempt.attempted_at.desc())
        .limit(200)
    )
    streak_rows = (await db.execute(streak_q)).scalars().all()
    best_streak = 0
    current_streak = 0
    for c in streak_rows:
        if c:
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        else:
            current_streak = 0

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "stats": {
            "total_attempts": total_attempts,
            "correct_count": correct_count,
            "accuracy": round(correct_count / total_attempts * 100, 1) if total_attempts > 0 else 0,
            "avg_time": avg_time,
            "best_streak": best_streak,
        },
        "attempts": [
            {
                "id": a.id,
                "puzzle_id": a.puzzle_id,
                "correct": a.correct,
                "time_taken": a.time_taken,
                "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
                "puzzle": {
                    "fen": a.puzzle.fen,
                    "phase": a.puzzle.phase,
                    "puzzle_type": a.puzzle.puzzle_type,
                    "themes": a.puzzle.themes or [],
                } if a.puzzle else None,
            }
            for a in attempts
        ],
    }
