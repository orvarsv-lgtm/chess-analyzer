"""
AI Move Explanations – per-move natural language analysis.

Uses a hybrid approach:
1. Deterministic concept extraction from engine data + FEN analysis
2. GPT-4o-mini to produce a readable explanation

Free users get 10 explanations/month. Pro users get unlimited.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import chess
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import get_settings
from app.db.models import Streak, User
from app.db.session import get_db

router = APIRouter()

FREE_MONTHLY_LIMIT = 10  # free users get 10 move explanations / month
EXPLANATIONS_STREAK_TYPE = "ai_explanations"


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class ExplainMoveRequest(BaseModel):
    fen: str  # Position before the move
    san: str  # Move played in SAN notation
    best_move_san: Optional[str] = None  # Engine best move
    eval_before: Optional[int] = None  # Centipawn eval before
    eval_after: Optional[int] = None  # Centipawn eval after
    cp_loss: Optional[int] = None  # Centipawn loss
    phase: Optional[str] = None  # opening/middlegame/endgame
    move_quality: Optional[str] = None  # Best/Good/Inaccuracy/Mistake/Blunder
    move_number: Optional[int] = None
    color: Optional[str] = None  # white/black
    game_id: Optional[int] = None  # Link to stored game (for context)


class ExplainMoveResponse(BaseModel):
    explanation: str
    concepts: list[str]
    severity: str  # good/neutral/warning/critical
    alternative: Optional[str]  # Why the best move was better
    explanations_used: int
    explanations_limit: Optional[int]


class ExplanationQuota(BaseModel):
    used: int
    limit: Optional[int]
    remaining: Optional[int]
    is_pro: bool


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.post("/explain-move", response_model=ExplainMoveResponse)
async def explain_move(
    body: ExplainMoveRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a natural language explanation for a specific chess move.
    Uses deterministic concept extraction + GPT-4o-mini.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI explanations not configured (missing OpenAI API key)",
        )

    # ── Quota check ─────────────────────────────────────
    is_pro = user.subscription_tier == "pro"
    usage_row, used_count = await _get_monthly_explanations_usage(db, user.id)
    if not is_pro and used_count >= FREE_MONTHLY_LIMIT:
        raise HTTPException(
            status_code=403,
            detail=f"Free plan limit reached ({FREE_MONTHLY_LIMIT} explanations/month). Upgrade to Pro for unlimited explanations.",
        )

    # ── Concept extraction (deterministic) ──────────────
    concepts = _extract_concepts(body)
    severity = _determine_severity(body)

    # ── Build prompt ────────────────────────────────────
    prompt = _build_explanation_prompt(body, concepts)

    # ── Call OpenAI ─────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 400,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="AI explanation service unavailable")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="AI explanation service error")

    try:
        data = resp.json()
        explanation_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise HTTPException(status_code=502, detail="Unexpected AI response format")

    # Parse alternative suggestion from the response
    alternative = None
    if body.best_move_san and body.best_move_san != body.san and body.best_move_san != "?":
        alternative = _extract_alternative(explanation_text, body.best_move_san)

    # ── Persist per-user monthly usage ──────────────────
    if usage_row:
        usage_row.current_count += 1
    else:
        usage_row = Streak(
            user_id=user.id,
            streak_type=EXPLANATIONS_STREAK_TYPE,
            context=_month_context(),
            current_count=1,
            best_count=1,
            started_at=datetime.utcnow(),
        )
        db.add(usage_row)

    await db.commit()
    new_used_count = usage_row.current_count

    return ExplainMoveResponse(
        explanation=explanation_text,
        concepts=concepts,
        severity=severity,
        alternative=alternative,
        explanations_used=new_used_count,
        explanations_limit=None if is_pro else FREE_MONTHLY_LIMIT,
    )


@router.get("/quota")
async def get_explanation_quota(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Check AI explanation quota."""
    is_pro = user.subscription_tier == "pro"
    _, used_count = await _get_monthly_explanations_usage(db, user.id)
    return ExplanationQuota(
        used=used_count,
        limit=None if is_pro else FREE_MONTHLY_LIMIT,
        remaining=None if is_pro else max(0, FREE_MONTHLY_LIMIT - used_count),
        is_pro=is_pro,
    )


