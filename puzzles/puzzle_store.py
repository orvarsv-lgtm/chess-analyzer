from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List

import chess

from puzzles.puzzle_types import Puzzle, Difficulty


@dataclass(frozen=True)
class PuzzleDefinition:
    """Puzzle schema required by the JS board UI."""

    fen: str
    solution_moves: List[str]  # UCI moves
    theme: str
    difficulty: int


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


def from_legacy_puzzle(p: Puzzle) -> PuzzleDefinition:
    """Convert existing Puzzle -> PuzzleDefinition without changing generation."""

    if p.best_move_uci:
        uci = p.best_move_uci
    else:
        uci = _san_to_uci_cached(p.fen, p.best_move_san)

    return PuzzleDefinition(
        fen=p.fen,
        solution_moves=[uci],
        theme=p.puzzle_type.value,
        difficulty=_difficulty_to_int(p.difficulty),
    )


def from_legacy_puzzles(puzzles: List[Puzzle]) -> List[PuzzleDefinition]:
    return [from_legacy_puzzle(p) for p in puzzles]
