from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from typing import List

import chess

from puzzles.puzzle_types import Puzzle, Difficulty
from puzzles.puzzle_engine import generate_puzzle_explanation


@dataclass(frozen=True)
class PuzzleDefinition:
    """Puzzle schema required by the JS board UI."""

    fen: str
    # First (required) best move in UCI. Full solution line is computed lazily in the UI.
    first_move_uci: str
    solution_moves: List[str]  # UCI moves - usually just [first_move_uci] until expanded
    theme: str
    difficulty: int
    explanation: str = ""
    # Optional source metadata for display in the trainer UI
    source_game_index: int | None = None
    white: str = ""
    black: str = ""
    # Stable identifiers (must come last, with defaults)
    puzzle_id: str = ""
    puzzle_key: str = ""


def _difficulty_to_int(d: Difficulty) -> int:
    # Keep simple + deterministic
    if d == Difficulty.EASY:
        return 1
    if d == Difficulty.MEDIUM:
        return 2
    return 3


@lru_cache(maxsize=1024)
def _san_to_uci_cached(fen: str, san: str) -> str:
    board = chess.Board(fen)
    move = board.parse_san(san)
    return move.uci()


def from_legacy_puzzle(
    p: Puzzle,
    *,
    game_players: dict[int, tuple[str, str]] | None = None,
) -> PuzzleDefinition:
    """Convert existing Puzzle -> PuzzleDefinition without changing generation."""

    if p.best_move_uci:
        uci = p.best_move_uci
    else:
        try:
            uci = _san_to_uci_cached(p.fen, p.best_move_san)
        except Exception:
            # If SAN conversion fails, this puzzle is corrupt. Raise to skip it.
            raise ValueError(f"Invalid puzzle: cannot parse {p.best_move_san} in {p.fen}")

    puzzle_key = hashlib.sha1(f"{p.fen}|{uci}".encode("utf-8")).hexdigest()[:16]

    # IMPORTANT (performance): do NOT compute Stockfish continuation lines here.
    # That can be very expensive when converting many puzzles (e.g., 64+).
    # We compute the full solution line lazily for the currently active puzzle in the UI.
    solution_moves = [uci]

    # PERFORMANCE: Skip explanation generation entirely here.
    # Explanations are generated on-demand in the UI when a puzzle is displayed.
    # This makes puzzle loading instant even for large puzzle sets.
    explanation = getattr(p, "explanation", None) or ""

    return PuzzleDefinition(
        puzzle_id=str(getattr(p, "puzzle_id", "") or ""),
        puzzle_key=puzzle_key,
        fen=p.fen,
        first_move_uci=uci,
        solution_moves=solution_moves,
        theme=p.puzzle_type.value,
        difficulty=_difficulty_to_int(p.difficulty),
        explanation=explanation or "Explanation unavailable for this puzzle.",
         source_game_index=int(getattr(p, "source_game_index", 0) or 0) or None,
         # Prefer origin names embedded in puzzle (if saved with global bank),
         # otherwise map using current game_players (may be None for Other Users view).
         white=(getattr(p, "origin_white", None)
             or (game_players or {}).get(int(getattr(p, "source_game_index", 0) or 0), ("", ""))[0]),
         black=(getattr(p, "origin_black", None)
             or (game_players or {}).get(int(getattr(p, "source_game_index", 0) or 0), ("", ""))[1]),
    )


def from_legacy_puzzles(
    puzzles: List[Puzzle],
    *,
    game_players: dict[int, tuple[str, str]] | None = None,
) -> List[PuzzleDefinition]:
    result = []
    for p in puzzles:
        try:
            result.append(from_legacy_puzzle(p, game_players=game_players))
        except Exception:
            # Skip invalid puzzles silently
            continue
    return result
