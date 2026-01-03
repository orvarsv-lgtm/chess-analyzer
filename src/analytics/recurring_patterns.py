# src/analytics/recurring_patterns.py
"""Module 4: Recurring Mistake Detection.

Detect patterns that repeat across games, not just isolated mistakes.

Required Patterns:
- Same blunder type recurring
- Same tactical motif missed repeatedly
- Errors clustering in same game phase
- Blunders after leaving theory
- Errors under time pressure

Implementation:
- Frequency thresholds
- Time-window clustering
- Cross-game aggregation
"""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from .schemas import RecurringPatternReport, RecurringPattern
from .blunder_classifier import BLUNDER_CP_THRESHOLD, MISTAKE_CP_THRESHOLD

if TYPE_CHECKING:
    from typing import Any

# Pattern detection thresholds
MIN_OCCURRENCES_CRITICAL = 3
MIN_OCCURRENCES_MODERATE = 2
MIN_GAMES_FOR_PATTERN = 2


def _ceil_int(x: float) -> int:
    return int(math.ceil(x))


def _severity(occurrences: int, games_affected: int) -> str:
    """Determine pattern severity."""
    if occurrences >= 5 or games_affected >= 4:
        return "critical"
    if occurrences >= 3 or games_affected >= 2:
        return "moderate"
    return "minor"


