"""
Chess Puzzle Generation Module

Deterministic puzzle generation from analyzed games.
All puzzles are derived from engine-identified blunders and mistakes.

No AI/LLM, no randomness - purely rule-based.
"""

from .puzzle_types import Puzzle, PuzzleAttempt, PuzzleSession, PuzzleType, Difficulty
from .difficulty import classify_difficulty
from .puzzle_engine import PuzzleGenerator, generate_puzzles_from_games, get_puzzle_stats
from .puzzle_ui import render_puzzle_board, render_puzzle_controls, PuzzleUIState, render_puzzle_page

__all__ = [
    # Types
    "Puzzle",
    "PuzzleAttempt",
    "PuzzleSession",
    "PuzzleType",
    "Difficulty",
    # Functions
    "classify_difficulty",
    "generate_puzzles_from_games",
    "get_puzzle_stats",
    # Classes
    "PuzzleGenerator",
    "PuzzleUIState",
    # UI
    "render_puzzle_board",
    "render_puzzle_controls",
    "render_puzzle_page",
]
