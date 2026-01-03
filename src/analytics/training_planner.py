# src/analytics/training_planner.py
"""Module 5: Personalized Weekly Training Plan Generator.

Generate a structured training plan based strictly on analytics.

Rules:
- Training themes map directly to detected weaknesses
- Include focus area, specific endgame types or tactics
- Output structure, NOT prose (LLM converts to prose later)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .schemas import (
    WeeklyTrainingPlan,
    TrainingDay,
    BlunderClassification,
    EndgameMaterialBreakdown,
    OpeningDeviationReport,
    RecurringPatternReport,
)

if TYPE_CHECKING:
    from typing import Any


# Training theme mappings
ENDGAME_TRAINING = {
    "king_pawn": {
        "theme": "King and pawn endgames",
        "exercises": ["Opposition practice", "Key squares study", "Passed pawn races"],
    },
    "rook_endgames": {
        "theme": "Rook endgames",
        "exercises": ["Lucena position", "Philidor position", "Rook activity drills"],
    },
    "minor_piece": {
        "theme": "Minor piece endgames",
        "exercises": ["Bishop vs knight positions", "Good bishop vs bad bishop", "Knight maneuvering"],
    },
    "queen_endgames": {
        "theme": "Queen endgames",
        "exercises": ["Queen vs pawn", "Queen centralization", "Perpetual check patterns"],
    },
    "mixed": {
        "theme": "Complex endgames",
        "exercises": ["Rook + minor piece coordination", "Material imbalances", "Fortress recognition"],
    },
}

BLUNDER_TYPE_TRAINING = {
    "hanging_piece": {
        "theme": "Piece safety awareness",
        "exercises": ["Blunder check puzzles", "Defensive calculation", "Hanging piece drills"],
    },
    "missed_tactic": {
        "theme": "Tactical pattern recognition",
        "exercises": ["Tactics trainer", "Pattern memorization", "Combination practice"],
    },
    "king_safety": {
        "theme": "King safety evaluation",
        "exercises": ["Attack recognition", "Defensive resources", "Prophylaxis training"],
    },
    "endgame_technique": {
        "theme": "Endgame technique",
        "exercises": ["Theoretical endgames", "Conversion practice", "Practical endgame puzzles"],
    },
    "opening_error": {
        "theme": "Opening preparation",
        "exercises": ["Opening study", "Repertoire review", "Typical middlegame plans"],
    },
    "time_pressure": {
        "theme": "Time management",
        "exercises": ["Blitz practice", "Quick decision drills", "Move prioritization"],
    },
}

PHASE_TRAINING = {
    "opening": {
        "theme": "Opening principles",
        "exercises": ["Development practice", "Central control", "Early game plans"],
    },
    "middlegame": {
        "theme": "Middlegame strategy",
        "exercises": ["Pawn structure study", "Piece coordination", "Planning exercises"],
    },
    "endgame": {
        "theme": "Endgame fundamentals",
        "exercises": ["Basic checkmates", "Pawn promotion", "King activation"],
    },
}


def generate_training_plan(
    blunder_analysis: BlunderClassification,
    endgame_breakdown: EndgameMaterialBreakdown,
    opening_deviations: OpeningDeviationReport,
    recurring_patterns: RecurringPatternReport,
) -> WeeklyTrainingPlan:
    """Generate a personalized weekly training plan.

    Args:
        blunder_analysis: Blunder classification results
        endgame_breakdown: Endgame material breakdown
        opening_deviations: Opening deviation analysis
        recurring_patterns: Recurring pattern detection

    Returns:
        WeeklyTrainingPlan with structured training recommendations.
    """
    plan = WeeklyTrainingPlan()

    # Determine priorities based on analytics
    priorities: list[tuple[str, int, str, list[str]]] = []  # (area, severity_score, theme, exercises)

    # 1. Check recurring patterns (highest priority)
    if recurring_patterns.patterns:
        most_critical = recurring_patterns.patterns[0]
        pattern_type = most_critical.pattern_type

        # Map pattern to training
        if pattern_type in BLUNDER_TYPE_TRAINING:
            t = BLUNDER_TYPE_TRAINING[pattern_type]
            priorities.append((pattern_type, 100, t["theme"], t["exercises"]))
        elif "endgame" in pattern_type or pattern_type == "rook_passivity":
            priorities.append(("endgame_patterns", 90, "Endgame pattern recognition", ["Endgame puzzles", "Technique drills"]))
        elif "opening" in pattern_type or pattern_type == "post_theory_errors":
            priorities.append(("opening_patterns", 85, "Opening preparation", ["Theory review", "Typical plans"]))

    # 2. Check weakest endgame type
    if endgame_breakdown.weakest_endgame_type:
        weak_eg = endgame_breakdown.weakest_endgame_type
        if weak_eg in ENDGAME_TRAINING:
            t = ENDGAME_TRAINING[weak_eg]
            priorities.append((weak_eg, 80, t["theme"], t["exercises"]))
            plan.priority_endgame_types.append(weak_eg.replace("_", " ").title())

    # 3. Check blunder type distribution
    by_type = blunder_analysis.by_type
    type_counts = [
        ("hanging_piece", by_type.hanging_piece),
        ("missed_tactic", by_type.missed_tactic),
        ("king_safety", by_type.king_safety),
        ("endgame_technique", by_type.endgame_technique),
        ("opening_error", by_type.opening_error),
    ]
    type_counts.sort(key=lambda x: x[1], reverse=True)

    for btype, count in type_counts[:2]:
        if count >= 2 and btype in BLUNDER_TYPE_TRAINING:
            t = BLUNDER_TYPE_TRAINING[btype]
            priorities.append((btype, 70 - type_counts.index((btype, count)) * 5, t["theme"], t["exercises"]))
            if "tactic" in btype.lower():
                plan.priority_tactical_themes.append(t["theme"])

    # 4. Check phase weaknesses
    by_phase = blunder_analysis.by_phase
    if by_phase:
        worst_phase = max(by_phase.items(), key=lambda x: x[1])[0]
        if worst_phase in PHASE_TRAINING:
            t = PHASE_TRAINING[worst_phase]
            priorities.append((worst_phase, 60, t["theme"], t["exercises"]))

    # 5. Opening accuracy
    if opening_deviations.avg_eval_loss_on_deviation >= 50:
        priorities.append(("opening_accuracy", 55, "Opening accuracy", ["Move order study", "Deviation analysis"]))

    # Deduplicate and sort priorities
    seen_themes: set[str] = set()
    unique_priorities: list[tuple[str, int, str, list[str]]] = []
    for area, score, theme, exercises in priorities:
        if theme not in seen_themes:
            seen_themes.add(theme)
            unique_priorities.append((area, score, theme, exercises))
    unique_priorities.sort(key=lambda x: x[1], reverse=True)

    # Build weekly plan
    if unique_priorities:
        plan.primary_focus = unique_priorities[0][2]
        if len(unique_priorities) > 1:
            plan.secondary_focus = unique_priorities[1][2]

        # Rationale
        plan.rationale = f"Based on {blunder_analysis.total_blunders} blunders across games, " \
                        f"with concentration in {recurring_patterns.most_critical_pattern or 'various areas'}."

    # Assign days
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_assignments: list[TrainingDay] = []

    for i, day in enumerate(days):
        if i < len(unique_priorities):
            _, _, theme, exercises = unique_priorities[i % len(unique_priorities)]
            day_assignments.append(TrainingDay(
                day=day,
                theme=theme,
                focus_area=unique_priorities[i % len(unique_priorities)][0],
                suggested_exercises=exercises[:2],
                estimated_duration_minutes=30 if i < 5 else 45,  # weekends longer
            ))
        else:
            # Cycle through priorities or add review days
            if unique_priorities:
                idx = i % len(unique_priorities)
                _, _, theme, exercises = unique_priorities[idx]
                day_assignments.append(TrainingDay(
                    day=day,
                    theme=f"{theme} (review)",
                    focus_area="review",
                    suggested_exercises=["Practice games", "Puzzle review"],
                    estimated_duration_minutes=45,
                ))
            else:
                day_assignments.append(TrainingDay(
                    day=day,
                    theme="General improvement",
                    focus_area="general",
                    suggested_exercises=["Tactics trainer", "Practice games"],
                    estimated_duration_minutes=30,
                ))

    plan.weekly_plan = day_assignments

    return plan