def detect_recurring_patterns(games_data: list[dict[str, Any]]) -> RecurringPatternReport:
    """Detect recurring mistake patterns across games.

    Args:
        games_data: List of game dicts with move_evals.

    Returns:
        RecurringPatternReport with detected patterns.
    """
    result = RecurringPatternReport()
    patterns: list[RecurringPattern] = []

    # Accumulators
    blunder_types: Counter[str] = Counter()
    blunder_types_games: dict[str, set[int]] = {}
    phase_errors: Counter[str] = Counter()
    phase_errors_games: dict[str, set[int]] = {}
    post_theory_blunders = 0
    post_theory_games: set[int] = set()
    time_pressure_errors = 0
    time_pressure_games: set[int] = set()

    # Tactical motifs (simplified detection)
    back_rank_issues = 0
    back_rank_games: set[int] = set()
    pin_misses = 0
    pin_games: set[int] = set()
    fork_misses = 0
    fork_games: set[int] = set()

    # Piece-specific patterns
    rook_passivity = 0
    rook_passivity_games: set[int] = set()
    knight_blunders = 0
    knight_games: set[int] = set()
    queen_early_losses = 0
    queen_early_games: set[int] = set()

    for game_idx, game in enumerate(games_data):
        move_evals = game.get("move_evals", []) or []
        game_info = game.get("game_info", {}) or {}

        # Track if we've left theory in this game
        in_theory = True
        theory_depth = 0

        for m in move_evals:
            cp_loss = int(m.get("cp_loss") or 0)
            phase = str(m.get("phase") or "middlegame")
            blunder_subtype = m.get("blunder_subtype") or ""
            move_num = int(m.get("move_num") or m.get("move_number") or 1)
            san = str(m.get("san") or m.get("move_san") or "")
            piece = str(m.get("piece") or "")
            clock = m.get("clock_seconds")

            is_blunder = cp_loss >= BLUNDER_CP_THRESHOLD
            is_mistake = cp_loss >= MISTAKE_CP_THRESHOLD

            if not is_mistake:
                continue

            # Count by blunder subtype
            if blunder_subtype and is_blunder:
                blunder_types[blunder_subtype] += 1
                blunder_types_games.setdefault(blunder_subtype, set()).add(game_idx)

            # Phase error clustering
            if is_blunder:
                phase_errors[phase] += 1
                phase_errors_games.setdefault(phase, set()).add(game_idx)

            # Post-theory blunders (after move 10)
            if move_num > 10 and is_blunder:
                post_theory_blunders += 1
                post_theory_games.add(game_idx)

            # Time pressure
            if clock is not None and int(clock) <= 30 and is_mistake:
                time_pressure_errors += 1
                time_pressure_games.add(game_idx)

            # Back rank issues (simplistic: king on back rank + rook blunder)
            if phase == "middlegame" and piece == "Rook" and is_blunder:
                back_rank_issues += 1
                back_rank_games.add(game_idx)

            # Rook passivity in endgames
            if phase == "endgame" and piece == "Rook" and is_mistake:
                rook_passivity += 1
                rook_passivity_games.add(game_idx)

            # Knight blunders
            if piece == "Knight" and is_blunder:
                knight_blunders += 1
                knight_games.add(game_idx)

            # Early queen losses
            if piece == "Queen" and move_num <= 15 and is_blunder:
                queen_early_losses += 1
                queen_early_games.add(game_idx)

    # Build patterns

    # 1. Recurring blunder types
    for btype, count in blunder_types.most_common(5):
        games = len(blunder_types_games.get(btype, set()))
        if count >= MIN_OCCURRENCES_MODERATE and games >= MIN_GAMES_FOR_PATTERN:
            patterns.append(RecurringPattern(
                pattern_type=btype,
                description=f"Recurring {btype.replace('_', ' ')} blunders",
                occurrences=count,
                games_affected=games,
                phase_concentration="all",
                severity=_severity(count, games),
            ))

    # 2. Phase clustering
    for phase, count in phase_errors.most_common():
        games = len(phase_errors_games.get(phase, set()))
        total_blunders = sum(phase_errors.values())
        if total_blunders > 0 and count / total_blunders >= 0.5 and count >= MIN_OCCURRENCES_CRITICAL:
            patterns.append(RecurringPattern(
                pattern_type=f"{phase}_weakness",
                description=f"Errors concentrate in {phase} phase ({_ceil_int(count/total_blunders*100)}%)",
                occurrences=count,
                games_affected=games,
                phase_concentration=phase,
                severity=_severity(count, games),
            ))

    # 3. Post-theory blunders
    if post_theory_blunders >= MIN_OCCURRENCES_MODERATE:
        patterns.append(RecurringPattern(
            pattern_type="post_theory_errors",
            description="Blunders occur after leaving opening theory",
            occurrences=post_theory_blunders,
            games_affected=len(post_theory_games),
            phase_concentration="middlegame",
            severity=_severity(post_theory_blunders, len(post_theory_games)),
        ))

    # 4. Time pressure
    if time_pressure_errors >= MIN_OCCURRENCES_MODERATE:
        patterns.append(RecurringPattern(
            pattern_type="time_pressure",
            description="Errors under time pressure (<30 seconds)",
            occurrences=time_pressure_errors,
            games_affected=len(time_pressure_games),
            phase_concentration="endgame",
            severity=_severity(time_pressure_errors, len(time_pressure_games)),
        ))

    # 5. Tactical motifs
    if back_rank_issues >= MIN_OCCURRENCES_MODERATE:
        patterns.append(RecurringPattern(
            pattern_type="back_rank_weakness",
            description="Back rank tactical vulnerabilities",
            occurrences=back_rank_issues,
            games_affected=len(back_rank_games),
            phase_concentration="middlegame",
            severity=_severity(back_rank_issues, len(back_rank_games)),
        ))

    if rook_passivity >= MIN_OCCURRENCES_MODERATE:
        patterns.append(RecurringPattern(
            pattern_type="rook_passivity",
            description="Passive rook play in endgames",
            occurrences=rook_passivity,
            games_affected=len(rook_passivity_games),
            phase_concentration="endgame",
            severity=_severity(rook_passivity, len(rook_passivity_games)),
        ))

    if knight_blunders >= MIN_OCCURRENCES_CRITICAL:
        patterns.append(RecurringPattern(
            pattern_type="knight_handling",
            description="Knight-related blunders (possibly positional)",
            occurrences=knight_blunders,
            games_affected=len(knight_games),
            phase_concentration="all",
            severity=_severity(knight_blunders, len(knight_games)),
        ))

    if queen_early_losses >= MIN_OCCURRENCES_MODERATE:
        patterns.append(RecurringPattern(
            pattern_type="early_queen_trouble",
            description="Early queen moves leading to blunders",
            occurrences=queen_early_losses,
            games_affected=len(queen_early_games),
            phase_concentration="opening",
            severity=_severity(queen_early_losses, len(queen_early_games)),
        ))

    # Sort by severity and occurrence
    severity_order = {"critical": 0, "moderate": 1, "minor": 2}
    patterns.sort(key=lambda p: (severity_order.get(p.severity, 3), -p.occurrences))

    result.patterns = patterns
    result.pattern_count = len(patterns)
    if patterns:
        result.most_critical_pattern = patterns[0].pattern_type

    return result