def _month_context(dt: Optional[datetime] = None) -> str:
    now = dt or datetime.utcnow()
    return now.strftime("%Y-%m")


async def _get_monthly_explanations_usage(
    db: AsyncSession, user_id: str
) -> tuple[Optional[Streak], int]:
    """Fetch explanation usage row for current month and return (row, used_count)."""
    month = _month_context()
    usage_q = await db.execute(
        select(Streak).where(
            Streak.user_id == user_id,
            Streak.streak_type == EXPLANATIONS_STREAK_TYPE,
            Streak.context == month,
        )
    )
    usage_row = usage_q.scalar_one_or_none()
    used_count = usage_row.current_count if usage_row else 0
    return usage_row, used_count


# ═══════════════════════════════════════════════════════════
# Deterministic concept extraction
# ═══════════════════════════════════════════════════════════


def _extract_concepts(body: ExplainMoveRequest) -> list[str]:
    """
    Extract chess concepts from the position and move data.
    Pure deterministic analysis — no AI needed.
    """
    concepts = []

    try:
        board = chess.Board(body.fen)
    except (ValueError, TypeError):
        return ["position analysis"]

    try:
        move = board.parse_san(body.san)
    except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
        return ["position analysis"]

    # ── Check for captures ──────────────────────────────
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured:
            piece_names = {
                chess.PAWN: "pawn",
                chess.KNIGHT: "knight",
                chess.BISHOP: "bishop",
                chess.ROOK: "rook",
                chess.QUEEN: "queen",
            }
            concepts.append(f"captures {piece_names.get(captured.piece_type, 'piece')}")

    # ── Check for checks ───────────────────────────────
    board_copy = board.copy()
    board_copy.push(move)
    if board_copy.is_check():
        concepts.append("check")
        if board_copy.is_checkmate():
            concepts.append("checkmate")

    # ── Castling ────────────────────────────────────────
    if board.is_castling(move):
        if board.is_kingside_castling(move):
            concepts.append("kingside castling")
        else:
            concepts.append("queenside castling")

    # ── Promotion ───────────────────────────────────────
    if move.promotion:
        promo_names = {
            chess.QUEEN: "queen",
            chess.ROOK: "rook",
            chess.BISHOP: "bishop",
            chess.KNIGHT: "knight",
        }
        concepts.append(f"promotion to {promo_names.get(move.promotion, 'piece')}")

    # ── En passant ──────────────────────────────────────
    if board.is_en_passant(move):
        concepts.append("en passant")

    # ── Piece development (opening) ─────────────────────
    if body.phase == "opening":
        piece = board.piece_at(move.from_square)
        if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            concepts.append("piece development")
        if piece and piece.piece_type == chess.PAWN:
            # Central pawn moves
            if chess.square_file(move.to_square) in (3, 4):  # d, e files
                concepts.append("center control")

    # ── Tactical patterns ───────────────────────────────
    if body.cp_loss is not None:
        if body.cp_loss == 0:
            concepts.append("engine-approved move")
        elif body.cp_loss >= 300:
            concepts.append("major blunder")
        elif body.cp_loss >= 100:
            concepts.append("significant mistake")

    # ── King safety (check for exposed king) ────────────
    if body.phase in ("middlegame", "opening"):
        king_sq = board.king(board.turn)
        if king_sq is not None:
            # Check if king is on initial rank
            rank = chess.square_rank(king_sq)
            expected_rank = 0 if board.turn == chess.WHITE else 7
            if rank != expected_rank and not board.has_castling_rights(board.turn):
                concepts.append("king safety")

    # ── Phase-specific concepts ─────────────────────────
    if body.phase == "endgame":
        # Count pieces
        piece_count = len(board.piece_map())
        if piece_count <= 6:
            concepts.append("endgame technique")
        concepts.append("endgame play")
    elif body.phase == "middlegame":
        concepts.append("middlegame strategy")
    elif body.phase == "opening":
        concepts.append("opening principles")

    return concepts if concepts else ["position analysis"]


