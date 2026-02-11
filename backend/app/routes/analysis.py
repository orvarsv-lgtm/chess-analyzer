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
from app.db.session import get_db

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
