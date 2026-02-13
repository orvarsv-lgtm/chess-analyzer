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
