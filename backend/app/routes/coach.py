"""
AI Coach routes – GPT-powered game review with quota enforcement.

Free users get 3 reviews/month. Pro users get unlimited.
The coach produces deterministic-style structured feedback (not vague chat).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import get_settings
from app.db.models import Game, GameAnalysis, MoveEvaluation, User
from app.db.session import get_db

router = APIRouter()

FREE_MONTHLY_LIMIT = 3


class CoachReviewRequest(BaseModel):
    game_id: int
    focus: Optional[str] = None  # e.g., "opening", "tactics", "endgame"


class CoachReviewResponse(BaseModel):
    game_id: int
    review: str
    sections: list[dict]
    reviews_used: int
    reviews_limit: Optional[int]


@router.post("/review", response_model=CoachReviewResponse)
async def get_coach_review(
    body: CoachReviewRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an AI Coach review for a specific analyzed game.
    Uses GPT-4o-mini for cost efficiency.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Coach is not configured (missing OpenAI API key)",
        )

    # ── Quota check ─────────────────────────────────────
    did_reset = _reset_coach_quota_if_new_month(user)
    if did_reset:
        db.add(user)
        await db.flush()

    is_pro = user.subscription_tier == "pro"
    if not is_pro and user.ai_coach_reviews_used >= FREE_MONTHLY_LIMIT:
        raise HTTPException(
            status_code=403,
            detail=f"Free plan limit reached ({FREE_MONTHLY_LIMIT} reviews/month). Upgrade to Pro for unlimited reviews.",
        )

    # ── Load game + analysis ────────────────────────────
    game_q = await db.execute(
        select(Game).where(Game.id == body.game_id, Game.user_id == user.id)
    )
    game = game_q.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    analysis_q = await db.execute(
        select(GameAnalysis).where(GameAnalysis.game_id == game.id)
    )
    analysis = analysis_q.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=400,
            detail="Game must be analyzed before requesting a coach review",
        )

    # Load move evaluations
    moves_q = await db.execute(
        select(MoveEvaluation)
        .where(MoveEvaluation.game_id == game.id)
        .order_by(MoveEvaluation.move_number, MoveEvaluation.color)
    )
    moves = moves_q.scalars().all()

    # ── Build the prompt ────────────────────────────────
    prompt = _build_review_prompt(game, analysis, moves, body.focus)

    # ── Call OpenAI ─────────────────────────────────────
    import httpx

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 1500,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="AI Coach service error")

    data = resp.json()
    review_text = data["choices"][0]["message"]["content"]

    # ── Update quota ────────────────────────────────────
    user.ai_coach_reviews_used += 1
    db.add(user)
    await db.commit()

    # ── Parse sections from the review ──────────────────
    sections = _parse_sections(review_text)

    return CoachReviewResponse(
        game_id=game.id,
        review=review_text,
        sections=sections,
        reviews_used=user.ai_coach_reviews_used,
        reviews_limit=None if is_pro else FREE_MONTHLY_LIMIT,
    )


@router.get("/quota")
async def get_quota(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Check how many AI Coach reviews the user has left."""
    if _reset_coach_quota_if_new_month(user):
        db.add(user)
        await db.commit()

    is_pro = user.subscription_tier == "pro"
    return {
        "reviews_used": user.ai_coach_reviews_used,
        "reviews_limit": None if is_pro else FREE_MONTHLY_LIMIT,
        "reviews_remaining": None if is_pro else max(0, FREE_MONTHLY_LIMIT - user.ai_coach_reviews_used),
        "is_pro": is_pro,
    }


def _month_context(dt: Optional[datetime] = None) -> str:
    now = dt or datetime.utcnow()
    return now.strftime("%Y-%m")


def _reset_coach_quota_if_new_month(user: User) -> bool:
    """Reset coach usage if stored reset month differs from current month."""
    now = datetime.utcnow()
    if not user.ai_coach_reviews_reset_at:
        user.ai_coach_reviews_reset_at = now
        user.ai_coach_reviews_used = 0
        return True

    if _month_context(user.ai_coach_reviews_reset_at) != _month_context(now):
        user.ai_coach_reviews_used = 0
        user.ai_coach_reviews_reset_at = now
        return True

    return False


# ═══════════════════════════════════════════════════════════
# Prompt engineering
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert chess coach reviewing a student's game.
Your review must be structured, actionable, and specific to the game data provided.

Format your review with exactly these sections:
## Summary
A 2-3 sentence overview of the game quality.

## Critical Moments
List the 2-3 most important moments (mistakes/blunders) with move numbers and what was missed.

## Phase Analysis
Brief assessment of opening, middlegame, and endgame play based on the CPL data.

## Actionable Advice
Exactly 3 specific, concrete things to practice based on the patterns you see.

Rules:
- Be specific (cite move numbers)
- Be encouraging but honest
- Never invent analysis — only reference the data provided
- Keep total response under 500 words
- Use plain language, not engine jargon"""


def _build_review_prompt(
    game: Game, analysis: GameAnalysis, moves: list, focus: Optional[str]
) -> str:
    """Build a structured prompt from game data."""

    # Gather critical moves
    critical = [m for m in moves if m.move_quality in ("Blunder", "Mistake")]
    critical_str = "\n".join(
        f"  Move {m.move_number} ({m.color}): {m.san} — {m.move_quality} "
        f"(lost {m.cp_loss} cp, phase: {m.phase})"
        for m in critical[:10]
    )

    focus_line = f"\nFocus area requested by student: {focus}" if focus else ""

    return f"""Game data for review:
- Opening: {game.opening_name or 'Unknown'} ({game.eco_code or '?'})
- Color: {game.color}
- Result: {game.result}
- Time control: {game.time_control or 'Unknown'}
- Player rating: {game.player_elo or '?'} vs Opponent: {game.opponent_elo or '?'}
- Total moves: {game.moves_count or len(moves)}

Analysis summary:
- Overall CPL: {analysis.overall_cpl}
- Opening CPL: {analysis.phase_opening_cpl or 'N/A'}
- Middlegame CPL: {analysis.phase_middlegame_cpl or 'N/A'}
- Endgame CPL: {analysis.phase_endgame_cpl or 'N/A'}
- Blunders: {analysis.blunders_count}, Mistakes: {analysis.mistakes_count}
- Inaccuracies: {analysis.inaccuracies_count}, Best moves: {analysis.best_moves_count}

Critical moves:
{critical_str or '  No major mistakes found.'}
{focus_line}

Please provide your structured coaching review."""


def _parse_sections(text: str) -> list[dict]:
    """Parse the GPT response into structured sections."""
    sections = []
    current_title = None
    current_content: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_title:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_content).strip(),
                })
            current_title = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)

    if current_title:
        sections.append({
            "title": current_title,
            "content": "\n".join(current_content).strip(),
        })

    return sections
