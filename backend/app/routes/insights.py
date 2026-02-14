"""
Insights routes – Aggregated performance data, coaching, trends.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import Game, GameAnalysis, MoveEvaluation, OpeningRepertoire, Puzzle, User
from app.db.session import get_db

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Time Control Classification Helper
# ═══════════════════════════════════════════════════════════

def _classify_time_control(tc: str | None) -> str | None:
    """Classify a time control string (e.g. '180+0', '600', '60+1') into a category."""
    if not tc:
        return None
    try:
        parts = tc.replace("+", " ").replace("|", " ").split()
        base = int(parts[0])
        inc = int(parts[1]) if len(parts) > 1 else 0
        total = base + inc * 40  # estimate total time
        if total < 120:
            return "bullet"
        elif total < 480:
            return "blitz"
        elif total < 1500:
            return "rapid"
        else:
            return "classical"
    except (ValueError, IndexError):
        return None


def _tc_filter_clause(tc_category: str | None):
    """Return a list of WHERE clauses for time control filtering.
    Returns empty list if no filter needed (None or 'all')."""
    if not tc_category or tc_category == "all":
        return []
    # We need to filter in Python since time_control is stored as raw string.
    # We'll return a list of possible patterns that match.
    return tc_category  # handled in queries via subquery


@router.get("/overview")
async def get_overview(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard overview – key numbers for the home page.
    Returns: total games, overall CPL, win rate, blunder rate, recent trend.
    """
    # Total games
    total_q = select(func.count()).select_from(Game).where(Game.user_id == user.id)
    total_games = (await db.execute(total_q)).scalar() or 0

    if total_games == 0:
        return {
            "total_games": 0,
            "overall_cpl": None,
            "win_rate": None,
            "blunder_rate": None,
            "recent_cpl": None,
            "trend": None,
            "current_elo": None,
            "elo_trend": None,
            "phase_accuracy": {"opening": None, "middlegame": None, "endgame": None},
            "puzzle_count": 0,
        }

    # Win rate
    wins_q = select(func.count()).select_from(Game).where(Game.user_id == user.id, Game.result == "win")
    wins = (await db.execute(wins_q)).scalar() or 0
    win_rate = round(wins / total_games * 100, 1)

    # Overall CPL (average across all analyzed games)
    cpl_q = (
        select(func.avg(GameAnalysis.overall_cpl))
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    overall_cpl = (await db.execute(cpl_q)).scalar()
    overall_cpl = round(overall_cpl, 1) if overall_cpl else None

    # Blunder rate per 100 player moves
    # blunders_count is player-only, so divide by player moves (total_moves / 2)
    blunder_q = (
        select(
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    row = (await db.execute(blunder_q)).one_or_none()
    blunder_rate = None
    if row and row.total_moves and row.total_moves > 0:
        player_moves = row.total_moves / 2  # moves_count includes both sides
        blunder_rate = round(row.total_blunders / player_moves * 100, 2)

    # Recent CPL (last 10 games) for trend
    recent_q = (
        select(GameAnalysis.overall_cpl)
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id, GameAnalysis.overall_cpl.isnot(None))
        .order_by(Game.date.desc())
        .limit(10)
    )
    recent_rows = (await db.execute(recent_q)).scalars().all()
    recent_cpl = round(sum(recent_rows) / len(recent_rows), 1) if recent_rows else None

    # Determine trend
    trend = None
    if overall_cpl and recent_cpl:
        diff = recent_cpl - overall_cpl
        if diff < -5:
            trend = "improving"
        elif diff > 5:
            trend = "declining"
        else:
            trend = "stable"

    # ── Current ELO (from most recent game with ELO data) ──
    elo_q = (
        select(Game.player_elo)
        .where(Game.user_id == user.id, Game.player_elo.isnot(None))
        .order_by(Game.date.desc())
        .limit(1)
    )
    current_elo = (await db.execute(elo_q)).scalar()

    # ELO trend: compare latest ELO with ELO from ~30 games ago
    elo_trend = None
    if current_elo:
        old_elo_q = (
            select(Game.player_elo)
            .where(Game.user_id == user.id, Game.player_elo.isnot(None))
            .order_by(Game.date.desc())
            .offset(30)
            .limit(1)
        )
        old_elo = (await db.execute(old_elo_q)).scalar()
        if old_elo:
            elo_trend = current_elo - old_elo

    # ── Phase accuracy (average CPL per phase across all analyzed games) ──
    phase_accuracy = {"opening": None, "middlegame": None, "endgame": None}
    for phase_key, col in [
        ("opening", GameAnalysis.phase_opening_cpl),
        ("middlegame", GameAnalysis.phase_middlegame_cpl),
        ("endgame", GameAnalysis.phase_endgame_cpl),
    ]:
        phase_q = (
            select(func.avg(col))
            .join(Game, Game.id == GameAnalysis.game_id)
            .where(Game.user_id == user.id, col.isnot(None))
        )
        val = (await db.execute(phase_q)).scalar()
        if val is not None:
            phase_accuracy[phase_key] = round(val, 1)

    # ── Puzzle count ──
    puzzle_count_q = (
        select(func.count())
        .select_from(Puzzle)
        .where(Puzzle.source_user_id == user.id)
    )
    puzzle_count = (await db.execute(puzzle_count_q)).scalar() or 0

    return {
        "total_games": total_games,
        "overall_cpl": overall_cpl,
        "win_rate": win_rate,
        "blunder_rate": blunder_rate,
        "recent_cpl": recent_cpl,
        "trend": trend,
        "current_elo": current_elo,
        "elo_trend": elo_trend,
        "phase_accuracy": phase_accuracy,
        "puzzle_count": puzzle_count,
    }


@router.get("/skill-profile")
async def get_skill_profile(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Skill radar data – 6 axes normalized to 0-100 for a radar chart.
    Axes: Opening, Middlegame, Endgame, Tactics, Composure, Consistency.
    Higher = better for all axes.
    """
    # Check minimum data
    analyzed_q = (
        select(func.count())
        .select_from(GameAnalysis)
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    analyzed_count = (await db.execute(analyzed_q)).scalar() or 0
    if analyzed_count < 3:
        return {"has_data": False, "message": "Analyze at least 3 games for skill profile."}

    # ── Aggregate stats ──
    agg_q = (
        select(
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.avg(GameAnalysis.phase_opening_cpl).label("opening_cpl"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame_cpl"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame_cpl"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(GameAnalysis.best_moves_count).label("total_best"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    agg = (await db.execute(agg_q)).one()

    avg_cpl = agg.avg_cpl or 50
    opening_cpl = agg.opening_cpl or avg_cpl
    middlegame_cpl = agg.middlegame_cpl or avg_cpl
    endgame_cpl = agg.endgame_cpl or avg_cpl
    total_blunders = agg.total_blunders or 0
    total_best = agg.total_best or 0
    total_moves = agg.total_moves or 1
    player_moves = total_moves / 2  # both sides counted

    # ── CPL standard deviation for consistency ──
    cpl_stddev_q = (
        select(func.stddev(GameAnalysis.overall_cpl))
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id, GameAnalysis.overall_cpl.isnot(None))
    )
    cpl_stddev = (await db.execute(cpl_stddev_q)).scalar() or 20

    # ── Normalize to 0-100 (higher = better) ──
    def cpl_to_score(cpl_val: float) -> int:
        """Map CPL to 0-100 where 0 CPL → 100, 100+ CPL → ~10."""
        score = max(0, min(100, round(103.17 * 2.718 ** (-0.01 * cpl_val) - 3.17)))
        return score

    opening_score = cpl_to_score(opening_cpl)
    middlegame_score = cpl_to_score(middlegame_cpl)
    endgame_score = cpl_to_score(endgame_cpl)

    # Tactics: best-move ratio (% of moves that are engine-best)
    best_rate = (total_best / player_moves * 100) if player_moves > 0 else 0
    tactics_score = max(0, min(100, round(best_rate * 2)))  # 50% best → 100

    # Composure: inverse blunder rate (fewer blunders = higher score)
    blunder_rate = (total_blunders / player_moves * 100) if player_moves > 0 else 5
    composure_score = max(0, min(100, round(100 - blunder_rate * 15)))

    # Consistency: inverse of CPL standard deviation
    consistency_score = max(0, min(100, round(100 - cpl_stddev * 2)))

    return {
        "has_data": True,
        "analyzed_games": analyzed_count,
        "axes": [
            {"axis": "Opening", "score": opening_score},
            {"axis": "Middlegame", "score": middlegame_score},
            {"axis": "Endgame", "score": endgame_score},
            {"axis": "Tactics", "score": tactics_score},
            {"axis": "Composure", "score": composure_score},
            {"axis": "Consistency", "score": consistency_score},
        ],
        "overall_score": round(
            (opening_score + middlegame_score + endgame_score + tactics_score + composure_score + consistency_score) / 6
        ),
    }


@router.get("/progress")
async def get_progress(
    months: int = 6,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Monthly progress data – CPL, accuracy, and blunder rate over time.
    Used for progress line/area charts.
    """
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=months * 30)

    # Monthly aggregates
    monthly_q = (
        select(
            func.date_trunc("month", Game.date).label("month"),
            func.count().label("games"),
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.avg(GameAnalysis.accuracy).label("avg_accuracy"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.date >= cutoff)
        .group_by(func.date_trunc("month", Game.date))
        .order_by(func.date_trunc("month", Game.date).asc())
    )
    rows = (await db.execute(monthly_q)).all()

    data_points = []
    for r in rows:
        player_moves = (r.total_moves or 0) / 2
        blunder_rate = round(r.total_blunders / player_moves * 100, 2) if player_moves > 0 and r.total_blunders else 0
        data_points.append({
            "period": r.month.strftime("%Y-%m") if r.month else None,
            "games": r.games,
            "avg_cpl": round(r.avg_cpl, 1) if r.avg_cpl else None,
            "accuracy": round(r.avg_accuracy, 1) if r.avg_accuracy else None,
            "blunder_rate": blunder_rate,
        })

    return {"months": months, "data": data_points}


@router.get("/phase-breakdown")
async def get_phase_breakdown(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """CPL breakdown by game phase (opening / middlegame / endgame)."""
    q = (
        select(
            func.avg(GameAnalysis.phase_opening_cpl).label("opening"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    row = (await db.execute(q)).one_or_none()
    if not row:
        return {"opening": None, "middlegame": None, "endgame": None}

    return {
        "opening": round(row.opening, 1) if row.opening else None,
        "middlegame": round(row.middlegame, 1) if row.middlegame else None,
        "endgame": round(row.endgame, 1) if row.endgame else None,
    }


@router.get("/openings")
async def get_opening_stats(
    color: Optional[str] = None,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Opening repertoire statistics."""
    query = select(OpeningRepertoire).where(OpeningRepertoire.user_id == user.id)
    if color:
        query = query.where(OpeningRepertoire.color == color)
    query = query.order_by(OpeningRepertoire.games_played.desc())

    result = await db.execute(query)
    openings = result.scalars().all()

    return [
        {
            "opening_name": o.opening_name,
            "eco_code": o.eco_code,
            "color": o.color,
            "games_played": o.games_played,
            "win_rate": round(o.games_won / o.games_played * 100, 1) if o.games_played > 0 else 0,
            "average_cpl": round(o.average_cpl, 1) if o.average_cpl else None,
            "early_deviations": o.early_deviations,
        }
        for o in openings
    ]


@router.get("/weaknesses")
async def get_weaknesses(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Top 3 actionable weaknesses derived from analysis data.
    This is the opinionated coaching surface – deterministic, not AI.
    """
    # Get phase breakdown
    phase_q = (
        select(
            func.avg(GameAnalysis.phase_opening_cpl).label("opening"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame"),
            func.avg(GameAnalysis.overall_cpl).label("overall"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    phase = (await db.execute(phase_q)).one_or_none()

    if not phase or phase.overall is None:
        return {"weaknesses": [], "message": "Not enough data. Analyze some games first."}

    weaknesses = []
    baseline = phase.overall or 50

    # Phase weaknesses – relative comparison first, then absolute fallback
    phase_entries = [
        ("Opening", phase.opening, "Your opening accuracy is below your overall level.", "Focus on learning your opening lines deeper."),
        ("Middlegame", phase.middlegame, "You lose accuracy in complex middlegame positions.", "Practice tactical puzzles to improve calculation."),
        ("Endgame", phase.endgame, "Your endgame technique needs work.", "Study basic endgame positions (K+P, R+P)."),
    ]
    for area, cpl, msg, action in phase_entries:
        if cpl and cpl > baseline * 1.15:
            weaknesses.append({
                "area": area,
                "severity": "high" if cpl > baseline * 1.3 else "medium",
                "message": msg,
                "cpl": round(cpl, 1),
                "action": action,
            })

    # Blunder pattern
    blunder_q = (
        select(
            MoveEvaluation.blunder_subtype,
            func.count().label("cnt"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.blunder_subtype.isnot(None),
        )
        .group_by(MoveEvaluation.blunder_subtype)
        .order_by(func.count().desc())
        .limit(1)
    )
    top_blunder = (await db.execute(blunder_q)).one_or_none()

    if top_blunder and top_blunder.cnt >= 3:
        subtype_messages = {
            "hanging_piece": "You frequently leave pieces undefended.",
            "missed_tactic": "You miss tactical opportunities (forks, pins, skewers).",
            "king_safety": "You make moves that weaken your king's safety.",
            "endgame_technique": "You make technical errors in simplified positions.",
        }
        weaknesses.append({
            "area": "Blunder Pattern",
            "severity": "high",
            "message": subtype_messages.get(top_blunder.blunder_subtype, f"Recurring {top_blunder.blunder_subtype} blunders."),
            "count": top_blunder.cnt,
            "action": f"Train positions involving {top_blunder.blunder_subtype.replace('_', ' ')}.",
        })

    # Converting advantages – games where player was winning but lost
    collapse_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result == "loss",
            MoveEvaluation.eval_after.isnot(None),
            MoveEvaluation.eval_after > 200,
        )
    )
    collapses = (await db.execute(collapse_q)).scalar() or 0
    if collapses >= 2:
        weaknesses.append({
            "area": "Converting Advantages",
            "severity": "high" if collapses >= 5 else "medium",
            "message": f"You collapsed from winning positions {collapses} times. Practice converting won endgames.",
            "count": collapses,
            "action": "Focus on technique in won positions.",
        })

    # Time control weakness – find worst performing time control
    tc_q = (
        select(
            Game.time_control,
            func.count().label("cnt"),
            func.avg(GameAnalysis.overall_cpl).label("tc_cpl"),
            func.sum(case((Game.result == "win", 1), else_=0)).label("wins"),
        )
        .join(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.time_control.isnot(None))
        .group_by(Game.time_control)
        .having(func.count() >= 3)
        .order_by(func.avg(GameAnalysis.overall_cpl).desc())
        .limit(1)
    )
    worst_tc_row = (await db.execute(tc_q)).one_or_none()
    if worst_tc_row and worst_tc_row.tc_cpl and worst_tc_row.tc_cpl > baseline * 1.1:
        weaknesses.append({
            "area": "Time Management",
            "severity": "medium",
            "message": f"You underperform in {worst_tc_row.time_control} games. Consider adjusting your time usage in that format.",
            "action": "Review your clock usage in this format.",
        })

    # Fallback: if no weaknesses found, identify the worst phase by absolute CPL
    if not weaknesses:
        worst_phase = None
        worst_cpl = 0.0
        for area, cpl in [("Opening", phase.opening), ("Middlegame", phase.middlegame), ("Endgame", phase.endgame)]:
            if cpl and cpl > worst_cpl:
                worst_cpl = cpl
                worst_phase = area
        if worst_phase:
            weaknesses.append({
                "area": worst_phase,
                "severity": "medium" if worst_cpl > 40 else "low",
                "message": f"Your {worst_phase.lower()} is your weakest phase at {round(worst_cpl, 1)} avg CPL.",
                "cpl": round(worst_cpl, 1),
                "action": f"Focus training on {worst_phase.lower()} positions.",
            })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    weaknesses.sort(key=lambda w: severity_order.get(w["severity"], 2))

    return {"weaknesses": weaknesses[:5]}


@router.get("/time-analysis")
async def get_time_analysis(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Time management analysis – blunders under time pressure,
    average move time, and time-control performance split.
    """
    # Blunders under time pressure (< 30 seconds remaining)
    time_pressure_q = (
        select(
            func.count().label("total_time_pressure_moves"),
            func.sum(
                case(
                    (MoveEvaluation.move_quality == "Blunder", 1),
                    else_=0,
                )
            ).label("time_pressure_blunders"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.time_remaining.isnot(None),
            MoveEvaluation.time_remaining < 30,
        )
    )
    tp_row = (await db.execute(time_pressure_q)).one_or_none()

    # Normal blunders (not under time pressure)
    normal_q = (
        select(
            func.count().label("total_normal_moves"),
            func.sum(
                case(
                    (MoveEvaluation.move_quality == "Blunder", 1),
                    else_=0,
                )
            ).label("normal_blunders"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.time_remaining.isnot(None),
            MoveEvaluation.time_remaining >= 30,
        )
    )
    n_row = (await db.execute(normal_q)).one_or_none()

    # Average move time from analysis
    avg_time_q = (
        select(func.avg(GameAnalysis.average_move_time))
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    avg_move_time = (await db.execute(avg_time_q)).scalar()

    # Time control breakdown
    tc_q = (
        select(
            Game.time_control,
            func.count().label("games"),
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.sum(case((Game.result == "win", 1), else_=0)).label("wins"),
        )
        .outerjoin(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.time_control.isnot(None))
        .group_by(Game.time_control)
        .order_by(func.count().desc())
        .limit(5)
    )
    tc_rows = (await db.execute(tc_q)).all()

    time_controls = [
        {
            "time_control": r.time_control,
            "games": r.games,
            "avg_cpl": round(r.avg_cpl, 1) if r.avg_cpl else None,
            "win_rate": round(r.wins / r.games * 100, 1) if r.games > 0 else 0,
        }
        for r in tc_rows
    ]

    return {
        "time_pressure_moves": tp_row.total_time_pressure_moves if tp_row else 0,
        "time_pressure_blunders": tp_row.time_pressure_blunders if tp_row else 0,
        "normal_moves": n_row.total_normal_moves if n_row else 0,
        "normal_blunders": n_row.normal_blunders if n_row else 0,
        "avg_move_time": round(avg_move_time, 1) if avg_move_time else None,
        "time_controls": time_controls,
    }


@router.get("/streaks")
async def get_streaks(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Win/loss streak tracking."""
    from app.db.models import Streak

    result = await db.execute(
        select(Streak).where(Streak.user_id == user.id)
    )
    streaks = result.scalars().all()

    # Also compute current streak from recent games
    recent_q = (
        select(Game.result)
        .where(Game.user_id == user.id)
        .order_by(Game.date.desc())
        .limit(50)
    )
    recent = (await db.execute(recent_q)).scalars().all()

    current_streak = 0
    streak_type = None
    if recent:
        streak_type = recent[0]  # "win", "loss", or "draw"
        for r in recent:
            if r == streak_type:
                current_streak += 1
            else:
                break

    return {
        "current_streak": current_streak,
        "current_streak_type": streak_type,
        "saved_streaks": [
            {
                "type": s.streak_type,
                "current": s.current_count,
                "best": s.best_count,
            }
            for s in streaks
        ],
    }


@router.get("/recent-games")
async def get_recent_games(
    limit: int = 5,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Last N games for the home-page activity feed."""
    from sqlalchemy.orm import selectinload

    q = (
        select(Game)
        .where(Game.user_id == user.id)
        .options(selectinload(Game.analysis))
        .order_by(Game.date.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    return [
        {
            "id": g.id,
            "date": g.date.isoformat() if g.date else None,
            "color": g.color,
            "result": g.result,
            "opening_name": g.opening_name,
            "platform": g.platform,
            "player_elo": g.player_elo,
            "opponent_elo": g.opponent_elo,
            "time_control": g.time_control,
            "has_analysis": g.analysis is not None,
            "overall_cpl": g.analysis.overall_cpl if g.analysis else None,
        }
        for g in rows
    ]


@router.get("/advanced-analytics")
async def get_advanced_analytics(
    time_control: Optional[str] = Query(None, description="Filter: all, bullet, blitz, rapid, classical"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Advanced player analytics – style classification, comeback ability,
    strengths/weaknesses summary, study recommendations.
    All deterministic, no AI/LLM.
    """
    # ── Time control filter setup ──
    tc_filter = time_control if time_control and time_control != "all" else None

    # Build a set of matching game IDs for the time control filter
    if tc_filter:
        # Fetch all games for user, classify in Python, build id set
        all_games_q = select(Game.id, Game.time_control).where(Game.user_id == user.id)
        all_games_rows = (await db.execute(all_games_q)).all()
        matching_ids = [
            r.id for r in all_games_rows
            if _classify_time_control(r.time_control) == tc_filter
        ]
        if not matching_ids:
            return {
                "has_data": False,
                "message": f"No games found for time control: {tc_filter}.",
            }
        tc_game_filter = Game.id.in_(matching_ids)
    else:
        tc_game_filter = None  # no filter

    # ── Base counts ──
    total_q = select(func.count()).select_from(Game).where(Game.user_id == user.id)
    if tc_game_filter is not None:
        total_q = total_q.where(tc_game_filter)
    total_games = (await db.execute(total_q)).scalar() or 0

    analyzed_q = (
        select(func.count())
        .select_from(GameAnalysis)
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    if tc_game_filter is not None:
        analyzed_q = analyzed_q.where(tc_game_filter)
    analyzed_games = (await db.execute(analyzed_q)).scalar() or 0

    if analyzed_games < 3:
        return {
            "has_data": False,
            "message": "Analyze at least 3 games to unlock advanced analytics.",
        }

    # ── Aggregate stats ──
    agg_q = (
        select(
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.avg(GameAnalysis.phase_opening_cpl).label("opening_cpl"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame_cpl"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame_cpl"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(GameAnalysis.mistakes_count).label("total_mistakes"),
            func.sum(GameAnalysis.inaccuracies_count).label("total_inaccuracies"),
            func.sum(GameAnalysis.best_moves_count).label("total_best"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    if tc_game_filter is not None:
        agg_q = agg_q.where(tc_game_filter)
    agg = (await db.execute(agg_q)).one()

    avg_cpl = agg.avg_cpl or 50
    total_blunders = agg.total_blunders or 0
    total_mistakes = agg.total_mistakes or 0
    total_inaccuracies = agg.total_inaccuracies or 0
    total_best = agg.total_best or 0
    total_moves = agg.total_moves or 1

    # ── Win/loss/draw breakdown ──
    results_q = (
        select(
            Game.result,
            func.count().label("cnt"),
        )
        .where(Game.user_id == user.id)
    )
    if tc_game_filter is not None:
        results_q = results_q.where(tc_game_filter)
    results_q = results_q.group_by(Game.result)
    result_rows = (await db.execute(results_q)).all()
    result_map = {r.result: r.cnt for r in result_rows}
    wins = result_map.get("win", 0)
    losses = result_map.get("loss", 0)
    draws = result_map.get("draw", 0)

    # ── Style classification ──
    blunder_rate = total_blunders / total_moves * 100 if total_moves else 0
    mistake_rate = total_mistakes / total_moves * 100 if total_moves else 0
    best_rate = total_best / total_moves * 100 if total_moves else 0
    error_rate = blunder_rate + mistake_rate  # combined error frequency

    # Determine primary & secondary style traits
    styles = []

    # Tactical: high error count but also high best-move count (sharp play)
    if best_rate > 40 and error_rate > 3:
        styles.append({"trait": "Tactical", "icon": "⚔️",
                        "description": "You thrive in sharp, complicated positions. You find great moves but also make more errors than average — typical of a tactical fighter."})
    elif best_rate > 50:
        styles.append({"trait": "Tactical", "icon": "⚔️",
                        "description": "You frequently find the best moves in critical positions, showing strong tactical vision."})

    # Solid / Positional: low CPL, low error rate
    if avg_cpl < 25 and error_rate < 2:
        styles.append({"trait": "Solid", "icon": "🏰",
                        "description": "You play clean, low-error chess. You rarely blunder and grind opponents down with consistency."})
    elif avg_cpl < 35 and error_rate < 3:
        styles.append({"trait": "Positional", "icon": "🧠",
                        "description": "You prefer quiet, strategic play. Your accuracy is above average with few wild swings."})

    # Aggressive: high win rate but also high loss rate (decisive games)
    if total_games > 0:
        win_pct = wins / total_games * 100
        loss_pct = losses / total_games * 100
        draw_pct = draws / total_games * 100

        if draw_pct < 10 and total_games >= 5:
            styles.append({"trait": "Aggressive", "icon": "🔥",
                            "description": "You play for a decisive result. Your games rarely end in draws — you push for the win."})
        elif win_pct > 55 and loss_pct > 30:
            styles.append({"trait": "Risk-Taker", "icon": "🎲",
                            "description": "You take bold risks that lead to big wins, but also sharp losses. High variance play."})

    # Endgame specialist or weakness
    opening_cpl = agg.opening_cpl or avg_cpl
    middlegame_cpl = agg.middlegame_cpl or avg_cpl
    endgame_cpl = agg.endgame_cpl or avg_cpl

    phase_cpls = {"opening": opening_cpl, "middlegame": middlegame_cpl, "endgame": endgame_cpl}
    best_phase = min(phase_cpls, key=phase_cpls.get)
    worst_phase = max(phase_cpls, key=phase_cpls.get)

    if best_phase == "endgame" and endgame_cpl < avg_cpl * 0.75:
        styles.append({"trait": "Endgame Specialist", "icon": "♟️",
                        "description": "Your endgame technique is your strongest phase — you convert advantages reliably."})
    elif best_phase == "opening" and opening_cpl < avg_cpl * 0.75:
        styles.append({"trait": "Opening Expert", "icon": "📖",
                        "description": "You play the opening with high accuracy — your preparation gives you a reliable edge."})

    # Resilient: good win rate vs higher rated
    upset_q = (
        select(func.count())
        .select_from(Game)
        .where(
            Game.user_id == user.id,
            Game.result == "win",
            Game.opponent_elo.isnot(None),
            Game.player_elo.isnot(None),
            Game.opponent_elo > Game.player_elo + 100,
        )
    )
    if tc_game_filter is not None:
        upset_q = upset_q.where(tc_game_filter)
    upsets = (await db.execute(upset_q)).scalar() or 0
    if upsets >= 3:
        styles.append({"trait": "Giant Killer", "icon": "🗡️",
                        "description": f"You've beaten higher-rated opponents {upsets} times — you rise to the challenge against stronger players."})

    # Fallback if no styles detected
    if not styles:
        if avg_cpl < 40:
            styles.append({"trait": "Balanced", "icon": "⚖️",
                            "description": "You have a well-rounded playing style with no extreme tendencies."})
        else:
            styles.append({"trait": "Developing", "icon": "🌱",
                            "description": "Your style is still forming. Keep playing and analyzing to develop your chess identity."})

    primary_style = styles[0] if styles else None
    secondary_styles = styles[1:4]  # up to 3 more

    # ── Comeback ability ──
    # Games where player was down material (eval < -200cp at some point) but still won
    comeback_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result == "win",
            MoveEvaluation.eval_after.isnot(None),
            MoveEvaluation.eval_after < -200,  # player was losing by 2+ pawns
        )
    )
    if tc_game_filter is not None:
        comeback_q = comeback_q.where(tc_game_filter)
    comeback_wins = (await db.execute(comeback_q)).scalar() or 0

    # Games where player was winning but lost
    collapse_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result == "loss",
            MoveEvaluation.eval_after.isnot(None),
            MoveEvaluation.eval_after > 200,  # player was winning by 2+ pawns
        )
    )
    if tc_game_filter is not None:
        collapse_q = collapse_q.where(tc_game_filter)
    collapses = (await db.execute(collapse_q)).scalar() or 0

    # ── Strengths & Weaknesses summary ──
    strengths = []
    weaknesses_list = []

    # Best phase
    strengths.append({
        "area": best_phase.capitalize(),
        "detail": f"Your strongest phase — {round(phase_cpls[best_phase], 1)} avg CPL.",
    })

    # Worst phase
    if phase_cpls[worst_phase] > phase_cpls[best_phase] * 1.3:
        weaknesses_list.append({
            "area": worst_phase.capitalize(),
            "detail": f"Your weakest phase — {round(phase_cpls[worst_phase], 1)} avg CPL.",
        })

    # Best move ratio
    if best_rate > 45:
        strengths.append({
            "area": "Accuracy",
            "detail": f"{round(best_rate, 1)}% of your moves are engine best moves.",
        })

    # Blunder tendency
    if blunder_rate > 2:
        weaknesses_list.append({
            "area": "Blunders",
            "detail": f"{round(blunder_rate, 1)} blunders per 100 moves — focus on checking for tactics before moving.",
        })
    elif blunder_rate < 1:
        strengths.append({
            "area": "Composure",
            "detail": f"Only {round(blunder_rate, 1)} blunders per 100 moves — very clean play.",
        })

    # Time control performance
    tc_q = (
        select(
            Game.time_control,
            func.count().label("cnt"),
            func.avg(GameAnalysis.overall_cpl).label("tc_cpl"),
            func.sum(case((Game.result == "win", 1), else_=0)).label("tc_wins"),
        )
        .outerjoin(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.time_control.isnot(None))
    )
    if tc_game_filter is not None:
        tc_q = tc_q.where(tc_game_filter)
    tc_q = (
        tc_q.group_by(Game.time_control)
        .having(func.count() >= 3)
        .order_by(func.avg(GameAnalysis.overall_cpl).asc())
    )
    tc_rows = (await db.execute(tc_q)).all()

    best_tc = None
    worst_tc = None
    if tc_rows:
        best_tc_row = tc_rows[0]
        worst_tc_row = tc_rows[-1]
        if best_tc_row.time_control != worst_tc_row.time_control:
            best_tc = best_tc_row.time_control
            worst_tc = worst_tc_row.time_control
            wr = round(best_tc_row.tc_wins / best_tc_row.cnt * 100, 1) if best_tc_row.cnt else 0
            strengths.append({
                "area": f"Time Control ({best_tc})",
                "detail": f"Your best format — {wr}% win rate, {round(best_tc_row.tc_cpl or 0, 1)} avg CPL.",
            })
            wr2 = round(worst_tc_row.tc_wins / worst_tc_row.cnt * 100, 1) if worst_tc_row.cnt else 0
            weaknesses_list.append({
                "area": f"Time Control ({worst_tc})",
                "detail": f"Your weakest format — {wr2}% win rate, {round(worst_tc_row.tc_cpl or 0, 1)} avg CPL.",
            })

    # ── Study recommendations ──
    recommendations = []

    if worst_phase == "endgame" and phase_cpls["endgame"] > avg_cpl * 1.15:
        recommendations.append({
            "priority": "high",
            "category": "Endgame",
            "message": "Study basic endgame positions (K+P, Rook endings). Your endgame accuracy drags down your results.",
        })
    if worst_phase == "opening" and phase_cpls["opening"] > avg_cpl * 1.15:
        recommendations.append({
            "priority": "high",
            "category": "Openings",
            "message": "Learn your opening lines deeper. You lose accuracy early and play catch-up.",
        })
    if worst_phase == "middlegame" and phase_cpls["middlegame"] > avg_cpl * 1.15:
        recommendations.append({
            "priority": "high",
            "category": "Tactics",
            "message": "Practice tactical puzzles daily. Your middlegame accuracy suggests missed tactics.",
        })
    if blunder_rate > 2.5:
        recommendations.append({
            "priority": "high",
            "category": "Blunder Check",
            "message": "Before each move, ask: 'Does this hang a piece?' Simple checks will cut your blunder rate.",
        })
    if collapses >= 3:
        recommendations.append({
            "priority": "medium",
            "category": "Converting Advantages",
            "message": f"You collapsed from winning positions {collapses} times. Practice converting won endgames.",
        })
    if worst_tc:
        recommendations.append({
            "priority": "medium",
            "category": "Time Management",
            "message": f"You underperform in {worst_tc} games. Consider adjusting your time usage in that format.",
        })

    if not recommendations:
        recommendations.append({
            "priority": "low",
            "category": "Keep Going",
            "message": "Your play is solid across the board. Focus on maintaining consistency and reviewing your losses.",
        })

    # ── Opening Performance (best & worst by avg CPL) ──
    opening_base_q = (
        select(
            Game.opening_name,
            func.count().label("games"),
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.sum(case((Game.result == "win", 1), else_=0)).label("wins"),
        )
        .join(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.opening_name.isnot(None))
    )
    if tc_game_filter is not None:
        opening_base_q = opening_base_q.where(tc_game_filter)
    opening_base_q = opening_base_q.group_by(Game.opening_name).having(func.count() >= 2)

    best_openings_q = opening_base_q.order_by(func.avg(GameAnalysis.overall_cpl).asc()).limit(5)
    worst_openings_q = opening_base_q.order_by(func.avg(GameAnalysis.overall_cpl).desc()).limit(5)

    best_opening_rows = (await db.execute(best_openings_q)).all()
    worst_opening_rows = (await db.execute(worst_openings_q)).all()

    def _format_opening(row):
        return {
            "name": row.opening_name,
            "games": row.games,
            "avg_cpl": round(row.avg_cpl, 1) if row.avg_cpl else None,
            "win_rate": round(row.wins / row.games * 100, 1) if row.games else 0,
        }

    best_openings = [_format_opening(r) for r in best_opening_rows]
    worst_openings = [_format_opening(r) for r in worst_opening_rows]

    # ── Piece Performance ──
    # Average CPL per piece, only for player's moves (color = player's color)
    # We need to know which color the player was, so we join with Game.color
    piece_q = (
        select(
            MoveEvaluation.piece,
            func.avg(MoveEvaluation.cp_loss).label("avg_cpl"),
            func.count().label("total_moves"),
            func.sum(case((MoveEvaluation.move_quality == "Best", 1), else_=0)).label("best_count"),
            func.sum(case((MoveEvaluation.move_quality == "Blunder", 1), else_=0)).label("blunder_count"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.piece.isnot(None),
            MoveEvaluation.color == Game.color,  # only player's moves
        )
    )
    if tc_game_filter is not None:
        piece_q = piece_q.where(tc_game_filter)
    piece_q = piece_q.group_by(MoveEvaluation.piece).having(func.count() >= 5)
    piece_rows = (await db.execute(piece_q)).all()

    piece_names = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}
    piece_icons = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙"}

    all_pieces = []
    for r in piece_rows:
        all_pieces.append({
            "piece": r.piece,
            "name": piece_names.get(r.piece, r.piece),
            "icon": piece_icons.get(r.piece, ""),
            "avg_cpl": round(r.avg_cpl, 1) if r.avg_cpl else 0,
            "total_moves": r.total_moves,
            "best_rate": round(r.best_count / r.total_moves * 100, 1) if r.total_moves else 0,
            "blunder_rate": round(r.blunder_count / r.total_moves * 100, 1) if r.total_moves else 0,
        })

    # Sort by avg_cpl ascending (best first)
    all_pieces.sort(key=lambda p: p["avg_cpl"])
    best_pieces = all_pieces[:3] if all_pieces else []
    worst_pieces = list(reversed(all_pieces[-3:])) if all_pieces else []

    return {
        "has_data": True,
        "analyzed_games": analyzed_games,
        "total_games": total_games,
        # Style
        "primary_style": primary_style,
        "secondary_styles": secondary_styles,
        # Comeback
        "comeback_wins": comeback_wins,
        "collapses": collapses,
        # Strengths & weaknesses
        "strengths": strengths[:4],
        "weaknesses": weaknesses_list[:4],
        # Recommendations
        "recommendations": recommendations[:5],
        # Openings
        "best_openings": best_openings,
        "worst_openings": worst_openings,
        # Pieces
        "best_pieces": best_pieces,
        "worst_pieces": worst_pieces,
        "all_pieces": all_pieces,
        # Raw stats for display
        "stats": {
            "avg_cpl": round(avg_cpl, 1),
            "blunder_rate": round(blunder_rate, 1),
            "mistake_rate": round(mistake_rate, 1),
            "best_move_rate": round(best_rate, 1),
            "win_rate": round(wins / total_games * 100, 1) if total_games else 0,
            "draw_rate": round(draws / total_games * 100, 1) if total_games else 0,
            "upsets": upsets,
            "best_phase": best_phase,
            "worst_phase": worst_phase,
        },
    }


# ═══════════════════════════════════════════════════════════
# Chess Identity – Fixed Persona System
# ═══════════════════════════════════════════════════════════

# 12 fixed personas. Each has matching criteria evaluated against player metrics.
# The persona with the highest match score is assigned.

CHESS_PERSONAS = [
    {
        "id": "the_tactician",
        "name": "The Tactician",
        "emoji": "⚔️",
        "tagline": "You see the board in combinations, not positions.",
        "gm_comparison": "Mikhail Tal",
        "description": "You live for the attack. Your games are full of sharp tactics, sacrifices, and forcing sequences. You'd rather calculate 10 moves deep than slowly maneuver a knight. When it works, it's brilliant. When it doesn't, it's spectacular.",
        "color": "#ef4444",  # red
    },
    {
        "id": "the_fortress",
        "name": "The Fortress",
        "emoji": "🏰",
        "tagline": "You don't beat opponents — you outlast them.",
        "gm_comparison": "Tigran Petrosian",
        "description": "You are the wall. Your opponents crash against your solid position and slowly run out of ideas. You rarely blunder, rarely take risks, and rarely lose games you shouldn't. Your chess is clean, disciplined, and frustrating to face.",
        "color": "#3b82f6",  # blue
    },
    {
        "id": "the_grinder",
        "name": "The Grinder",
        "emoji": "🔧",
        "tagline": "You squeeze water from stones.",
        "gm_comparison": "Anatoly Karpov",
        "description": "You don't need fireworks. A small edge is all you need — a slightly better pawn structure, a tiny initiative — and you nurse it into a win. Your endgame technique is your lethal weapon. Opponents hate playing you because nothing is ever truly drawn.",
        "color": "#8b5cf6",  # purple
    },
    {
        "id": "the_speedster",
        "name": "The Speedster",
        "emoji": "⚡",
        "tagline": "Your clock is a weapon, not a constraint.",
        "gm_comparison": "Hikaru Nakamura",
        "description": "You thrive under time pressure. While opponents panic with 30 seconds left, you play your best chess. Fast time controls are your playground — bullet and blitz bring out something in you that classical never does.",
        "color": "#f59e0b",  # amber
    },
    {
        "id": "the_scientist",
        "name": "The Scientist",
        "emoji": "🔬",
        "tagline": "Every position is a puzzle to be solved precisely.",
        "gm_comparison": "Vladimir Kramnik",
        "description": "You approach chess with methodical precision. You don't wing it — you calculate, evaluate, and choose. Your best-move rate is high because you treat every position like a laboratory experiment. When the position demands accuracy, you deliver.",
        "color": "#06b6d4",  # cyan
    },
    {
        "id": "the_phoenix",
        "name": "The Phoenix",
        "emoji": "🔥",
        "tagline": "You don't know the meaning of a lost position.",
        "gm_comparison": "David Bronstein",
        "description": "Other players resign positions you go on to win. You have an uncanny ability to create complications when you're losing, and your opponents crack under the pressure. Your comebacks aren't lucky — they're a pattern.",
        "color": "#f97316",  # orange
    },
    {
        "id": "the_assassin",
        "name": "The Assassin",
        "emoji": "🗡️",
        "tagline": "You play up. You don't play down.",
        "gm_comparison": "Garry Kasparov",
        "description": "Higher-rated opponents don't intimidate you — they motivate you. You have a remarkable ability to raise your game against stronger players. Upsets aren't anomalies for you, they're a signature.",
        "color": "#dc2626",  # red-600
    },
    {
        "id": "the_chameleon",
        "name": "The Chameleon",
        "emoji": "🦎",
        "tagline": "You have no weaknesses because you have every style.",
        "gm_comparison": "Magnus Carlsen",
        "description": "You're dangerous because you're unpredictable. Your skill profile is balanced — no clear weakness, no obvious pattern for opponents to exploit. You can grind endgames, attack kings, or play positionally depending on what the position demands.",
        "color": "#10b981",  # emerald
    },
    {
        "id": "the_berserker",
        "name": "The Berserker",
        "emoji": "💥",
        "tagline": "Your games are never boring.",
        "gm_comparison": "Rashid Nezhmetdinov",
        "description": "Draw? What draw? Your games end decisively — either you win spectacularly or you go down in flames. You take risks others wouldn't dream of. Your opponents never know what's coming, and frankly, sometimes neither do you.",
        "color": "#e11d48",  # rose
    },
    {
        "id": "the_professor",
        "name": "The Professor",
        "emoji": "📖",
        "tagline": "You win games before move 15.",
        "gm_comparison": "Levon Aronian",
        "description": "Your opening preparation is your superpower. While opponents are still figuring out what to play, you're already out of book with a comfortable position. Your opening accuracy is significantly better than the rest of your game.",
        "color": "#6366f1",  # indigo
    },
    {
        "id": "the_survivor",
        "name": "The Survivor",
        "emoji": "🛡️",
        "tagline": "You bend, but you don't break.",
        "gm_comparison": "Viswanathan Anand",
        "description": "You might not always find the best move, but you almost never find the worst one. Your composure under pressure is remarkable — low blunder rate, consistent play, and a knack for holding difficult positions.",
        "color": "#14b8a6",  # teal
    },
    {
        "id": "the_adventurer",
        "name": "The Adventurer",
        "emoji": "🌟",
        "tagline": "Your chess identity is still being written.",
        "gm_comparison": "Bobby Fischer (early career)",
        "description": "You're on a journey. Your style is evolving with every game you play, and the data shows it — improving trends, growing pattern recognition, and a hunger to learn. The most exciting thing about your chess? What comes next.",
        "color": "#a855f7",  # violet
    },
]


def _score_persona(persona_id: str, metrics: dict) -> float:
    """
    Score how well a player matches each persona.
    Returns a float score — higher is better match.
    All logic is deterministic based on metrics.
    """
    score = 0.0

    avg_cpl = metrics.get("avg_cpl", 50)
    blunder_rate = metrics.get("blunder_rate", 3)
    best_rate = metrics.get("best_rate", 30)
    error_rate = metrics.get("error_rate", 5)
    win_rate = metrics.get("win_rate", 50)
    draw_rate = metrics.get("draw_rate", 15)
    comeback_wins = metrics.get("comeback_wins", 0)
    collapses = metrics.get("collapses", 0)
    upsets = metrics.get("upsets", 0)
    opening_cpl = metrics.get("opening_cpl", 50)
    middlegame_cpl = metrics.get("middlegame_cpl", 50)
    endgame_cpl = metrics.get("endgame_cpl", 50)
    cpl_stddev = metrics.get("cpl_stddev", 20)
    total_games = metrics.get("total_games", 0)
    best_tc = metrics.get("best_tc_category", "")
    skill_balance = metrics.get("skill_balance", 20)  # lower = more balanced
    trend = metrics.get("trend", "stable")

    if persona_id == "the_tactician":
        # High best-move rate + high error rate = sharp tactical player
        if best_rate > 40:
            score += (best_rate - 40) * 2
        if error_rate > 3:
            score += (error_rate - 3) * 3
        if middlegame_cpl > avg_cpl:
            score += 5  # middlegame complexity
        if best_rate > 50 and error_rate > 4:
            score += 15  # quintessential tactician

    elif persona_id == "the_fortress":
        # Low blunder rate, low CPL, few collapses
        if blunder_rate < 1.5:
            score += (1.5 - blunder_rate) * 20
        if avg_cpl < 30:
            score += (30 - avg_cpl) * 1.5
        if error_rate < 2.5:
            score += (2.5 - error_rate) * 8
        if collapses == 0 and total_games >= 5:
            score += 10

    elif persona_id == "the_grinder":
        # Endgame specialist — endgame CPL much lower than avg
        if endgame_cpl < avg_cpl * 0.8:
            score += (avg_cpl - endgame_cpl) * 1.5
        if endgame_cpl < opening_cpl and endgame_cpl < middlegame_cpl:
            score += 20
        if blunder_rate < 2:
            score += 5

    elif persona_id == "the_speedster":
        # Best performance in bullet/blitz
        if best_tc in ("bullet", "blitz"):
            score += 25
        # Low time-pressure blunder rate indicates good time management
        tp_blunder_ratio = metrics.get("time_pressure_blunder_ratio", None)
        if tp_blunder_ratio is not None and tp_blunder_ratio < 0.1:
            score += 15

    elif persona_id == "the_scientist":
        # Very high best-move rate, low CPL
        if best_rate > 45:
            score += (best_rate - 45) * 4
        if avg_cpl < 25:
            score += (25 - avg_cpl) * 2
        if error_rate < 2:
            score += 10
        if cpl_stddev < 12:
            score += 10  # consistent precision

    elif persona_id == "the_phoenix":
        # High comeback wins relative to games
        if comeback_wins >= 3:
            score += comeback_wins * 5
        if comeback_wins >= 5:
            score += 15  # bonus for truly prolific comebacks
        comeback_ratio = comeback_wins / max(total_games, 1)
        if comeback_ratio > 0.1:
            score += 20

    elif persona_id == "the_assassin":
        # Giant killer — beats higher-rated players
        if upsets >= 3:
            score += upsets * 4
        if upsets >= 5:
            score += 15
        upset_ratio = upsets / max(total_games, 1)
        if upset_ratio > 0.08:
            score += 20

    elif persona_id == "the_chameleon":
        # Balanced skill profile — low variance across axes
        if skill_balance < 10:
            score += (10 - skill_balance) * 5
        if skill_balance < 15:
            score += 10
        # No extreme phase difference
        phase_range = max(opening_cpl, middlegame_cpl, endgame_cpl) - min(opening_cpl, middlegame_cpl, endgame_cpl)
        if phase_range < 10:
            score += 15
        elif phase_range < 15:
            score += 8

    elif persona_id == "the_berserker":
        # Very low draw rate, high variance
        if draw_rate < 8:
            score += (8 - draw_rate) * 4
        if cpl_stddev > 25:
            score += (cpl_stddev - 25) * 2
        if draw_rate < 5 and total_games >= 5:
            score += 15

    elif persona_id == "the_professor":
        # Opening specialist — opening CPL much lower than other phases
        if opening_cpl < avg_cpl * 0.75:
            score += (avg_cpl - opening_cpl) * 2
        if opening_cpl < middlegame_cpl and opening_cpl < endgame_cpl:
            score += 15
        if opening_cpl < 15:
            score += 10  # excellent opening play

    elif persona_id == "the_survivor":
        # Very low blunder rate, high composure
        if blunder_rate < 1:
            score += (1 - blunder_rate) * 30
        if collapses <= 1 and total_games >= 10:
            score += 10
        if cpl_stddev < 15:
            score += 8

    elif persona_id == "the_adventurer":
        # Improving trend, relatively new player
        if trend == "improving":
            score += 20
        if total_games < 30:
            score += 10  # still finding style
        if total_games < 15:
            score += 10

    return score


@router.get("/chess-identity")
async def get_chess_identity(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Chess Identity — deterministic persona assignment based on all available metrics.
    Returns one primary persona with personalized stats and narrative details.
    """
    import hashlib, json

    # ── Check minimum data ──
    analyzed_q = (
        select(func.count())
        .select_from(GameAnalysis)
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    analyzed_count = (await db.execute(analyzed_q)).scalar() or 0
    if analyzed_count < 3:
        return {"has_data": False, "message": "Analyze at least 3 games to discover your chess identity."}

    # ── Total games ──
    total_q = select(func.count()).select_from(Game).where(Game.user_id == user.id)
    total_games = (await db.execute(total_q)).scalar() or 0

    # ── Aggregate stats ──
    agg_q = (
        select(
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.avg(GameAnalysis.phase_opening_cpl).label("opening_cpl"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame_cpl"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame_cpl"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(GameAnalysis.mistakes_count).label("total_mistakes"),
            func.sum(GameAnalysis.best_moves_count).label("total_best"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    agg = (await db.execute(agg_q)).one()

    avg_cpl = agg.avg_cpl or 50
    opening_cpl = agg.opening_cpl or avg_cpl
    middlegame_cpl = agg.middlegame_cpl or avg_cpl
    endgame_cpl = agg.endgame_cpl or avg_cpl
    total_blunders = agg.total_blunders or 0
    total_mistakes = agg.total_mistakes or 0
    total_best = agg.total_best or 0
    total_moves = agg.total_moves or 1
    player_moves = total_moves / 2

    blunder_rate = total_blunders / player_moves * 100 if player_moves > 0 else 0
    mistake_rate = total_mistakes / player_moves * 100 if player_moves > 0 else 0
    error_rate = blunder_rate + mistake_rate
    best_rate = total_best / player_moves * 100 if player_moves > 0 else 0

    # ── Win/loss/draw ──
    results_q = (
        select(Game.result, func.count().label("cnt"))
        .where(Game.user_id == user.id)
        .group_by(Game.result)
    )
    result_rows = (await db.execute(results_q)).all()
    result_map = {r.result: r.cnt for r in result_rows}
    wins = result_map.get("win", 0)
    losses = result_map.get("loss", 0)
    draws = result_map.get("draw", 0)
    win_rate = round(wins / total_games * 100, 1) if total_games else 0
    draw_rate = round(draws / total_games * 100, 1) if total_games else 0

    # ── CPL stddev for consistency ──
    cpl_stddev_q = (
        select(func.stddev(GameAnalysis.overall_cpl))
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id, GameAnalysis.overall_cpl.isnot(None))
    )
    cpl_stddev = (await db.execute(cpl_stddev_q)).scalar() or 20

    # ── Comeback wins ──
    comeback_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result == "win",
            MoveEvaluation.eval_after.isnot(None),
            MoveEvaluation.eval_after < -200,
        )
    )
    comeback_wins = (await db.execute(comeback_q)).scalar() or 0

    # ── Collapses ──
    collapse_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            Game.result == "loss",
            MoveEvaluation.eval_after.isnot(None),
            MoveEvaluation.eval_after > 200,
        )
    )
    collapses = (await db.execute(collapse_q)).scalar() or 0

    # ── Upsets (giant kills) ──
    upset_q = (
        select(func.count())
        .select_from(Game)
        .where(
            Game.user_id == user.id,
            Game.result == "win",
            Game.opponent_elo.isnot(None),
            Game.player_elo.isnot(None),
            Game.opponent_elo > Game.player_elo + 100,
        )
    )
    upsets = (await db.execute(upset_q)).scalar() or 0

    # ── Best time control ──
    tc_q = (
        select(
            Game.time_control,
            func.count().label("cnt"),
            func.avg(GameAnalysis.overall_cpl).label("tc_cpl"),
        )
        .outerjoin(GameAnalysis, GameAnalysis.game_id == Game.id)
        .where(Game.user_id == user.id, Game.time_control.isnot(None))
        .group_by(Game.time_control)
        .having(func.count() >= 3)
        .order_by(func.avg(GameAnalysis.overall_cpl).asc())
    )
    tc_rows = (await db.execute(tc_q)).all()
    best_tc_category = ""
    if tc_rows:
        best_tc_raw = tc_rows[0].time_control
        best_tc_category = _classify_time_control(best_tc_raw) or ""

    # ── Time pressure blunder ratio ──
    tp_q = (
        select(
            func.count().label("tp_moves"),
            func.sum(case((MoveEvaluation.move_quality == "Blunder", 1), else_=0)).label("tp_blunders"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.time_remaining.isnot(None),
            MoveEvaluation.time_remaining < 30,
        )
    )
    tp_row = (await db.execute(tp_q)).one_or_none()
    tp_blunder_ratio = None
    if tp_row and tp_row.tp_moves and tp_row.tp_moves > 0:
        tp_blunder_ratio = (tp_row.tp_blunders or 0) / tp_row.tp_moves

    # ── Skill balance (stddev of skill profile axes) ──
    # Recompute the 6 axes inline
    def cpl_to_score(cpl_val: float) -> int:
        return max(0, min(100, round(103.17 * 2.718 ** (-0.01 * cpl_val) - 3.17)))

    opening_score = cpl_to_score(opening_cpl)
    middlegame_score = cpl_to_score(middlegame_cpl)
    endgame_score = cpl_to_score(endgame_cpl)
    best_rate_pct = max(0, min(100, round(best_rate * 2)))
    composure_score = max(0, min(100, round(100 - blunder_rate * 15)))
    consistency_score = max(0, min(100, round(100 - cpl_stddev * 2)))

    axes_scores = [opening_score, middlegame_score, endgame_score, best_rate_pct, composure_score, consistency_score]
    axes_mean = sum(axes_scores) / len(axes_scores)
    skill_balance = (sum((s - axes_mean) ** 2 for s in axes_scores) / len(axes_scores)) ** 0.5

    # ── Trend ──
    recent_q = (
        select(GameAnalysis.overall_cpl)
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id, GameAnalysis.overall_cpl.isnot(None))
        .order_by(Game.date.desc())
        .limit(10)
    )
    recent_rows = (await db.execute(recent_q)).scalars().all()
    recent_cpl = sum(recent_rows) / len(recent_rows) if recent_rows else avg_cpl
    if avg_cpl and recent_cpl:
        diff = recent_cpl - avg_cpl
        trend = "improving" if diff < -5 else ("declining" if diff > 5 else "stable")
    else:
        trend = "stable"

    # ── Phase identification ──
    phase_cpls = {"opening": opening_cpl, "middlegame": middlegame_cpl, "endgame": endgame_cpl}
    best_phase = min(phase_cpls, key=phase_cpls.get)
    worst_phase = max(phase_cpls, key=phase_cpls.get)

    # ── Build metrics dict ──
    metrics = {
        "avg_cpl": avg_cpl,
        "blunder_rate": blunder_rate,
        "mistake_rate": mistake_rate,
        "error_rate": error_rate,
        "best_rate": best_rate,
        "win_rate": win_rate,
        "draw_rate": draw_rate,
        "comeback_wins": comeback_wins,
        "collapses": collapses,
        "upsets": upsets,
        "opening_cpl": opening_cpl,
        "middlegame_cpl": middlegame_cpl,
        "endgame_cpl": endgame_cpl,
        "cpl_stddev": cpl_stddev,
        "total_games": total_games,
        "best_tc_category": best_tc_category,
        "time_pressure_blunder_ratio": tp_blunder_ratio,
        "skill_balance": skill_balance,
        "trend": trend,
    }

    # ── Score all personas ──
    scored = []
    for persona in CHESS_PERSONAS:
        s = _score_persona(persona["id"], metrics)
        scored.append((s, persona))

    scored.sort(key=lambda x: x[0], reverse=True)
    primary = scored[0][1]
    primary_score = scored[0][0]

    # Secondary persona (if score > 50% of primary and different)
    secondary = None
    if len(scored) > 1 and scored[1][0] > primary_score * 0.5 and scored[1][0] > 5:
        secondary = scored[1][1]

    # ── Build personalized "signature stats" ──
    signature_stats = []

    # Always include best phase
    signature_stats.append({
        "label": "Strongest Phase",
        "value": best_phase.capitalize(),
        "detail": f"{round(phase_cpls[best_phase], 1)} avg CPL",
    })

    # Best-move rate
    signature_stats.append({
        "label": "Best Move Rate",
        "value": f"{round(best_rate, 1)}%",
        "detail": f"{total_best} engine-best moves",
    })

    # Blunder rate
    signature_stats.append({
        "label": "Blunder Rate",
        "value": f"{round(blunder_rate, 1)}/100",
        "detail": f"{total_blunders} total blunders",
    })

    # Comeback or upset count if notable
    if comeback_wins >= 2:
        signature_stats.append({
            "label": "Comebacks",
            "value": str(comeback_wins),
            "detail": "Wins from losing positions",
        })
    if upsets >= 2:
        signature_stats.append({
            "label": "Giant Kills",
            "value": str(upsets),
            "detail": "Wins vs higher-rated opponents",
        })

    # Win rate
    signature_stats.append({
        "label": "Win Rate",
        "value": f"{win_rate}%",
        "detail": f"{wins}W / {draws}D / {losses}L",
    })

    # ── Build "kryptonite" — what beats this player ──
    kryptonite = None
    if worst_phase and phase_cpls[worst_phase] > avg_cpl * 1.15:
        kryptonite = {
            "area": worst_phase.capitalize(),
            "message": f"Your {worst_phase} is your Achilles heel. It's significantly weaker than your other phases and costing you games you should be winning.",
        }
    elif collapses >= 3:
        kryptonite = {
            "area": "Converting Advantages",
            "message": f"You collapsed from winning positions {collapses} times. The wins are there — you just need to learn how to close them out.",
        }
    elif blunder_rate > 3:
        kryptonite = {
            "area": "Blunders",
            "message": "You're making too many critical errors. These aren't small inaccuracies — they're game-ending mistakes that are holding you back.",
        }

    # ── One thing to change ──
    one_thing = None
    if blunder_rate > 3:
        one_thing = "Before every move, ask yourself: 'Can my opponent take something?' Cutting your blunder rate in half would transform your results."
    elif worst_phase == "endgame" and endgame_cpl > avg_cpl * 1.2:
        one_thing = "Spend 15 minutes a day on basic endgames. King and pawn, rook endings. Your middlegame is already strong — the endgame is where your points are hiding."
    elif worst_phase == "opening" and opening_cpl > avg_cpl * 1.2:
        one_thing = "Pick one opening as White and one as Black. Learn them to move 10. You're losing accuracy in the first 15 moves and playing catch-up."
    elif collapses >= 3:
        one_thing = "When you're winning, slow down. Take a breath, check for your opponent's best response. Your biggest gains are in positions you've already earned."
    elif cpl_stddev > 25:
        one_thing = "Focus on consistency. Your best games show what you're capable of — make your average game look more like your best game."
    else:
        one_thing = "Keep playing and analyzing. Your chess is solid — incremental improvements in your weakest phase will unlock the next level."

    # ══════════════════════════════════════════════════════
    # ENHANCED REPORT: Why You, Chess Story, Tendencies,
    # Phase Breakdown, Growth Path
    # ══════════════════════════════════════════════════════

    # ── "Why You Match This Persona" — personalized match reasons ──
    why_you = []
    pid = primary["id"]

    if pid == "the_phoenix":
        comeback_pct = round(comeback_wins / max(total_games, 1) * 100, 1)
        why_you.append(f"You've won {comeback_wins} games from losing positions — that's {comeback_pct}% of your games. Most players have near-zero comebacks. You have a pattern of refusing to lose.")
        if collapses > 0 and comeback_wins > collapses:
            why_you.append(f"Your comeback-to-collapse ratio is {comeback_wins}:{collapses}. When positions get messy, you're more likely to be the one who survives.")
        if draw_rate < 10:
            why_you.append(f"You only draw {draw_rate}% of your games. You fight to the end — and that fighting spirit is what makes comebacks possible.")
    elif pid == "the_tactician":
        why_you.append(f"Your best-move rate of {round(best_rate, 1)}% shows strong tactical vision — you find the right move frequently.")
        if error_rate > 3:
            why_you.append(f"But your combined error rate of {round(error_rate, 1)} per 100 moves reveals the other side: you play sharp, complex chess that creates both brilliancies and blunders.")
        why_you.append("This combination — high best moves with higher-than-average errors — is the signature of a tactical fighter.")
    elif pid == "the_fortress":
        why_you.append(f"Your blunder rate is remarkably low — just {round(blunder_rate, 1)} per 100 moves. You simply don't give your opponents free points.")
        why_you.append("Your accuracy is consistently clean. You play the kind of solid, precise chess that wears opponents down over time.")
        if collapses == 0:
            why_you.append("You've never collapsed from a winning position. When you're ahead, you stay ahead.")
    elif pid == "the_grinder":
        why_you.append("Your endgame accuracy is significantly better than your opening and middlegame. When pieces come off the board, you're in your element.")
        why_you.append("You convert advantages in simplified positions where other players stumble. The endgame is your home.")
    elif pid == "the_speedster":
        why_you.append(f"You perform best in {best_tc_category} — fast time controls bring out your best chess.")
        if tp_blunder_ratio is not None:
            why_you.append(f"Your time-pressure blunder ratio is just {round(tp_blunder_ratio * 100, 1)}%. While others panic with seconds left, you stay sharp.")
    elif pid == "the_scientist":
        why_you.append(f"Your best-move rate of {round(best_rate, 1)}% is exceptionally high. You treat each position with methodical precision.")
        why_you.append("Your game-to-game consistency is impressive — you rarely have wild swings. You play at a steady, high level match after match.")
    elif pid == "the_assassin":
        upset_pct = round(upsets / max(total_games, 1) * 100, 1)
        why_you.append(f"You've beaten higher-rated opponents {upsets} times ({upset_pct}% of games). You don't just compete against stronger players — you beat them.")
        why_you.append("Most players wilt against higher-rated opposition. You elevate.")
    elif pid == "the_chameleon":
        why_you.append("Your skill balance is remarkably even. No phase is dramatically weaker than another — you're dangerous everywhere.")
        why_you.append("You play with similar accuracy whether it's move 5 or move 50. That kind of balance is rare and hard to play against.")
    elif pid == "the_berserker":
        why_you.append(f"Only {draw_rate}% of your games end in draws. Your record of {wins}W / {draws}D / {losses}L tells the story — every game is a fight to the death.")
        if cpl_stddev > 20:
            why_you.append("Your game-to-game variance is high. Some games are brilliant, some are explosive — but they're never boring. You play chess like a contact sport.")
    elif pid == "the_professor":
        why_you.append("Your opening accuracy is significantly stronger than your middlegame and endgame. You start games with a preparation edge that other players at your level simply don't have.")
        why_you.append("You enter the middlegame with a reliable advantage before the real fight begins — that's a massive asset.")
    elif pid == "the_survivor":
        why_you.append(f"Your blunder rate of just {round(blunder_rate, 1)} per 100 moves shows exceptional composure. You rarely make the worst move.")
        why_you.append("Your consistency is rock solid — your opponents can never count on you to crack. You're the kind of player who grinds people down just by not making mistakes.")
    elif pid == "the_adventurer":
        why_you.append(f"Your recent games show a {trend} trend. With {total_games} games analyzed, your chess identity is still forming.")
        why_you.append("The patterns are there but still emerging. Every game adds new data to the picture of who you are as a player.")

    # Always add at least one general stat-based reason
    if not why_you:
        why_you.append(f"Based on {analyzed_count} analyzed games, your metrics point clearly toward the {primary['name']} archetype.")

    # ── "Your Chess Story" — narrative paragraph weaving stats together ──
    # Build a personalized multi-sentence narrative
    story_parts = []

    # Opening
    if opening_cpl < 30:
        story_parts.append("Your openings are a real strength. You come out of the first 15 moves in good shape more often than not, which means you're rarely playing catch-up.")
    elif opening_cpl < 50:
        story_parts.append("Your openings are solid — you're not giving away the game early. But there's room to build a bigger edge from the start. A little preparation would go a long way.")
    else:
        story_parts.append("Your games often start on the back foot. You're frequently conceding ground in the first 15 moves, which means the rest of the game is spent trying to recover.")

    # Middlegame
    if middlegame_cpl < opening_cpl and middlegame_cpl < endgame_cpl:
        story_parts.append("The middlegame is where you come alive. When the position gets complex, your calculation and pattern recognition kick in — it's clearly your strongest phase.")
    elif middlegame_cpl > avg_cpl * 1.2:
        story_parts.append("The middlegame is where things get complicated for you. When positions get complex, the number of possibilities tends to overwhelm your calculation. This is where most of your accuracy drops.")
    else:
        story_parts.append("In the middlegame, you hold your own. It's neither your strongest nor weakest phase — you navigate complex positions reasonably well.")

    # Endgame
    if endgame_cpl < opening_cpl and endgame_cpl < middlegame_cpl:
        story_parts.append("And when the pieces come off? That's when you're at your best. You convert advantages that other players would fumble — the endgame is clearly your strongest phase.")
    elif endgame_cpl > avg_cpl * 1.3:
        story_parts.append("But the endgame is where wins slip away. When the position simplifies, you lose accuracy — and that means games you've already won at the board are escaping.")
    else:
        story_parts.append("Your endgame play is respectable. You can convert clear advantages, though the trickier endgames still give you trouble.")

    # Decisive nature
    if draw_rate < 5:
        story_parts.append(f"What's striking is how decisive your games are: only {draws} draws out of {total_games} games. You play to win or go down fighting — there's no in-between.")
    elif draw_rate < 15:
        story_parts.append(f"With a draw rate of {draw_rate}%, your games are more decisive than average — you tend to push for a result rather than settle.")

    # Comebacks / resilience
    if comeback_wins >= 5:
        story_parts.append(f"Perhaps most remarkably, you've won {comeback_wins} games from clearly losing positions (down 2+ pawns). This isn't luck — it's a pattern. You create chaos when you're behind, and your opponents break under the pressure.")
    elif comeback_wins >= 2:
        story_parts.append(f"You've also shown resilience, pulling off {comeback_wins} comeback wins from losing positions.")

    # Collapses
    if collapses >= 5:
        story_parts.append(f"On the flip side, you've also collapsed from winning positions {collapses} times. The ability to fight back is there — but the ability to close out won games still needs work.")
    elif collapses >= 2:
        story_parts.append(f"You've lost {collapses} games from winning positions, suggesting that converting advantages is an area to watch.")

    # Upsets
    if upsets >= 5:
        story_parts.append(f"Against higher-rated opponents, you're a genuine threat — {upsets} giant kills show you rise to the challenge when facing stronger players.")

    chess_story = " ".join(story_parts)

    # ── "Behavioral Tendencies" — patterns derived from metrics ──
    tendencies = []

    if draw_rate < 5:
        tendencies.append({
            "label": "All or Nothing",
            "icon": "⚔️",
            "description": f"Only {draw_rate}% draws — you play for a decisive result every game.",
        })
    elif draw_rate < 10:
        tendencies.append({
            "label": "Decisive",
            "icon": "🎯",
            "description": f"Low draw rate ({draw_rate}%) — you push for results rather than accepting equality.",
        })

    if comeback_wins >= 3:
        tendencies.append({
            "label": "Never Says Die",
            "icon": "🔥",
            "description": f"{comeback_wins} comeback wins — you refuse to accept a lost position.",
        })

    if blunder_rate > 3:
        tendencies.append({
            "label": "Volatile",
            "icon": "🎢",
            "description": f"{round(blunder_rate, 1)} blunders per 100 moves — you play exciting but error-prone chess.",
        })
    elif blunder_rate < 1:
        tendencies.append({
            "label": "Rock Solid",
            "icon": "🪨",
            "description": f"Only {round(blunder_rate, 1)} blunders per 100 moves — your opponents can't count on you to crack.",
        })

    if cpl_stddev > 25:
        tendencies.append({
            "label": "Streaky",
            "icon": "📊",
            "description": f"Your game quality varies significantly (±{round(cpl_stddev, 1)} CPL). Brilliant one game, shaky the next.",
        })
    elif cpl_stddev < 10:
        tendencies.append({
            "label": "Metronome",
            "icon": "⏱️",
            "description": f"Extremely consistent play (±{round(cpl_stddev, 1)} CPL variance). You deliver the same level every game.",
        })

    if upsets >= 3:
        tendencies.append({
            "label": "Giant Killer",
            "icon": "🗡️",
            "description": f"{upsets} wins vs higher-rated — you play up, not down.",
        })

    if best_rate > 45:
        tendencies.append({
            "label": "Engine-Like",
            "icon": "🤖",
            "description": f"{round(best_rate, 1)}% best moves — you find the top move with exceptional frequency.",
        })

    if collapses >= 3 and collapses > comeback_wins:
        tendencies.append({
            "label": "Closer Problem",
            "icon": "📉",
            "description": f"Collapsed {collapses} times from winning — the finish line is your biggest obstacle.",
        })

    # ── Phase breakdown with personalized commentary ──
    # Phase-normalize CPL: endgame positions are inherently more critical
    # (fewer pieces = each move matters more), so raw CPL is biased.
    # Apply normalization factors based on chess statistics research.
    PHASE_CPL_NORMALIZERS = {"opening": 1.0, "middlegame": 1.0, "endgame": 0.7}
    norm_opening_cpl = opening_cpl * PHASE_CPL_NORMALIZERS["opening"]
    norm_middlegame_cpl = middlegame_cpl * PHASE_CPL_NORMALIZERS["middlegame"]
    norm_endgame_cpl = endgame_cpl * PHASE_CPL_NORMALIZERS["endgame"]

    norm_phase_cpls = {"opening": norm_opening_cpl, "middlegame": norm_middlegame_cpl, "endgame": norm_endgame_cpl}
    best_phase = min(norm_phase_cpls, key=norm_phase_cpls.get)
    worst_phase = max(norm_phase_cpls, key=norm_phase_cpls.get)

    phase_breakdown = []
    for phase_name, cpl_val in [("Opening", opening_cpl), ("Middlegame", middlegame_cpl), ("Endgame", endgame_cpl)]:
        norm_cpl = cpl_val * PHASE_CPL_NORMALIZERS[phase_name.lower()]
        score_val = cpl_to_score(norm_cpl)
        is_best = phase_name.lower() == best_phase
        is_worst = phase_name.lower() == worst_phase

        if is_best:
            tag = "strongest"
            commentary = f"This is where you're at your best. You play this phase with real authority."
        elif is_worst and norm_cpl > avg_cpl * 1.2:
            tag = "weakest"
            commentary = f"Your biggest vulnerability. This phase is dragging your overall performance down significantly."
        elif is_worst:
            tag = "weakest"
            commentary = f"Relatively weaker than your other phases, but not critical."
        else:
            tag = "neutral"
            commentary = f"Solid performance — neither a standout strength nor a weakness."

        phase_breakdown.append({
            "phase": phase_name,
            "cpl": round(norm_cpl, 1),
            "score": score_val,
            "tag": tag,
            "commentary": commentary,
        })

    # ── Growth path — hyper-specific, data-driven advice ──
    # First, gather detailed blunder data for specificity
    growth_steps = []

    # ── Query: which piece do you blunder most? ──
    piece_blunder_q = (
        select(
            MoveEvaluation.piece,
            func.count().label("cnt"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
        )
        .group_by(MoveEvaluation.piece)
        .order_by(func.count().desc())
    )
    piece_blunder_rows = (await db.execute(piece_blunder_q)).all()
    piece_names = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}
    top_blunder_piece = None
    top_blunder_piece_count = 0
    top_blunder_piece_pct = 0
    if piece_blunder_rows and total_blunders > 0:
        top_blunder_piece = piece_blunder_rows[0].piece
        top_blunder_piece_count = piece_blunder_rows[0].cnt
        top_blunder_piece_pct = round(top_blunder_piece_count / total_blunders * 100)

    # ── Query: which phase has the most blunders? ──
    phase_blunder_q = (
        select(
            MoveEvaluation.phase,
            func.count().label("cnt"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.phase.isnot(None),
        )
        .group_by(MoveEvaluation.phase)
        .order_by(func.count().desc())
    )
    phase_blunder_rows = (await db.execute(phase_blunder_q)).all()
    top_blunder_phase = None
    top_blunder_phase_count = 0
    if phase_blunder_rows and total_blunders > 0:
        top_blunder_phase = phase_blunder_rows[0].phase
        top_blunder_phase_count = phase_blunder_rows[0].cnt

    # ── Query: top blunder subtypes with full distribution ──
    subtype_q = (
        select(
            MoveEvaluation.blunder_subtype,
            func.count().label("cnt"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.blunder_subtype.isnot(None),
        )
        .group_by(MoveEvaluation.blunder_subtype)
        .order_by(func.count().desc())
    )
    subtype_rows = (await db.execute(subtype_q)).all()
    subtypes_with_count = total_blunders if total_blunders > 0 else 1
    top_subtype = None
    top_subtype_count = 0
    top_subtype_pct = 0
    if subtype_rows:
        top_subtype = subtype_rows[0].blunder_subtype
        top_subtype_count = subtype_rows[0].cnt
        top_subtype_pct = round(top_subtype_count / subtypes_with_count * 100)

    # ── Query: average cp_loss of blunders (how costly are they?) ──
    blunder_severity_q = (
        select(
            func.avg(MoveEvaluation.cp_loss).label("avg_loss"),
            func.max(MoveEvaluation.cp_loss).label("max_loss"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.cp_loss.isnot(None),
        )
    )
    severity_row = (await db.execute(blunder_severity_q)).one_or_none()
    avg_blunder_loss = severity_row.avg_loss if severity_row and severity_row.avg_loss else 0
    max_blunder_loss = severity_row.max_loss if severity_row and severity_row.max_loss else 0

    # ── Query: blunders under time pressure vs with time ──
    tp_blunder_q2 = (
        select(
            func.sum(case((MoveEvaluation.time_remaining < 30, 1), else_=0)).label("under_pressure"),
            func.sum(case((MoveEvaluation.time_remaining >= 30, 1), else_=0)).label("with_time"),
            func.count().label("total_with_clock"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(
            Game.user_id == user.id,
            MoveEvaluation.move_quality == "Blunder",
            MoveEvaluation.time_remaining.isnot(None),
        )
    )
    tp2_row = (await db.execute(tp_blunder_q2)).one_or_none()
    tp_blunders = (tp2_row.under_pressure or 0) if tp2_row else 0
    calm_blunders = (tp2_row.with_time or 0) if tp2_row else 0
    tp_total = (tp2_row.total_with_clock or 0) if tp2_row else 0
    tp_pct = round(tp_blunders / tp_total * 100) if tp_total > 0 else 0

    # ── Now build the growth steps with real data ──

    # 1. Worst phase with specific guidance
    if worst_phase == "endgame" and endgame_cpl > avg_cpl * 1.15:
        eg_blunders = next((r.cnt for r in phase_blunder_rows if r.phase and r.phase.lower() == "endgame"), 0)
        eg_piece = ""
        # Get the most-blundered piece in endgames specifically
        eg_piece_q = (
            select(MoveEvaluation.piece, func.count().label("cnt"))
            .join(Game, Game.id == MoveEvaluation.game_id)
            .where(
                Game.user_id == user.id,
                MoveEvaluation.move_quality == "Blunder",
                MoveEvaluation.phase.ilike("endgame"),
            )
            .group_by(MoveEvaluation.piece)
            .order_by(func.count().desc())
            .limit(1)
        )
        eg_piece_row = (await db.execute(eg_piece_q)).first()
        if eg_piece_row:
            eg_piece = piece_names.get(eg_piece_row.piece, eg_piece_row.piece)
        desc = f"Your endgame CPL of {round(endgame_cpl, 1)} is {round(endgame_cpl - avg_cpl, 1)} points worse than your average."
        if eg_blunders > 0:
            desc += f" You've made {eg_blunders} blunders in the endgame"
            if eg_piece:
                desc += f", most often with your {eg_piece}"
            desc += "."
        if endgame_cpl > 80:
            desc += " Focus on King and Pawn endings first — know when to push vs when to blockade. Then Rook endings: the Lucena and Philidor positions will save you 2-3 games a month."
        else:
            desc += " You're not far off — study Rook endgame technique and practice converting 1-pawn advantages. That's where your points are hiding."
        growth_steps.append({"priority": "high", "title": "Shore Up Your Endgame", "description": desc})

    elif worst_phase == "opening" and opening_cpl > avg_cpl * 1.15:
        op_blunders = next((r.cnt for r in phase_blunder_rows if r.phase and r.phase.lower() == "opening"), 0)
        desc = f"Your opening CPL of {round(opening_cpl, 1)} means you're starting at a disadvantage before the real fight begins."
        if op_blunders > 0:
            desc += f" You've blundered {op_blunders} times in the first 15 moves — these are the easiest errors to eliminate because openings are memorizable."
        desc += " Pick ONE opening as White (e.g., London System or Italian) and ONE as Black (e.g., Caro-Kann or Scandinavian). Learn them to move 12. Don't try to learn 5 openings — own 2."
        growth_steps.append({"priority": "high", "title": "Deepen Your Opening Preparation", "description": desc})

    elif worst_phase == "middlegame" and middlegame_cpl > avg_cpl * 1.15:
        mg_blunders = next((r.cnt for r in phase_blunder_rows if r.phase and r.phase.lower() == "middlegame"), 0)
        desc = f"Your middlegame CPL of {round(middlegame_cpl, 1)} is where your accuracy drops most."
        if mg_blunders > 0 and top_blunder_piece:
            desc += f" {mg_blunders} of your {total_blunders} blunders happen in the middlegame, often involving your {piece_names.get(top_blunder_piece, top_blunder_piece)}."
        desc += " Train tactics for 15 min/day on Lichess puzzles — focus on the themes you fail most (forks, pins, discovered attacks). The middlegame is pattern recognition, and patterns are trainable."
        growth_steps.append({"priority": "high", "title": "Sharpen Your Middlegame Calculation", "description": desc})

    # 2. Blunder-specific advice — now with WHAT you're blundering
    if blunder_rate > 2.5 and total_blunders >= 5:
        desc = f"You've made {total_blunders} blunders across {analyzed_count} games ({round(blunder_rate, 1)} per 100 moves)."

        # What kind of blunders?
        subtype_detail = ""
        if top_subtype and top_subtype_pct > 30:
            subtype_labels = {
                "hanging_piece": "leaving pieces undefended",
                "missed_tactic": "missing tactical shots",
                "king_safety": "king safety oversights",
                "endgame_technique": "endgame technique errors",
            }
            subtype_label = subtype_labels.get(top_subtype, top_subtype.replace("_", " "))
            subtype_detail = f" {top_subtype_pct}% of your blunders are {subtype_label}"
            if top_subtype == "hanging_piece":
                subtype_detail += " — before every move, scan the board: is anything undefended? Can my opponent capture something? This 3-second habit eliminates the most common blunder type."
            elif top_subtype == "missed_tactic":
                subtype_detail += " — you're missing forcing moves your opponent has. Train 'find the threat' puzzles: before your move, ask 'what does my opponent WANT to play?'"
            elif top_subtype == "king_safety":
                subtype_detail += " — your king is getting caught. Before committing to an attack, check: is MY king safe first? Castle early, don't push pawns in front of your king."
            elif top_subtype == "endgame_technique":
                subtype_detail += " — you know enough to reach endgames but not enough to play them. Study the 5 essential positions: Lucena, Philidor, opposition, king and pawn, and queen vs pawn."
            else:
                subtype_detail += "."
            desc += subtype_detail

        # Which piece?
        elif top_blunder_piece and top_blunder_piece_pct > 25:
            pname = piece_names.get(top_blunder_piece, top_blunder_piece)
            desc += f" {top_blunder_piece_pct}% involve your {pname}."
            if top_blunder_piece in ("Q", "R"):
                desc += f" Your heavy pieces are your most expensive mistakes — before moving your {pname}, ask: is this square actually safe? Can I be forked? Is there a discovered attack?"
            elif top_blunder_piece in ("N", "B"):
                desc += f" You're losing minor pieces to tactical oversights. Check for forks and pins before committing your {pname} to a square."
            else:
                desc += f" Pay special attention to {pname} safety in complex positions."

        # Time pressure angle?
        if tp_pct > 50 and tp_total >= 5:
            desc += f" {tp_pct}% of your blunders happen with less than 30 seconds on the clock — time management is a factor. Leave at least 1 minute for the last 10 moves."
        elif tp_pct < 30 and tp_total >= 5:
            desc += f" Only {tp_pct}% of your blunders are under time pressure — these are calculation errors, not speed errors. Slow down even when you have time."

        # Severity
        if avg_blunder_loss > 400:
            desc += f" Your average blunder costs {round(avg_blunder_loss)} centipawns (≈{round(avg_blunder_loss / 100, 1)} pawns) — these aren't small inaccuracies, they're game-ending mistakes. Focus on eliminating the catastrophic ones first."

        growth_steps.append({"priority": "high", "title": f"Stop Blundering Your {piece_names.get(top_blunder_piece, 'Pieces')}" if top_blunder_piece and top_blunder_piece_pct > 30 else "Cut Your Blunder Rate", "description": desc})

    # 3. Conversion / collapse advice — with specifics
    if collapses >= 3:
        collapse_pct = round(collapses / max(losses, 1) * 100)
        desc = f"You've collapsed from winning positions {collapses} times — that's {collapse_pct}% of your losses."
        if worst_phase == "endgame" or endgame_cpl > middlegame_cpl * 1.2:
            desc += f" Most collapses happen when the position simplifies and your endgame accuracy ({round(endgame_cpl, 1)} CPL) can't sustain the advantage. When you're winning and pieces are trading off, this is your danger zone."
            desc += " Practice converting a +2 advantage in Rook endgames until it's automatic."
        else:
            desc += " When you're ahead, switch gears: stop looking for the best move and start looking for the SAFEST good move. Trade pieces, simplify, and remove your opponent's counterplay."
        growth_steps.append({"priority": "medium", "title": "Close Out Won Games", "description": desc})

    # 4. Consistency — with specific data, not vague
    if cpl_stddev > 25:
        # Find games with wildly different CPLs to illustrate the spread
        desc = f"Your game-to-game accuracy swings by ±{round(cpl_stddev, 1)} CPL."
        if tp_pct > 50 and tp_total >= 5:
            desc += f" {tp_pct}% of your blunders happen under time pressure — your inconsistency is partly a clock management problem. Try allocating your time more evenly: don't spend 5 minutes on move 10 and then have 30 seconds for move 35."
        elif blunder_rate > 3:
            desc += f" With {round(blunder_rate, 1)} blunders per 100 moves, individual catastrophic errors are creating the swings. The fix isn't 'try harder' — it's building a pre-move checklist: (1) what does my opponent threaten? (2) is my piece safe on that square? (3) does this create any tactics?"
        else:
            desc += " Your best games are already strong — the gap is between your focused play and your unfocused play. Identifying WHEN you lose focus (after a mistake? in equal positions? when ahead?) is the key."
        growth_steps.append({"priority": "medium", "title": "Close the Gap Between Your Best and Worst", "description": desc})

    # 5. Persona-specific growth — with specific data
    if pid == "the_phoenix":
        comeback_pct = round(comeback_wins / max(total_games, 1) * 100, 1)
        desc = f"You've fought back from losing positions {comeback_wins} times ({comeback_pct}% of games) — that's a genuine skill."
        if blunder_rate > 2:
            desc += f" But your blunder rate of {round(blunder_rate, 1)}/100 means you're creating the losing positions you then have to escape. Cut your blunders by even 30% and you'll spend more games pressing advantages instead of manufacturing comebacks."
        else:
            desc += " The next level is needing comebacks less often — not because you can't do them, but because you're ahead more from the start."
        growth_steps.append({"priority": "medium", "title": "Win Without the Drama", "description": desc})
    elif pid == "the_berserker":
        desc = f"Your {draw_rate}% draw rate shows you fight every game to the death — that's part of your identity."
        if collapses >= 2:
            desc += f" But {collapses} collapses from winning positions means your aggression is sometimes self-destructive. Learn to recognize when the position calls for consolidation: trade a pair of pieces, secure your king, THEN attack."
        else:
            desc += " To level up, learn to switch gears. Some positions demand patience — recognizing those moments and playing quietly for 3-4 moves before striking is what separates berserkers from titled players."
        growth_steps.append({"priority": "medium", "title": "Channel Your Aggression", "description": desc})
    elif pid == "the_chameleon":
        phase_range_val = max(opening_cpl, middlegame_cpl, endgame_cpl) - min(opening_cpl, middlegame_cpl, endgame_cpl)
        desc = f"Your phase CPL range is only {round(phase_range_val, 1)} — you're equally capable everywhere. That's rare."
        if best_rate < 35:
            desc += f" But your best-move rate of {round(best_rate, 1)}% suggests your 'equal everywhere' is 'average everywhere.' Pick the phase you enjoy most and push it to elite level. A balanced player with one weapon becomes unpredictable."
        else:
            desc += " Your edge is that opponents can't target a weak phase. Double down on this by studying universal principles — piece activity, pawn structure, prophylaxis — that improve ALL phases at once."
        growth_steps.append({"priority": "medium", "title": "Add a Specialty to Your Versatility", "description": desc})

    # 6. Final step — specific, not generic
    if analyzed_count < total_games * 0.5 and total_games >= 10:
        growth_steps.append({
            "priority": "low",
            "title": "Analyze More of Your Games",
            "description": f"You've only analyzed {analyzed_count} of your {total_games} games ({round(analyzed_count / total_games * 100)}%). Every unanalyzed game is a missed lesson. Analyze at least your losses — that's where the biggest improvements hide.",
        })
    elif best_rate > 40 and blunder_rate < 2:
        growth_steps.append({
            "priority": "low",
            "title": "Push Into Harder Territory",
            "description": f"Your fundamentals are solid — {round(best_rate, 1)}% best moves, {round(blunder_rate, 1)} blunders/100. You're past the 'stop making mistakes' phase. Study master games in your openings, learn positional concepts (weak squares, minority attacks, piece coordination), and start playing longer time controls to deepen your calculation.",
        })
    else:
        growth_steps.append({
            "priority": "low",
            "title": "Build a Post-Game Routine",
            "description": f"After every game: (1) find your worst move and understand WHY it was bad, (2) find one move where you missed a tactic, (3) check if your opening was sound. 5 minutes of targeted review beats 30 minutes of passive analysis. You have {analyzed_count} games analyzed — make each one count.",
        })

    # ── Skill axes for the radar in the identity card ──
    axes = [
        {"axis": "Opening", "score": opening_score},
        {"axis": "Middlegame", "score": middlegame_score},
        {"axis": "Endgame", "score": endgame_score},
        {"axis": "Tactics", "score": best_rate_pct},
        {"axis": "Composure", "score": composure_score},
        {"axis": "Consistency", "score": consistency_score},
    ]
    overall_score = round(sum(a["score"] for a in axes) / len(axes))

    return {
        "has_data": True,
        "persona": {
            "id": primary["id"],
            "name": primary["name"],
            "emoji": primary["emoji"],
            "tagline": primary["tagline"],
            "gm_comparison": primary["gm_comparison"],
            "description": primary["description"],
            "color": primary["color"],
        },
        "secondary_persona": {
            "id": secondary["id"],
            "name": secondary["name"],
            "emoji": secondary["emoji"],
            "tagline": secondary["tagline"],
        } if secondary else None,
        "signature_stats": signature_stats[:6],
        "kryptonite": kryptonite,
        "one_thing": one_thing,
        # Enhanced report sections
        "why_you": why_you,
        "chess_story": chess_story,
        "tendencies": tendencies[:6],
        "phase_breakdown": phase_breakdown,
        "growth_path": growth_steps[:5],
        # Skill shape
        "skill_axes": axes,
        "overall_score": overall_score,
        "analyzed_games": analyzed_count,
        "total_games": total_games,
    }


# ═══════════════════════════════════════════════════════════
# Weekly Study Plan
# ═══════════════════════════════════════════════════════════


@router.get("/study-plan")
async def get_study_plan(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a 7-day study plan based on the player's weaknesses and recent performance.
    Each day has a focus area with specific activities. Deterministic — no LLMs.
    """
    from datetime import date, timedelta

    # Gather player stats
    total_q = select(func.count()).select_from(Game).where(Game.user_id == user.id)
    total_games = (await db.execute(total_q)).scalar() or 0

    if total_games == 0:
        return {
            "week_start": date.today().isoformat(),
            "days": [],
            "message": "Analyze some games first to generate your study plan.",
        }

    # Phase CPL averages
    phase_q = select(
        func.avg(GameAnalysis.phase_opening_cpl).label("opening"),
        func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame"),
        func.avg(GameAnalysis.phase_endgame_cpl).label("endgame"),
    ).join(Game, Game.id == GameAnalysis.game_id).where(Game.user_id == user.id)
    phase_row = (await db.execute(phase_q)).one_or_none()

    opening_cpl = round(phase_row.opening or 0, 1) if phase_row else 0
    middlegame_cpl = round(phase_row.middlegame or 0, 1) if phase_row else 0
    endgame_cpl = round(phase_row.endgame or 0, 1) if phase_row else 0

    # Blunder rate
    blunder_q = select(
        func.sum(GameAnalysis.blunders_count).label("blunders"),
        func.count().label("games"),
    ).join(Game, Game.id == GameAnalysis.game_id).where(Game.user_id == user.id)
    brow = (await db.execute(blunder_q)).one_or_none()
    blunder_rate = round((brow.blunders or 0) / max(brow.games, 1), 1) if brow else 0

    # Count unsolved puzzles
    from sqlalchemy import distinct
    from app.db.models import PuzzleAttempt

    total_puzzles_q = select(func.count()).select_from(Puzzle).where(Puzzle.source_user_id == user.id)
    total_puzzles = (await db.execute(total_puzzles_q)).scalar() or 0

    # Build priority list of areas
    areas = [
        {"area": "opening", "cpl": opening_cpl, "label": "Opening Prep"},
        {"area": "middlegame", "cpl": middlegame_cpl, "label": "Middlegame Tactics"},
        {"area": "endgame", "cpl": endgame_cpl, "label": "Endgame Technique"},
    ]
    areas.sort(key=lambda a: a["cpl"], reverse=True)  # worst first

    # Activity templates
    ACTIVITIES = {
        "opening": [
            {"type": "review", "title": "Review your worst opening", "description": "Check your opening repertoire stats and study the line with the highest CPL.", "duration": 15},
            {"type": "puzzles", "title": "Opening puzzles", "description": "Solve puzzles from your opening mistakes.", "duration": 10},
        ],
        "middlegame": [
            {"type": "puzzles", "title": "Tactical training", "description": "Solve middlegame puzzles to sharpen calculation.", "duration": 15},
            {"type": "review", "title": "Analyze a loss", "description": "Review a recent loss focusing on the middlegame turning point.", "duration": 10},
        ],
        "endgame": [
            {"type": "puzzles", "title": "Endgame drills", "description": "Practice converting advantages in endgame positions.", "duration": 15},
            {"type": "review", "title": "Endgame review", "description": "Study a game where you lost the endgame despite a good position.", "duration": 10},
        ],
        "blunders": [
            {"type": "puzzles", "title": "Blunder prevention", "description": "Practice recognizing blunder-prone positions.", "duration": 10},
            {"type": "warmup", "title": "Daily warmup", "description": "Complete your 5-puzzle daily warmup.", "duration": 5},
        ],
        "intuition": [
            {"type": "intuition", "title": "Intuition training", "description": "Spot the blunder among 4 moves to sharpen pattern recognition.", "duration": 10},
        ],
        "advantage": [
            {"type": "advantage", "title": "Capitalize advantages", "description": "Practice converting winning positions that you've failed to win in the past.", "duration": 15},
        ],
    }

    # Build 7-day plan
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    days = []

    day_themes = [
        # Mon: worst area, Tue: 2nd worst, Wed: blunders, Thu: worst again,
        # Fri: intuition + advantage, Sat: 3rd area, Sun: review + warmup
        areas[0]["area"],
        areas[1]["area"] if len(areas) > 1 else areas[0]["area"],
        "blunders",
        areas[0]["area"],
        "mixed",
        areas[2]["area"] if len(areas) > 2 else areas[0]["area"],
        "review",
    ]

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for i, theme in enumerate(day_themes):
        day_date = week_start + timedelta(days=i)
        is_past = day_date < today
        is_today = day_date == today

        if theme == "mixed":
            activities = ACTIVITIES["intuition"] + ACTIVITIES["advantage"]
            label = "Pattern Recognition"
        elif theme == "review":
            activities = ACTIVITIES["blunders"] + [
                {"type": "review", "title": "Weekly review", "description": "Look at your progress charts and identify trends.", "duration": 10},
            ]
            label = "Review & Reflect"
        else:
            activities = ACTIVITIES.get(theme, ACTIVITIES["middlegame"])
            label = next((a["label"] for a in areas if a["area"] == theme), theme.title())

        total_duration = sum(a["duration"] for a in activities)

        days.append({
            "day": day_names[i],
            "date": day_date.isoformat(),
            "focus": label,
            "theme": theme,
            "is_past": is_past,
            "is_today": is_today,
            "total_duration_min": total_duration,
            "activities": activities,
        })

    return {
        "week_start": week_start.isoformat(),
        "days": days,
        "stats": {
            "opening_cpl": opening_cpl,
            "middlegame_cpl": middlegame_cpl,
            "endgame_cpl": endgame_cpl,
            "blunder_rate": blunder_rate,
            "total_puzzles": total_puzzles,
        },
    }


# ═══════════════════════════════════════════════════════════
# AI Coach Report — elo-aware, deeply personalized
# ═══════════════════════════════════════════════════════════


@router.get("/coach-report")
async def get_coach_report(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a full AI Coach Report with elo-tiered advice, training plan with CTAs,
    honest truths, and a personalized chess story. Deterministic — no LLMs.
    """

    # ── Fetch identity data (reuse the chess-identity computation) ──
    identity = await get_chess_identity(user=user, db=db)
    if not identity.get("has_data"):
        return {"has_data": False, "message": "Analyze at least 3 games to generate your coach report."}

    # ── Get player elo ──
    elo_q = (
        select(Game.player_elo)
        .where(Game.user_id == user.id, Game.player_elo.isnot(None))
        .order_by(Game.date.desc())
        .limit(1)
    )
    current_elo = (await db.execute(elo_q)).scalar()

    # Elo 30 games ago for trend
    elo_old_q = (
        select(Game.player_elo)
        .where(Game.user_id == user.id, Game.player_elo.isnot(None))
        .order_by(Game.date.desc())
        .offset(30)
        .limit(1)
    )
    old_elo = (await db.execute(elo_old_q)).scalar()
    elo_trend = (current_elo - old_elo) if current_elo and old_elo else None

    # Classify elo tier
    elo = current_elo or 0
    if elo < 1000:
        tier = "beginner"
        tier_label = "Beginner"
    elif elo < 1500:
        tier = "intermediate"
        tier_label = "Intermediate"
    elif elo < 1900:
        tier = "advanced"
        tier_label = "Advanced"
    else:
        tier = "expert"
        tier_label = "Expert"

    # ── Extract the metrics we need from the identity response ──
    persona = identity["persona"]
    phase_breakdown = identity.get("phase_breakdown", [])
    growth_path = identity.get("growth_path", [])
    kryptonite = identity.get("kryptonite")
    one_thing = identity.get("one_thing")
    chess_story = identity.get("chess_story", "")
    why_you = identity.get("why_you", [])
    tendencies = identity.get("tendencies", [])
    analyzed_games = identity.get("analyzed_games", 0)
    total_games = identity.get("total_games", 0)
    skill_axes = identity.get("skill_axes", [])
    overall_score = identity.get("overall_score", 0)

    # ── Re-query the raw metrics for the headline and honest truths ──
    agg_q = (
        select(
            func.avg(GameAnalysis.overall_cpl).label("avg_cpl"),
            func.avg(GameAnalysis.phase_opening_cpl).label("opening_cpl"),
            func.avg(GameAnalysis.phase_middlegame_cpl).label("middlegame_cpl"),
            func.avg(GameAnalysis.phase_endgame_cpl).label("endgame_cpl"),
            func.sum(GameAnalysis.blunders_count).label("total_blunders"),
            func.sum(GameAnalysis.mistakes_count).label("total_mistakes"),
            func.sum(GameAnalysis.best_moves_count).label("total_best"),
            func.sum(Game.moves_count).label("total_moves"),
        )
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id)
    )
    agg = (await db.execute(agg_q)).one()
    avg_cpl = agg.avg_cpl or 50
    opening_cpl = agg.opening_cpl or avg_cpl
    middlegame_cpl = agg.middlegame_cpl or avg_cpl
    endgame_cpl = agg.endgame_cpl or avg_cpl
    total_blunders = agg.total_blunders or 0
    total_moves = agg.total_moves or 1
    player_moves = total_moves / 2
    blunder_rate = total_blunders / player_moves * 100 if player_moves > 0 else 0
    total_best = agg.total_best or 0
    best_rate = total_best / player_moves * 100 if player_moves > 0 else 0

    # Win/loss
    results_q = (
        select(Game.result, func.count().label("cnt"))
        .where(Game.user_id == user.id)
        .group_by(Game.result)
    )
    result_rows = (await db.execute(results_q)).all()
    result_map = {r.result: r.cnt for r in result_rows}
    wins = result_map.get("win", 0)
    losses = result_map.get("loss", 0)
    draws = result_map.get("draw", 0)
    win_rate = round(wins / max(total_games, 1) * 100, 1)

    # Phase identification (with normalization for fair comparison)
    # Endgame CPL is inherently higher due to position criticality — normalize it
    PHASE_CPL_NORMALIZERS = {"opening": 1.0, "middlegame": 1.0, "endgame": 0.7}
    phase_cpls = {
        "opening": opening_cpl * PHASE_CPL_NORMALIZERS["opening"],
        "middlegame": middlegame_cpl * PHASE_CPL_NORMALIZERS["middlegame"],
        "endgame": endgame_cpl * PHASE_CPL_NORMALIZERS["endgame"],
    }
    best_phase = min(phase_cpls, key=phase_cpls.get)
    worst_phase = max(phase_cpls, key=phase_cpls.get)

    # CPL stddev
    cpl_stddev_q = (
        select(func.stddev(GameAnalysis.overall_cpl))
        .join(Game, Game.id == GameAnalysis.game_id)
        .where(Game.user_id == user.id, GameAnalysis.overall_cpl.isnot(None))
    )
    cpl_stddev = (await db.execute(cpl_stddev_q)).scalar() or 20

    # Comebacks / collapses
    comeback_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(Game.user_id == user.id, Game.result == "win",
               MoveEvaluation.eval_after.isnot(None), MoveEvaluation.eval_after < -200)
    )
    comeback_wins = (await db.execute(comeback_q)).scalar() or 0

    collapse_q = (
        select(func.count(func.distinct(MoveEvaluation.game_id)))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(Game.user_id == user.id, Game.result == "loss",
               MoveEvaluation.eval_after.isnot(None), MoveEvaluation.eval_after > 200)
    )
    collapses = (await db.execute(collapse_q)).scalar() or 0

    # Top blunder piece
    piece_blunder_q = (
        select(MoveEvaluation.piece, func.count().label("cnt"))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(Game.user_id == user.id, MoveEvaluation.move_quality == "Blunder")
        .group_by(MoveEvaluation.piece)
        .order_by(func.count().desc())
        .limit(1)
    )
    piece_names = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}
    pb_row = (await db.execute(piece_blunder_q)).first()
    top_piece = piece_names.get(pb_row.piece, pb_row.piece) if pb_row else None
    top_piece_pct = round(pb_row.cnt / max(total_blunders, 1) * 100) if pb_row else 0

    # Top blunder subtype
    subtype_q = (
        select(MoveEvaluation.blunder_subtype, func.count().label("cnt"))
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(Game.user_id == user.id, MoveEvaluation.move_quality == "Blunder",
               MoveEvaluation.blunder_subtype.isnot(None))
        .group_by(MoveEvaluation.blunder_subtype)
        .order_by(func.count().desc())
        .limit(1)
    )
    st_row = (await db.execute(subtype_q)).first()
    top_subtype = st_row.blunder_subtype if st_row else None
    subtype_labels = {
        "hanging_piece": "hanging pieces",
        "missed_fork": "missed forks",
        "missed_pin": "missed pins",
        "missed_skewer": "missed skewers",
        "missed_discovery": "missed discovered attacks",
        "missed_mate": "missed checkmates",
        "missed_capture": "missed captures",
        "back_rank": "back-rank blind spots",
        "king_safety": "king safety mistakes",
        "endgame_technique": "endgame technique errors",
        "positional": "positional misjudgments",
    }

    # Time pressure blunder %
    tp_q = (
        select(
            func.sum(case((MoveEvaluation.time_remaining < 30, 1), else_=0)).label("under_tp"),
            func.count().label("total"),
        )
        .join(Game, Game.id == MoveEvaluation.game_id)
        .where(Game.user_id == user.id, MoveEvaluation.move_quality == "Blunder",
               MoveEvaluation.time_remaining.isnot(None))
    )
    tp_row = (await db.execute(tp_q)).one_or_none()
    tp_blunders = (tp_row.under_tp or 0) if tp_row else 0
    tp_total = (tp_row.total or 0) if tp_row else 0
    tp_pct = round(tp_blunders / tp_total * 100) if tp_total > 0 else None

    # ══════════════════════════════════════════════════════
    # BUILD THE REPORT
    # ══════════════════════════════════════════════════════

    # ── 1. Headline — one punchy sentence, NO raw numbers ──
    headline = ""
    if tier == "beginner":
        if blunder_rate > 4:
            headline = f"You're a {persona['name']} who gives away too many pieces — fix that one thing and your rating jumps."
        elif worst_phase == "endgame":
            headline = f"You play good chess until the endgame, then it falls apart. That's fixable."
        else:
            headline = f"You're finding your style as a {persona['name']} — the foundation is there, now let's build on it."
    elif tier == "intermediate":
        if worst_phase == "endgame":
            headline = f"You're a {persona['name']} who plays well in the opening but struggles to close games. That gap is where your rating is stuck."
        elif blunder_rate > 3:
            headline = f"You're strong enough to build good positions but you give them away too often. Your blunder habit is the single biggest thing holding you back."
        else:
            headline = f"You're a solid {persona['name']} — the next jump is hiding in your {worst_phase}."
    elif tier == "advanced":
        if cpl_stddev > 25:
            headline = f"Your best games are impressive, but your worst games are far below your level. Consistency is your ceiling right now."
        elif collapses >= 3:
            headline = f"You build winning positions like a much stronger player and then let them slip. Conversion is your bottleneck."
        else:
            headline = f"You're a {persona['name']} ready for the next level — sharpen your {worst_phase} and tighten your consistency."
    else:  # expert
        if cpl_stddev > 20:
            headline = f"Your ceiling is high but your floor is inconsistent. On the days you play like yourself, you're dangerous."
        else:
            headline = f"You're a refined {persona['name']}. The gains from here are surgical — specific preparation and eliminating your last blind spots."

    # ── 2. Honest Truths — blunt, human-language observations ──
    honest_truths = []

    # Phase imbalance
    phase_gap = round(phase_cpls[worst_phase] - phase_cpls[best_phase], 1)
    if phase_gap > 20:
        honest_truths.append({
            "icon": "📊",
            "text": f"You play like two different people. Your {best_phase} is genuinely strong, but your {worst_phase} is a completely different level. That gap is costing you games you should be winning.",
            "cta_label": f"Train {worst_phase.title()}",
            "cta_url": f"/train?phase={worst_phase}",
        })

    # Blunder piece
    if top_piece and top_piece_pct > 25 and total_blunders >= 5:
        honest_truths.append({
            "icon": "♟️",
            "text": f"You have a specific blind spot with your {top_piece}. A disproportionate number of your blunders involve this piece — it's not random, it's a pattern worth studying.",
            "cta_label": "Practice Your Blunders",
            "cta_url": "/train?mode=warmup",
        })

    # Blunder type
    if top_subtype and st_row and st_row.cnt >= 3:
        # Map subtype to a tactic filter
        _subtype_tactic_map = {
            "missed_fork": "fork", "missed_pin": "pin", "missed_skewer": "skewer",
            "missed_discovery": "discovered_attack", "back_rank": "back_rank",
            "missed_mate": "checkmate_pattern", "king_safety": "king_activity",
        }
        truth_tactic = _subtype_tactic_map.get(top_subtype)
        honest_truths.append({
            "icon": "🔍",
            "text": f"Your number one blunder pattern is {subtype_labels.get(top_subtype, top_subtype.replace('_', ' '))}. This keeps showing up in your games — it's a trainable habit, not bad luck.",
            "cta_label": f"Train {subtype_labels.get(top_subtype, 'This Pattern').rstrip('s').title()}s" if truth_tactic else "Practice Puzzles",
            "cta_url": f"/train?tactic={truth_tactic}" if truth_tactic else "/train",
        })

    # Collapses
    if collapses >= 3:
        honest_truths.append({
            "icon": "📉",
            "text": f"You've thrown away multiple won games. You're not losing because you're outplayed — you're losing positions you've already earned. This is the most fixable problem you have.",
            "cta_label": "Practice Converting",
            "cta_url": "/train?mode=advantage",
        })

    # Time pressure
    if tp_pct is not None and tp_pct > 50 and tp_total >= 5:
        honest_truths.append({
            "icon": "⏰",
            "text": f"Most of your blunders happen in time trouble. You're not a bad calculator — you're a bad time manager. The clock is beating you, not your opponents.",
            "cta_label": "Timed Puzzle Sprint",
            "cta_url": "/train?mode=timed",
        })

    # Consistency
    if cpl_stddev > 30:
        honest_truths.append({
            "icon": "🎢",
            "text": f"Your accuracy swings wildly between games. On your good days, you're genuinely dangerous. On your bad days, you play far below your ability. Closing that gap IS your rating gain.",
            "cta_label": "Daily Warmup",
            "cta_url": "/train?mode=warmup",
        })

    # Limit to 3 most impactful
    honest_truths = honest_truths[:3]

    # If we couldn't find blunt truths, add a general one
    if not honest_truths:
        honest_truths.append({
            "icon": "📋",
            "text": f"You're playing solid chess across {analyzed_games} analyzed games. The gains from here are about refinement, not revolution.",
        })

    # ── 3. Phase report — elo-calibrated commentary in HUMAN language ──
    phase_report = []
    for pb in phase_breakdown:
        phase_name = pb["phase"].lower()
        cpl_val = pb["cpl"]
        score_val = pb["score"]
        tag = pb["tag"]

        # Elo-aware commentary — human voice, no raw numbers
        if tier == "beginner":
            if phase_name == "opening":
                if cpl_val < 40:
                    commentary = "Your opening is actually decent — don't stress about memorizing lines. Just keep developing pieces, controlling the center, and castling early. That's all you need right now."
                else:
                    commentary = "You're losing accuracy early. Don't memorize openings yet — just follow three rules: control the center with pawns, develop knights before bishops, and castle before move 10. That alone will make a big difference."
            elif phase_name == "middlegame":
                if cpl_val > 60:
                    commentary = "You're making expensive decisions in complex positions. Before every move, ask ONE question: 'can my opponent take something if I play this?' That single habit will cut your errors dramatically."
                else:
                    commentary = "Your middlegame is reasonable. Keep practicing tactical puzzles — forks, pins, and skewers are the patterns that matter most at your level."
            else:  # endgame
                if cpl_val > 50:
                    commentary = "Your endgame needs the most work. Learn just TWO things: activate your King — push it to the center, and passed pawns must be pushed. These two principles alone will transform your endgames."
                else:
                    commentary = "Your endgame is okay. When pieces come off the board, remember: your King becomes a fighting piece. Push it forward."
        elif tier == "intermediate":
            if phase_name == "opening":
                if cpl_val > 50:
                    commentary = "You're consistently coming out of the opening worse. Pick ONE system as White and ONE as Black — learn them deeply to move 12. Own two openings well instead of five superficially."
                elif cpl_val < 25:
                    commentary = "Your opening prep is a genuine strength. You're getting good positions out of the gate — now make sure you don't waste that advantage in the middlegame."
                else:
                    commentary = "Your opening is fine — not losing you games, not winning them either. At your level this is acceptable. Focus your study time elsewhere."
            elif phase_name == "middlegame":
                if cpl_val > 55:
                    commentary = "The middlegame is where your games get complicated and your accuracy drops. This is a calculation problem. Do daily tactical puzzles — not easy ones, ones that take you 2-3 minutes to solve. Build the muscle."
                else:
                    commentary = "Your middlegame calculation is solid for your rating. Start thinking about positional concepts: weak squares, piece activity, and when to trade."
            else:
                if cpl_val > 42:
                    commentary = "Your endgame is where wins become draws and draws become losses. Learn these specifically: the Lucena position, the Philidor position, King opposition, and when to trade into pawn endgames. Those four concepts cover most practical endgames."
                else:
                    commentary = "Your endgame is decent. Practice converting advantages — when you're up a pawn, you should be winning those games consistently."
        elif tier == "advanced":
            if phase_name == "opening":
                if cpl_val > 40:
                    commentary = "Your opening accuracy is below where it should be at your level. You're likely playing lines you don't fully understand. Audit your repertoire — which openings have the worst results? Cut what doesn't work and deepen what does."
                else:
                    commentary = "Your opening preparation is strong. At this level, marginal gains come from understanding the PLANS after the opening, not memorizing more theory."
            elif phase_name == "middlegame":
                if cpl_val > 50:
                    commentary = "Your middlegame is your growth area. At your level, this usually means you're tactically sharp but strategically uncertain. Study annotated GM games — focus on how they choose plans, not just moves."
                else:
                    commentary = "Your middlegame is competitive for your rating. Push further by studying your specific opening structures — understand the typical plans, piece placements, and pawn breaks."
            else:
                if cpl_val > 35:
                    commentary = "Your endgame technique is the gap between you and the next level. This is where improving players get stuck. Do targeted endgame practice — not just puzzles, but playing out positions against an engine."
                else:
                    commentary = "Your endgame is strong. Focus on the complex ones: rook + pawn vs rook, bishop vs knight, and opposite-colored bishop endgames."
        else:  # expert
            if phase_name == "opening":
                commentary = "At your level, openings should be near-automatic. Any opening that consistently gives you trouble is worth auditing. Consider building a preparation database for your main lines."
            elif phase_name == "middlegame":
                commentary = "Your middlegame is where the subtle gains are. Study your losses with an engine — find the moments where you chose a reasonable move but there was a much stronger one. Those 'not-quite-right' decisions are your growth edge."
            else:
                commentary = "If your endgame is weaker than your middlegame, it's likely in complex positions with multiple pieces. Study practical rook endgames and conversion technique from real games."

        phase_report.append({
            "phase": pb["phase"],
            "cpl": cpl_val,
            "score": score_val,
            "tag": tag,
            "commentary": commentary,
            "cta_label": f"Train {pb['phase']}" if tag == "weakest" else None,
            "cta_url": f"/train?phase={phase_name}" if tag == "weakest" else None,
        })

    # ── 4. Training plan — actionable with CTA links, human voice ──
    training_plan = []

    # The most impactful training action based on tier + data
    if tier == "beginner":
        # Beginners: principles first, not tactics
        if blunder_rate > 4:
            training_plan.append({
                "title": "Daily Blunder Check Practice",
                "why": "You're giving away pieces too often. At your level, just NOT hanging pieces would win you more games than anything else.",
                "how": "Before every move in your games, count your opponent's attacks. Start with the Blunder Preventer trainer to build the habit.",
                "cta_label": "Start Blunder Preventer",
                "cta_url": "/train?mode=warmup",
            })
        training_plan.append({
            "title": "5 Puzzles a Day — No More, No Less",
            "why": "Pattern recognition is how your brain learns chess. A few puzzles daily is better than a marathon once a week.",
            "how": "Do the Daily Warmup every day. Don't rush — if a puzzle takes 3 minutes, that's fine. The goal is accuracy, not speed.",
            "cta_label": "Start Daily Warmup",
            "cta_url": "/train?mode=warmup",
        })
        if worst_phase == "endgame":
            training_plan.append({
                "title": "Learn 2 Endgame Rules",
                "why": "Your endgame is dragging down your results. You don't need theory — you need two rules.",
                "how": "Rule 1: In the endgame, your King is a fighting piece — push it to the center. Rule 2: Passed pawns must be pushed. Practice endgame puzzles to internalize these.",
                "cta_label": "Practice Endgames",
                "cta_url": "/train?phase=endgame",
            })
    elif tier == "intermediate":
        # Intermediates: targeted weakness training
        if worst_phase == "endgame":
            training_plan.append({
                "title": "Endgame Conversion Training",
                "why": "Your endgame is your biggest weakness. You build good positions but can't finish them off.",
                "how": "Use the 'Capitalize Advantages' trainer — it gives you positions from YOUR games where you were winning but failed to convert. Practice until you can win these consistently.",
                "cta_label": "Capitalize Advantages",
                "cta_url": "/train?mode=advantage",
            })
        if blunder_rate > 2.5:
            piece_note = f" You have a specific blind spot with your {top_piece}." if top_piece and top_piece_pct > 30 else ""
            subtype_note = f" Your main pattern: {subtype_labels.get(top_subtype, '')}." if top_subtype else ""
            training_plan.append({
                "title": f"Fix Your {top_piece + ' ' if top_piece and top_piece_pct > 30 else ''}Blunders",
                "why": f"You're blundering too often for your level.{piece_note}{subtype_note}",
                "how": "Do the Blunder Preventer daily. Then review your blunders from recent games — you'll start seeing the same patterns.",
                "cta_label": "Blunder Preventer",
                "cta_url": "/train?mode=warmup",
            })
        # Add tactic-specific training if we have a top blunder subtype
        if top_subtype and top_subtype.startswith("missed_"):
            tactic_name = top_subtype.replace("missed_", "")
            training_plan.append({
                "title": f"Train Your {tactic_name.replace('_', ' ').title()} Vision",
                "why": f"You keep missing {subtype_labels.get(top_subtype, tactic_name + 's')} in your games. This is a pattern recognition problem — solvable with targeted practice.",
                "how": f"Do puzzles specifically tagged with {tactic_name.replace('_', ' ')} themes. Your brain will start spotting these patterns automatically.",
                "cta_label": f"Train {tactic_name.replace('_', ' ').title()}s",
                "cta_url": f"/train?tactic={tactic_name}",
            })
        else:
            training_plan.append({
                "title": "Tactical Pattern Training",
                "why": "Improving your ability to find the best move is pure rating points. Every percentage point in accuracy matters.",
                "how": "Solve puzzles from your own mistakes first (they're the most relevant), then supplement with global puzzles. Aim for puzzles that take you 1-3 minutes.",
                "cta_label": "Start Puzzle Session",
                "cta_url": "/train?mode=warmup",
            })
    elif tier == "advanced":
        # Advanced: repertoire refinement, positional play, conversion
        if worst_phase == "opening":
            training_plan.append({
                "title": "Audit Your Opening Repertoire",
                "why": "Your opening accuracy is below where it should be. Some of your lines aren't working for you.",
                "how": "Go to your Openings page and sort by performance. Find the 2-3 openings with the worst results. Either study them deeper or switch to something more solid.",
                "cta_label": "View Openings",
                "cta_url": "/openings",
            })
        if collapses >= 3:
            training_plan.append({
                "title": "Conversion Practice",
                "why": "You've collapsed from winning positions multiple times. These are games you already won at the board — then gave back.",
                "how": "The 'Capitalize Advantages' trainer gives you YOUR positions where you were winning. Practice finding the calm, safe continuation instead of the flashy one.",
                "cta_label": "Capitalize Advantages",
                "cta_url": "/train?mode=advantage",
            })
        training_plan.append({
            "title": "Intuition Sharpening",
            "why": "At your level, rapid pattern recognition separates good play from great play. The faster you spot threats, the more time you save for critical decisions.",
            "how": "Do the Intuition Trainer: spot the blunder among 4 moves. This trains threat detection at speed.",
            "cta_label": "Intuition Trainer",
            "cta_url": "/train?mode=intuition",
        })
    else:  # expert
        training_plan.append({
            "title": "Deep Game Analysis",
            "why": "At your level, improvement comes from understanding your decisions, not just drilling tactics.",
            "how": "Review your last 5 losses in detail. For each loss, find the move where you went wrong and understand the CONCEPT you missed — was it a tactical pattern, a positional misjudgment, or a calculation error?",
            "cta_label": "View Games",
            "cta_url": "/games",
        })
        if cpl_stddev > 20:
            training_plan.append({
                "title": "Consistency Protocol",
                "why": "Your inconsistency is holding you back. Your bad games are dragging your rating down.",
                "how": "Build a pre-game checklist: Are you well-rested? Have you warmed up with 5 puzzles? Are you tilted from a previous game? Don't play if two of these are no.",
                "cta_label": "Daily Warmup",
                "cta_url": "/train?mode=warmup",
            })
        if worst_phase == "endgame":
            training_plan.append({
                "title": "Complex Endgame Study",
                "why": "Your endgame has gaps — likely in complex positions with multiple pieces on the board.",
                "how": "Study practical rook endgames and conversion technique. Play out endgame positions against Stockfish from your own games.",
                "cta_label": "Practice Endgames",
                "cta_url": "/train?phase=endgame",
            })

    # Ensure at least 3 training actions
    if len(training_plan) < 3:
        training_plan.append({
            "title": "Build the Analysis Habit",
            "why": "Every game has lessons — wins and losses alike. Players who analyze every game improve much faster.",
            "how": "After every game, spend 5 minutes: find your worst move, find your best move, check your opening. That's the full routine.",
            "cta_label": "View Games",
            "cta_url": "/games",
        })

    # ── 5. Weekly focus (compact version of study plan) ──
    from datetime import date as date_type
    today_str = date_type.today().strftime("%A")
    # Get the study plan for this week's focus areas
    study_plan = await get_study_plan(user=user, db=db)
    today_focus = None
    week_themes = []
    if study_plan.get("days"):
        for day in study_plan["days"]:
            if day.get("is_today"):
                today_focus = {"day": day["day"], "focus": day["focus"], "activities": day["activities"]}
            week_themes.append({"day": day["day"], "focus": day["focus"], "duration": day.get("total_duration_min", 0)})

    # ── Assemble the complete report ──
    return {
        "has_data": True,
        # Player context
        "elo": current_elo,
        "elo_trend": elo_trend,
        "elo_tier": tier,
        "elo_tier_label": tier_label,
        # Identity (for theming)
        "persona": persona,
        "overall_score": overall_score,
        "analyzed_games": analyzed_games,
        "total_games": total_games,
        # Report sections
        "headline": headline,
        "honest_truths": honest_truths,
        "chess_story": chess_story,
        "phase_report": phase_report,
        "tendencies": tendencies,
        "kryptonite": kryptonite,
        "training_plan": training_plan[:4],
        "growth_path": growth_path,
        "one_thing": one_thing,
        # Weekly context
        "today_focus": today_focus,
        "week_themes": week_themes,
    }
