"""
Cross-Game Pattern Detection – Identify recurring weaknesses across games.

Endpoints:
- GET /patterns/recurring — Find patterns that repeat across games
- GET /patterns/progress — Track improvement over time per pattern
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import Game, GameAnalysis, MoveEvaluation, OpeningRepertoire, User
from app.db.session import get_db

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class RecurringPattern(BaseModel):
    pattern_type: str  # "phase_weakness", "piece_weakness", "opening_issue", "blunder_type"
    description: str
    occurrences: int
    severity: str  # "high", "medium", "low"
    phase: Optional[str] = None
    avg_cp_loss: Optional[float] = None
    trend: Optional[str] = None  # "improving", "worsening", "stable"
    examples: list[dict] = []
    recommendation: str


class ProgressPoint(BaseModel):
    period: str  # e.g. "2024-01", "2024-02"
    games: int
    avg_cpl: Optional[float]
    blunder_rate: Optional[float]
    pattern_count: int


class PatternsResponse(BaseModel):
    patterns: list[RecurringPattern]
    total_games_analyzed: int
    analysis_period: str


class ProgressResponse(BaseModel):
    overall: list[ProgressPoint]
    by_phase: dict[str, list[ProgressPoint]]


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.get("/recurring", response_model=PatternsResponse)
async def get_recurring_patterns(
    limit: int = Query(default=10, ge=1, le=50),
    min_games: int = Query(default=3, description="Minimum games for pattern to qualify"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Identify recurring weakness patterns across the user's analyzed games.
    Uses aggregate queries on move evaluations to find systematic issues.
    """
    # Count total analyzed games
    game_count_q = await db.execute(
        select(func.count(Game.id))
        .join(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id)
    )
    total_games = game_count_q.scalar() or 0

    if total_games < min_games:
        return PatternsResponse(
            patterns=[],
            total_games_analyzed=total_games,
            analysis_period="insufficient data",
        )

    patterns: list[RecurringPattern] = []

    # ── Pattern 1: Phase weaknesses ─────────────────────
    # Find which phase has the highest CPL consistently
    phase_stats = await db.execute(
        select(
            MoveEvaluation.phase,
            func.avg(MoveEvaluation.cp_loss).label("avg_cpl"),
            func.count(MoveEvaluation.id).label("move_count"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.phase.isnot(None),
            MoveEvaluation.color == Game.color,  # only player's moves
        )
        .group_by(MoveEvaluation.phase)
    )
    phase_rows = phase_stats.fetchall()

    phase_data = {}
    for row in phase_rows:
        phase_name = row[0]
        avg_cpl = float(row[1]) if row[1] else 0
        move_count = row[2] or 0
        phase_data[phase_name] = {"avg_cpl": avg_cpl, "moves": move_count}

    # Determine weakest phase
    if phase_data:
        weakest_phase = max(phase_data.items(), key=lambda x: x[1]["avg_cpl"])
        if weakest_phase[1]["avg_cpl"] > 30 and weakest_phase[1]["moves"] >= 20:
            phase_name = weakest_phase[0]
            avg = round(weakest_phase[1]["avg_cpl"], 1)
            severity = "high" if avg > 60 else "medium" if avg > 40 else "low"

            recommendations = {
                "opening": "Study opening principles and your repertoire. Focus on development, center control, and king safety in the first 10 moves.",
                "middlegame": "Practice tactical puzzles and study positional concepts. Focus on piece coordination and finding plans.",
                "endgame": "Study basic endgame positions (K+P, rook endings). Practice converting advantages into wins.",
            }

            patterns.append(RecurringPattern(
                pattern_type="phase_weakness",
                description=f"Your {phase_name} play averages {avg} centipawn loss — this is your weakest phase.",
                occurrences=weakest_phase[1]["moves"],
                severity=severity,
                phase=phase_name,
                avg_cp_loss=avg,
                recommendation=recommendations.get(phase_name, "Focus on improving this phase of the game."),
            ))

    # ── Pattern 2: Blunder frequency by phase ───────────
    blunder_by_phase = await db.execute(
        select(
            MoveEvaluation.phase,
            func.count(MoveEvaluation.id).label("blunder_count"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.color == Game.color,  # only player's blunders
        )
        .group_by(MoveEvaluation.phase)
    )
    blunder_rows = blunder_by_phase.fetchall()

    for row in blunder_rows:
        phase_name = row[0] or "unknown"
        blunder_count = row[1] or 0
        total_phase_moves = phase_data.get(phase_name, {}).get("moves", 1)
        blunder_rate = round((blunder_count / max(total_phase_moves, 1)) * 100, 1)

        if blunder_count >= 3 and blunder_rate > 2:
            patterns.append(RecurringPattern(
                pattern_type="blunder_concentration",
                description=f"You blunder {blunder_rate}% of the time in the {phase_name} ({blunder_count} blunders total).",
                occurrences=blunder_count,
                severity="high" if blunder_rate > 5 else "medium",
                phase=phase_name,
                recommendation=f"Before making {phase_name} moves, take extra time to check for hanging pieces and tactical threats.",
            ))

    # ── Pattern 3: Opening-specific weaknesses ──────────
    opening_stats = await db.execute(
        select(OpeningRepertoire)
        .where(
            OpeningRepertoire.user_id == user.id,
            OpeningRepertoire.games_played >= min_games,
        )
        .order_by(OpeningRepertoire.average_cpl.desc().nullslast())
    )
    opening_rows = opening_stats.scalars().all()

    for op in opening_rows[:3]:
        if op.average_cpl and op.average_cpl > 40 and op.games_played >= min_games:
            wr = round((op.games_won / op.games_played) * 100, 1) if op.games_played > 0 else 0
            patterns.append(RecurringPattern(
                pattern_type="opening_issue",
                description=f"Struggling with {op.opening_name} as {op.color}: {op.average_cpl:.0f} avg CPL, {wr}% win rate over {op.games_played} games.",
                occurrences=op.games_played,
                severity="high" if op.average_cpl > 60 else "medium",
                avg_cp_loss=op.average_cpl,
                recommendation=f"Review your {op.opening_name} games, study the main ideas, or consider switching to a different opening as {op.color}.",
            ))

    # ── Pattern 4: Piece-specific mistakes ──────────────
    piece_mistakes = await db.execute(
        select(
            MoveEvaluation.piece,
            func.avg(MoveEvaluation.cp_loss).label("avg_cpl"),
            func.count(MoveEvaluation.id).label("move_count"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.piece.isnot(None),
            MoveEvaluation.cp_loss > 25,
            MoveEvaluation.color == Game.color,  # only player's moves
        )
        .group_by(MoveEvaluation.piece)
        .having(func.count(MoveEvaluation.id) >= 5)
        .order_by(desc("avg_cpl"))
    )
    piece_rows = piece_mistakes.fetchall()

    piece_names = {"P": "pawns", "N": "knights", "B": "bishops", "R": "rooks", "Q": "queen", "K": "king"}

    for row in piece_rows[:2]:
        piece = row[0]
        avg_cpl = float(row[1]) if row[1] else 0
        count = row[2] or 0
        piece_name = piece_names.get(piece, piece)

        if avg_cpl > 50:
            patterns.append(RecurringPattern(
                pattern_type="piece_weakness",
                description=f"Your {piece_name} moves lose an average of {avg_cpl:.0f} centipawns ({count} suboptimal moves).",
                occurrences=count,
                severity="medium",
                avg_cp_loss=avg_cpl,
                recommendation=f"Practice {piece_name}-specific tactics. Pay extra attention when moving your {piece_name}.",
            ))

    # ── Pattern 5: Consistency issues (high CPL variance) ─
    cpl_variance = await db.execute(
        select(
            func.stddev(GameAnalysis.overall_cpl).label("cpl_stddev"),
            func.avg(GameAnalysis.overall_cpl).label("cpl_avg"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    var_row = cpl_variance.fetchone()
    if var_row and var_row[0] and var_row[1]:
        stddev = float(var_row[0])
        avg = float(var_row[1])
        cv = (stddev / avg) * 100 if avg > 0 else 0

        if cv > 60 and total_games >= 5:
            patterns.append(RecurringPattern(
                pattern_type="consistency",
                description=f"Your play is inconsistent — CPL varies significantly between games (avg {avg:.0f} ± {stddev:.0f}).",
                occurrences=total_games,
                severity="medium",
                avg_cp_loss=avg,
                recommendation="Focus on consistent calculation habits. Try to maintain focus throughout each game. Consider playing at a consistent time format.",
            ))

    # Sort by severity then occurrence count
    severity_order = {"high": 0, "medium": 1, "low": 2}
    patterns.sort(key=lambda p: (severity_order.get(p.severity, 3), -p.occurrences))

    # Get date range
    date_range = await db.execute(
        select(
            func.min(Game.date),
            func.max(Game.date),
        ).where(Game.user_id == user.id)
    )
    date_row = date_range.fetchone()
    period = "all time"
    if date_row and date_row[0] and date_row[1]:
        start = date_row[0].strftime("%b %Y") if hasattr(date_row[0], 'strftime') else str(date_row[0])[:7]
        end = date_row[1].strftime("%b %Y") if hasattr(date_row[1], 'strftime') else str(date_row[1])[:7]
        period = f"{start} – {end}"

    return PatternsResponse(
        patterns=patterns[:limit],
        total_games_analyzed=total_games,
        analysis_period=period,
    )


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(
    months: int = Query(default=6, ge=1, le=24),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Track improvement over time — monthly CPL, blunder rate, and pattern counts.
    """
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=months * 30)

    # Monthly aggregates
    monthly = await db.execute(
        select(
            func.to_char(Game.date, 'YYYY-MM').label("period"),
            func.count(Game.id).label("games"),
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(
            Game.user_id == user.id,
            Game.date >= cutoff,
        )
        .group_by(func.to_char(Game.date, 'YYYY-MM'))
        .order_by(func.to_char(Game.date, 'YYYY-MM'))
    )
    monthly_rows = monthly.fetchall()

    overall = []
    for row in monthly_rows:
        period = row[0]
        games = row[1] or 0
        avg_cpl = round(float(row[2]), 1) if row[2] else None
        total_blunders = row[3] or 0
        total_moves = row[4] or 1
        player_moves = max(total_moves / 2, 1)  # moves_count includes both sides
        blunder_rate = round((total_blunders / player_moves) * 100, 2)

        overall.append(ProgressPoint(
            period=period,
            games=games,
            avg_cpl=avg_cpl,
            blunder_rate=blunder_rate,
            pattern_count=total_blunders,
        ))

    # Phase-specific progress
    by_phase: dict[str, list[ProgressPoint]] = {}
    for phase_name in ["opening", "middlegame", "endgame"]:
        phase_q = await db.execute(
            select(
                func.to_char(Game.date, 'YYYY-MM').label("period"),
                func.count(func.distinct(Game.id)).label("games"),
                func.avg(MoveEvaluation.cp_loss).label("avg_cpl"),
                func.count(
                    case(
                        (MoveEvaluation.move_quality == "Blunder", MoveEvaluation.id),
                    )
                ).label("blunder_count"),
            )
            .join(Game, Game.id == MoveEvaluation.game_id)
            .where(
                Game.user_id == user.id,
                MoveEvaluation.phase == phase_name,
                MoveEvaluation.color == Game.color,  # only player's moves
                Game.date >= cutoff,
            )
            .group_by(func.to_char(Game.date, 'YYYY-MM'))
            .order_by(func.to_char(Game.date, 'YYYY-MM'))
        )
        phase_rows = phase_q.fetchall()

        by_phase[phase_name] = [
            ProgressPoint(
                period=row[0],
                games=row[1] or 0,
                avg_cpl=round(float(row[2]), 1) if row[2] else None,
                blunder_rate=None,
                pattern_count=row[3] or 0,
            )
            for row in phase_rows
        ]

    return ProgressResponse(overall=overall, by_phase=by_phase)
