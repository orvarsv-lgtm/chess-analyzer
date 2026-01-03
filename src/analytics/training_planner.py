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
        "exercises": ["Blunder check puzzles", "Defensive calculation", "Hanging piece drills", "'Is my piece safe?' pre-move checklist"],
    },
    "missed_tactic": {
        "theme": "Tactical pattern recognition",
        "exercises": ["Tactics trainer", "Pattern memorization", "Combination practice", "Fork/pin/skewer recognition"],
    },
    "king_safety": {
        "theme": "King safety evaluation",
        "exercises": ["Attack recognition", "Defensive resources", "Prophylaxis training", "King shelter analysis"],
    },
    "endgame_technique": {
        "theme": "Endgame technique",
        "exercises": ["Theoretical endgames", "Conversion practice", "Practical endgame puzzles", "King activation drills"],
    },
    "opening_error": {
        "theme": "Opening preparation",
        "exercises": ["Opening study", "Repertoire review", "Typical middlegame plans", "Memorize key lines"],
    },
    "time_pressure": {
        "theme": "Time management",
        "exercises": ["Blitz practice", "Quick decision drills", "Move prioritization", "Increment usage strategy"],
    },
    "back_rank": {
        "theme": "Back rank awareness",
        "exercises": ["Back rank mate patterns", "Luft creation (h3/h6)", "Escape square planning", "Rook lift maneuvers"],
    },
    "pawn_structure": {
        "theme": "Pawn structure mastery",
        "exercises": ["IQP positions", "Doubled pawn handling", "Pawn break timing", "Weak square identification"],
    },
    "piece_activity": {
        "theme": "Piece coordination",
        "exercises": ["Find the worst piece", "Piece activity puzzles", "Rook activation", "Knight outpost planning"],
    },
    "overlooked_recapture": {
        "theme": "Recapture awareness",
        "exercises": ["Capture sequence calculation", "Exchange evaluation", "Zwischenzug recognition"],
    },
    "promotion_oversight": {
        "theme": "Pawn promotion awareness",
        "exercises": ["Promotion race calculation", "Passed pawn creation", "Queening technique"],
    },
    "discovered_attack": {
        "theme": "Discovery pattern recognition",
        "exercises": ["Discovered attack puzzles", "Battery creation", "X-ray motifs"],
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
        ("back_rank", by_type.back_rank),
        ("pawn_structure", by_type.pawn_structure),
        ("piece_activity", by_type.piece_activity),
    ]
    type_counts.sort(key=lambda x: x[1], reverse=True)

    for btype, count in type_counts[:3]:  # Top 3 blunder types
        if count >= 1 and btype in BLUNDER_TYPE_TRAINING:
            t = BLUNDER_TYPE_TRAINING[btype]
            priorities.append((btype, 70 - type_counts.index((btype, count)) * 5, t["theme"], t["exercises"]))
            if "tactic" in btype.lower():
                plan.priority_tactical_themes.append(t["theme"])

    # 4. Check phase weaknesses
    by_phase = blunder_analysis.by_phase
    if by_phase:
        phase_values = [(p, c) for p, c in by_phase.items() if c > 0]
        if phase_values:
            worst_phase = max(phase_values, key=lambda x: x[1])[0]
            if worst_phase in PHASE_TRAINING:
                t = PHASE_TRAINING[worst_phase]
                priorities.append((worst_phase, 60, t["theme"], t["exercises"]))

    # 5. Opening accuracy
    if opening_deviations.avg_eval_loss_on_deviation >= 50:
        priorities.append(("opening_accuracy", 55, "Opening accuracy", ["Move order study", "Deviation analysis", "Opening repertoire building"]))

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

        # Detailed rationale
        blunder_areas = []
        if blunder_analysis.by_type.missed_tactic > 0:
            blunder_areas.append("missed tactics")
        if blunder_analysis.by_type.hanging_piece > 0:
            blunder_areas.append("piece safety")
        if blunder_analysis.by_type.endgame_technique > 0:
            blunder_areas.append("endgame technique")
        if blunder_analysis.by_type.opening_error > 0:
            blunder_areas.append("opening theory")
        if blunder_analysis.by_type.king_safety > 0:
            blunder_areas.append("king safety")
        if blunder_analysis.by_type.back_rank > 0:
            blunder_areas.append("back rank awareness")
        
        area_str = ", ".join(blunder_areas[:3]) if blunder_areas else "general play"
        plan.rationale = f"Based on {blunder_analysis.total_blunders} blunders across games with issues in {area_str}. " \
                        f"Most critical pattern: {recurring_patterns.most_critical_pattern or 'varied errors'}."

    # Assign days with more detailed exercises
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_assignments: list[TrainingDay] = []

    for i, day in enumerate(days):
        if i < len(unique_priorities):
            area, _, theme, exercises = unique_priorities[i % len(unique_priorities)]
            # Add more specific exercises based on area
            expanded_exercises = _expand_exercises(area, exercises)
            day_assignments.append(TrainingDay(
                day=day,
                theme=theme,
                focus_area=area,
                suggested_exercises=expanded_exercises[:4],
                estimated_duration_minutes=30 if i < 5 else 45,  # weekends longer
            ))
        else:
            # Cycle through priorities or add review days
            if unique_priorities:
                idx = i % len(unique_priorities)
                area, _, theme, exercises = unique_priorities[idx]
                day_assignments.append(TrainingDay(
                    day=day,
                    theme=f"{theme} (review & practice)",
                    focus_area="review",
                    suggested_exercises=["Play 2-3 practice games", "Review today's mistakes", "Puzzle sprint (20 puzzles)"],
                    estimated_duration_minutes=45,
                ))
            else:
                day_assignments.append(TrainingDay(
                    day=day,
                    theme="General improvement",
                    focus_area="general",
                    suggested_exercises=["Tactics trainer (30 min)", "Play 1 slow game", "Analyze your game"],
                    estimated_duration_minutes=30,
                ))

    plan.weekly_plan = day_assignments
    
    # Generate recommended resources based on weaknesses
    plan.recommended_resources = _generate_resources(unique_priorities, endgame_breakdown)

    return plan


