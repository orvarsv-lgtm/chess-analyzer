# src/analytics/aggregator.py
"""Analytics Aggregator: Compose all modules into final coach-ready JSON summary.

This is the main entry point for the analytics pipeline.
It orchestrates all modules and produces the final CoachingSummary.

Pipeline:
PGN
 └─▶ Engine Analysis (existing)
     └─▶ Deterministic Analytics Modules (this pipeline)
         └─▶ Aggregated Metrics + Pattern Candidates
             └─▶ LLM-Ready JSON Summary (CoachingSummary)
                 └─▶ AI Coach Output (text) [LLM layer, not in this module]
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .schemas import (
    CoachingSummary,
    PlayerProfile,
    BlunderClassification,
    EndgameMaterialBreakdown,
    OpeningDeviationReport,
    RecurringPatternReport,
    WeeklyTrainingPlan,
    PeerBenchmark,
)
from .blunder_classifier import analyze_blunders
from .endgame_analyzer import analyze_endgames
from .opening_deviation import analyze_opening_deviations
from .recurring_patterns import detect_recurring_patterns
from .training_planner import generate_training_plan
from .peer_benchmark import benchmark_from_games_data

if TYPE_CHECKING:
    from typing import Any


def _ceil_int(x: float) -> int:
    return int(math.ceil(x))


def _extract_player_profile(
    games_data: list[dict[str, Any]],
    username: str = "",
    player_rating: int = 0,
) -> PlayerProfile:
    """Extract player profile from games data."""
    profile = PlayerProfile()
    profile.username = username
    profile.games_analyzed = len(games_data)

    total_moves = 0
    all_cp_losses: list[int] = []
    phase_cp_losses: dict[str, list[int]] = {"opening": [], "middlegame": [], "endgame": []}
    wins = 0
    draws = 0
    losses = 0
    openings: dict[str, int] = {}
    ratings: list[int] = []
    time_controls: dict[str, int] = {}

    for game in games_data:
        game_info = game.get("game_info", {}) or {}
        move_evals = game.get("move_evals", []) or []

        # Results
        result = game_info.get("score")
        if result == "win":
            wins += 1
        elif result == "draw":
            draws += 1
        elif result == "loss":
            losses += 1

        # Openings
        opening = game_info.get("opening_name") or "Unknown"
        openings[opening] = openings.get(opening, 0) + 1

        # Rating
        for key in ("player_rating", "rating", "white_rating", "black_rating"):
            r = game_info.get(key)
            if r:
                try:
                    ratings.append(int(r))
                except Exception:
                    pass

        # Time control
        tc = game_info.get("time_control") or ""
        if tc:
            time_controls[tc] = time_controls.get(tc, 0) + 1

        # CPL by phase
        for m in move_evals:
            cp_loss = int(m.get("cp_loss") or 0)
            phase = str(m.get("phase") or "middlegame")
            total_moves += 1

            if cp_loss > 0:
                capped = min(cp_loss, 2000)
                all_cp_losses.append(capped)
                if phase in phase_cp_losses:
                    phase_cp_losses[phase].append(capped)

    profile.total_moves = total_moves

    # Overall CPL
    if all_cp_losses:
        profile.overall_cpl = _ceil_int(sum(all_cp_losses) / len(all_cp_losses))

    # Phase CPLs
    for phase, phase_loss_list in phase_cp_losses.items():
        if phase_loss_list:
            profile.phase_cpls[phase] = _ceil_int(sum(phase_loss_list) / len(phase_loss_list))

    # Win rates
    total_games = wins + draws + losses
    if total_games > 0:
        profile.win_rate_pct = _ceil_int((wins / total_games) * 100)
        profile.draw_rate_pct = _ceil_int((draws / total_games) * 100)
        profile.loss_rate_pct = _ceil_int((losses / total_games) * 100)

    # Favorite openings (top 3)
    sorted_openings = sorted(openings.items(), key=lambda x: x[1], reverse=True)
    profile.favorite_openings = [o[0] for o in sorted_openings[:3]]

    # Rating
    if player_rating > 0:
        profile.rating = player_rating
    elif ratings:
        profile.rating = int(sum(ratings) / len(ratings))

    # Time control preference
    if time_controls:
        profile.time_control_preference = max(time_controls.items(), key=lambda x: x[1])[0]

    return profile


def _derive_critical_issues(
    blunder_analysis: BlunderClassification,
    endgame_breakdown: EndgameMaterialBreakdown,
    recurring_patterns: RecurringPatternReport,
) -> list[str]:
    """Derive critical issues from analytics."""
    issues: list[str] = []

    # High blunder rate
    if blunder_analysis.blunder_rate_per_100_moves >= 3.0:
        issues.append(f"High blunder rate: {_ceil_int(blunder_analysis.blunder_rate_per_100_moves)} per 100 moves")

    # Dominant blunder type
    by_type = blunder_analysis.by_type
    total = blunder_analysis.total_blunders
    if total > 0:
        type_counts = [
            ("Hanging pieces", by_type.hanging_piece),
            ("Missed tactics", by_type.missed_tactic),
            ("King safety", by_type.king_safety),
            ("Endgame technique", by_type.endgame_technique),
        ]
        for name, count in type_counts:
            if count > 0 and count / total >= 0.4:
                issues.append(f"{name}: {_ceil_int(count/total*100)}% of blunders")

    # Critical recurring pattern
    if recurring_patterns.patterns:
        critical = [p for p in recurring_patterns.patterns if p.severity == "critical"]
        for p in critical[:2]:
            issues.append(f"Recurring: {p.description} ({p.occurrences} occurrences)")

    # Weak endgame type
    if endgame_breakdown.weakest_endgame_type:
        weak = endgame_breakdown.weakest_endgame_type
        stats = getattr(endgame_breakdown, weak, None)
        if stats and stats.avg_cpl > 0:
            issues.append(f"Weak in {weak.replace('_', ' ')}: {stats.avg_cpl} avg CPL")

    return issues[:5]


def _derive_secondary_patterns(
    opening_deviations: OpeningDeviationReport,
    recurring_patterns: RecurringPatternReport,
    blunder_analysis: BlunderClassification,
) -> list[str]:
    """Derive secondary patterns from analytics."""
    patterns: list[str] = []

    # Opening deviation issues
    if opening_deviations.avg_eval_loss_on_deviation >= 30:
        patterns.append(f"Opening deviations cost avg {opening_deviations.avg_eval_loss_on_deviation}cp")

    if opening_deviations.most_costly_opening:
        patterns.append(f"Most problematic opening: {opening_deviations.most_costly_opening}")

    # Moderate recurring patterns
    if recurring_patterns.patterns:
        moderate = [p for p in recurring_patterns.patterns if p.severity == "moderate"]
        for p in moderate[:2]:
            patterns.append(f"{p.description}")

    # Phase clustering
    by_phase = blunder_analysis.by_phase
    total = sum(by_phase.values())
    if total > 0:
        for phase, count in by_phase.items():
            if count / total >= 0.5:
                patterns.append(f"{_ceil_int(count/total*100)}% of blunders in {phase}")

    return patterns[:5]


def _derive_strengths(
    player_profile: PlayerProfile,
    blunder_analysis: BlunderClassification,
    endgame_breakdown: EndgameMaterialBreakdown,
    peer_comparison: PeerBenchmark,
) -> list[str]:
    """Derive player strengths from analytics."""
    strengths: list[str] = []

    # Low blunder rate
    if blunder_analysis.blunder_rate_per_100_moves <= 1.5:
        strengths.append("Low blunder rate")

    # Strong endgame type
    if endgame_breakdown.strongest_endgame_type:
        strong = endgame_breakdown.strongest_endgame_type
        stats = getattr(endgame_breakdown, strong, None)
        if stats and stats.games > 0:
            strengths.append(f"Strong {strong.replace('_', ' ')}")

    # Above-average vs peers
    if peer_comparison.overall_cpl_percentile >= 60:
        strengths.append(f"Top {100 - peer_comparison.overall_cpl_percentile}% CPL in rating bracket")

    # Strongest phase vs peers
    if peer_comparison.strongest_vs_peers:
        phase = peer_comparison.strongest_vs_peers
        pct = getattr(peer_comparison, f"{phase}_cpl_percentile", 0)
        if pct >= 60:
            strengths.append(f"Strong {phase} (top {100 - pct}% vs peers)")

    # Win rate
    if player_profile.win_rate_pct >= 55:
        strengths.append(f"Positive win rate: {player_profile.win_rate_pct}%")

    return strengths[:5]


def generate_coaching_report(
    games_data: list[dict[str, Any]],
    username: str = "",
    player_rating: int = 0,
) -> CoachingSummary:
    """Generate complete coaching report from games data.

    This is the main entry point for the analytics pipeline.

    Args:
        games_data: List of game dicts with move_evals, game_info
        username: Player username
        player_rating: Player rating (optional, will be extracted from games if not provided)

    Returns:
        CoachingSummary ready for LLM processing.

    Example usage:
        from src.analytics import generate_coaching_report

        # games_data comes from engine analysis
        report = generate_coaching_report(games_data, username="magnus", player_rating=2800)

        # Get LLM-ready JSON
        llm_input = report.to_json()
    """
    summary = CoachingSummary()

    # 1. Extract player profile
    summary.player_profile = _extract_player_profile(games_data, username, player_rating)

    # 2. Run all analytics modules
    summary.blunder_analysis = analyze_blunders(games_data)
    summary.endgame_breakdown = analyze_endgames(games_data)
    summary.opening_deviations = analyze_opening_deviations(games_data)
    summary.recurring_patterns = detect_recurring_patterns(games_data)

    # 3. Generate training plan based on analytics
    summary.training_plan = generate_training_plan(
        summary.blunder_analysis,
        summary.endgame_breakdown,
        summary.opening_deviations,
        summary.recurring_patterns,
    )

    # 4. Compute peer benchmark
    summary.peer_comparison = benchmark_from_games_data(games_data, player_rating)

    # 5. Derive prioritized insights
    summary.critical_issues = _derive_critical_issues(
        summary.blunder_analysis,
        summary.endgame_breakdown,
        summary.recurring_patterns,
    )

    summary.secondary_patterns = _derive_secondary_patterns(
        summary.opening_deviations,
        summary.recurring_patterns,
        summary.blunder_analysis,
    )

    summary.strengths = _derive_strengths(
        summary.player_profile,
        summary.blunder_analysis,
        summary.endgame_breakdown,
        summary.peer_comparison,
    )

    return summary
