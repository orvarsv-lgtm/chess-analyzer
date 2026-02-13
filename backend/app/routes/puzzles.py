"""
Puzzle routes – List puzzles, record attempts, spaced repetition queue.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import Puzzle, PuzzleAttempt, User
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
    difficulty: str
    explanation: Optional[str]
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
    difficulty: Optional[str] = None,
    phase: Optional[str] = None,
    puzzle_type: Optional[str] = None,
    game_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List puzzles generated from the user's games. Optionally filter by game_id."""
    query = select(Puzzle).where(Puzzle.source_user_id == user.id)

    if game_id:
        query = query.where(Puzzle.source_game_id == game_id)

    if difficulty:
        query = query.where(Puzzle.difficulty == difficulty)
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
            difficulty=p.difficulty,
            explanation=p.explanation,
            themes=p.themes or [],
        )
        for p in puzzles
    ]


@router.get("/global", response_model=list[PuzzleOut])
async def global_puzzles(
    difficulty: Optional[str] = None,
    phase: Optional[str] = None,
    puzzle_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List puzzles from ALL users' games (community puzzles). Excludes already-solved."""
    # Subquery: puzzle IDs the user has already solved correctly
    solved_sq = (
        select(PuzzleAttempt.puzzle_id)
        .where(PuzzleAttempt.user_id == user.id, PuzzleAttempt.correct == True)
        .distinct()
        .subquery()
    )

    query = select(Puzzle).where(Puzzle.id.notin_(select(solved_sq)))

    if difficulty:
        query = query.where(Puzzle.difficulty == difficulty)
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
            difficulty=p.difficulty,
            explanation=p.explanation,
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
            difficulty=p.difficulty,
            explanation=p.explanation,
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