def _expand_exercises(area: str, base_exercises: list[str]) -> list[str]:
    """Expand exercises with more specific suggestions."""
    expanded = list(base_exercises)
    
    area_specific = {
        "hanging_piece": [
            "Before each move, ask: 'Is my piece defended?'",
            "Lichess puzzle theme: Hanging piece",
            "Play 5 slow games focusing on piece safety",
        ],
        "missed_tactic": [
            "Lichess puzzles (30+ daily)",
            "Study fork/pin/skewer patterns",
            "Analyze master games for tactical motifs",
            "Chess tempo tactical training",
        ],
        "king_safety": [
            "Study attacking patterns against castled king",
            "Practice h-pawn storm attacks",
            "Learn Greek gift sacrifice patterns",
            "Lichess puzzle theme: King attack",
        ],
        "endgame_technique": [
            "Silman's Complete Endgame Course (chapter per week)",
            "Practice basic checkmates blindfolded",
            "Lichess endgame studies",
            "Master K+P vs K positions",
        ],
        "opening_error": [
            "Build opening repertoire (3 openings max)",
            "Study 5 master games in your openings",
            "Practice opening moves for speed",
            "Learn key middlegame plans from your openings",
        ],
        "back_rank": [
            "Study back rank mate patterns",
            "Practice creating luft (h3/h6)",
            "Lichess puzzle theme: Back rank mate",
        ],
        "pawn_structure": [
            "Study pawn structures (IQP, hanging pawns, etc.)",
            "Learn plans for common structures",
            "Watch Naroditsky pawn structure videos",
        ],
        "piece_activity": [
            "Study piece coordination",
            "Practice finding the worst piece",
            "Improve knight vs bishop understanding",
        ],
        "rook_endgames": [
            "Master Lucena and Philidor positions",
            "Practice rook activity in endgames",
            "Study rook + pawn vs rook",
        ],
        "king_pawn": [
            "Learn key squares and opposition",
            "Practice pawn promotion races",
            "Study triangulation",
        ],
    }
    
    if area in area_specific:
        expanded.extend(area_specific[area])
    
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for ex in expanded:
        if ex.lower() not in seen:
            seen.add(ex.lower())
            unique.append(ex)
    
    return unique[:6]  # Return top 6 exercises


def _generate_resources(priorities: list[tuple[str, int, str, list[str]]], 
                       endgame_breakdown: EndgameMaterialBreakdown) -> list[str]:
    """Generate recommended resources based on detected weaknesses."""
    resources = []
    
    # Always recommend these
    resources.append("Lichess.org - Free tactics trainer and lessons")
    
    priority_areas = {p[0] for p in priorities}
    
    # Tactical weakness resources
    if any(a in priority_areas for a in ["missed_tactic", "hanging_piece"]):
        resources.append("Chess.com Tactics Trainer or Lichess Puzzles (aim for 30+ daily)")
        resources.append("'Winning Chess Tactics' by Yasser Seirawan")
        resources.append("ChessTempo.com for rated tactical training")
    
    # Endgame resources
    if any(a in priority_areas for a in ["endgame_technique", "rook_endgames", "king_pawn", "minor_piece"]):
        resources.append("'Silman's Complete Endgame Course' - study appropriate chapter")
        resources.append("Lichess Practice: Endgames section")
        resources.append("'100 Endgames You Must Know' by Jesus de la Villa")
    
    # Opening resources
    if any(a in priority_areas for a in ["opening_error", "opening_accuracy", "opening_patterns"]):
        resources.append("ChessBase/Lichess Opening Explorer")
        resources.append("YouTube: GothamChess or Daniel Naroditsky opening guides")
        resources.append("Focus on understanding ideas, not memorizing moves")
    
    # King safety / Attack resources
    if "king_safety" in priority_areas:
        resources.append("'The Art of Attack in Chess' by Vladimir Vukovic")
        resources.append("Study attacking games (Tal, Kasparov)")
    
    # Specific endgame type recommendations
    if endgame_breakdown.weakest_endgame_type == "rook_endgames":
        resources.append("'Dvoretsky's Endgame Manual' - Rook endings chapter")
    elif endgame_breakdown.weakest_endgame_type == "king_pawn":
        resources.append("Study king and pawn endgames systematically")
    
    # General improvement
    resources.append("Play slow games (15+10 or longer) and analyze every game")
    resources.append("Watch Daniel Naroditsky's 'Speedrun' series for thinking process")
    
    return resources[:10]  # Limit to 10 resources