def _determine_severity(body: ExplainMoveRequest) -> str:
    """Determine the severity level for the UI display."""
    if body.move_quality == "Blunder":
        return "critical"
    elif body.move_quality == "Mistake":
        return "warning"
    elif body.move_quality in ("Inaccuracy",):
        return "warning"
    elif body.move_quality in ("Best", "Excellent"):
        return "good"
    return "neutral"


# ═══════════════════════════════════════════════════════════
# Prompt engineering
# ═══════════════════════════════════════════════════════════

EXPLANATION_SYSTEM_PROMPT = """You are an expert chess instructor explaining a single move to a student.

Rules:
- Explain in 2-4 sentences maximum
- Use plain language accessible to intermediate players (1200-1800 rating)
- Reference the specific move and position
- If the move was bad, explain WHY it was bad and what was better
- If the move was good, explain what it achieves strategically or tactically
- Never use vague statements like "this was a mistake"
- Always explain the REASON (hanging piece, weakened squares, tempo loss, etc.)
- Be specific about squares, pieces, and threats
- Be encouraging but honest"""


def _build_explanation_prompt(
    body: ExplainMoveRequest, concepts: list[str]
) -> str:
    """Build the prompt for GPT move explanation."""

    # Try to describe the position
    pos_desc = ""
    try:
        board = chess.Board(body.fen)
        # Count material
        white_material = sum(
            len(board.pieces(pt, chess.WHITE)) * v
            for pt, v in [(chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                          (chess.ROOK, 5), (chess.QUEEN, 9)]
        )
        black_material = sum(
            len(board.pieces(pt, chess.BLACK)) * v
            for pt, v in [(chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                          (chess.ROOK, 5), (chess.QUEEN, 9)]
        )
        material_diff = white_material - black_material
        if material_diff > 0:
            pos_desc = f"White is up {material_diff} points of material. "
        elif material_diff < 0:
            pos_desc = f"Black is up {abs(material_diff)} points of material. "
        else:
            pos_desc = "Material is roughly equal. "
    except (ValueError, TypeError):
        pass

    eval_desc = ""
    if body.eval_before is not None:
        eval_pawns = body.eval_before / 100
        if abs(eval_pawns) < 0.3:
            eval_desc = "The position was roughly equal"
        elif eval_pawns > 0:
            eval_desc = f"White had an advantage of {eval_pawns:+.1f} pawns"
        else:
            eval_desc = f"Black had an advantage of {abs(eval_pawns):.1f} pawns"

    quality_desc = ""
    if body.move_quality and body.cp_loss is not None:
        if body.cp_loss > 0:
            quality_desc = f"This was classified as a {body.move_quality} (lost {body.cp_loss} centipawns)."
        else:
            quality_desc = f"This was classified as the {body.move_quality} move."

    best_move_desc = ""
    if body.best_move_san and body.best_move_san != body.san and body.best_move_san != "?":
        best_move_desc = f"The engine's recommended move was {body.best_move_san}."

    return f"""Position (FEN): {body.fen}
Move played: {body.san} (move {body.move_number or '?'}, {body.color or '?'} to move)
Phase: {body.phase or 'unknown'}

{pos_desc}{eval_desc}
{quality_desc}
{best_move_desc}

Detected concepts: {', '.join(concepts)}

Explain this move in 2-4 sentences."""


def _extract_alternative(explanation: str, best_move_san: str) -> Optional[str]:
    """Extract or generate a brief explanation of why the best move was better."""
    # Look for mention of the best move in the explanation
    if best_move_san.lower() in explanation.lower():
        # The LLM already explained the alternative
        return None
    return f"The engine preferred {best_move_san} in this position."
