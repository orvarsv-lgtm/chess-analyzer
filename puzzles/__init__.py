"""
Chess Puzzle Generation Module

Deterministic puzzle generation from analyzed games.
All puzzles are derived from engine-identified blunders and mistakes.

No AI/LLM, no randomness - purely rule-based.
"""

from .puzzle_types import Puzzle, PuzzleAttempt, PuzzleSession, PuzzleType, Difficulty
from .difficulty import classify_difficulty
from .puzzle_engine import (
    PuzzleGenerator, 
    generate_puzzles_from_games, 
    get_puzzle_stats,
    generate_puzzle_explanation,
    generate_puzzle_explanation_detailed,
)
from .explanation_engine import (
    PuzzleExplanation,
    TacticalMotif,
    generate_puzzle_explanation_v2,
    generate_explanation_string,
    get_tactical_pattern_explanation,
)
from .tactical_patterns import (
    PatternAttribution,
    AtomicConstraint,
    TacticalOutcome,
    CompositePattern,
    AdvancedPattern,
    ConstraintEvidence,
    analyze_tactical_patterns,
    explain_why_move_works,
    get_all_constraints_for_position,
)
from .puzzle_ui import render_puzzle_board, render_puzzle_controls, PuzzleUIState, render_puzzle_page

__all__ = [
    # Types
    "Puzzle",
    "PuzzleAttempt",
    "PuzzleSession",
    "PuzzleType",
    "Difficulty",
    "PuzzleExplanation",
    "TacticalMotif",
    # New Pattern Types
    "PatternAttribution",
    "AtomicConstraint",
    "TacticalOutcome",
    "CompositePattern",
    "AdvancedPattern",
    "ConstraintEvidence",
    # Functions
    "classify_difficulty",
    "generate_puzzles_from_games",
    "get_puzzle_stats",
    "generate_puzzle_explanation",
    "generate_puzzle_explanation_detailed",
    "generate_puzzle_explanation_v2",
    "generate_explanation_string",
    "get_tactical_pattern_explanation",
    # New Pattern Functions
    "analyze_tactical_patterns",
    "explain_why_move_works",
    "get_all_constraints_for_position",
    # Classes
    "PuzzleGenerator",
    "PuzzleUIState",
    # UI
    "render_puzzle_board",
    "render_puzzle_controls",
    "render_puzzle_page",
]
