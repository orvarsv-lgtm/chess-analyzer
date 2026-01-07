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

    # Stable identifiers
    # - puzzle_id: original per-source id (may collide across users)
    # - puzzle_key: stable cross-user id derived from (fen, first_move_uci)
    puzzle_id: str = ""
    puzzle_key: str = ""

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
        uci = _san_to_uci_cached(p.fen, p.best_move_san)

    puzzle_key = hashlib.sha1(f"{p.fen}|{uci}".encode("utf-8")).hexdigest()[:16]

    # IMPORTANT (performance): do NOT compute Stockfish continuation lines here.
    # That can be very expensive when converting many puzzles (e.g., 64+).
    # We compute the full solution line lazily for the currently active puzzle in the UI.
    solution_moves = [uci]

    # Guarantee explanation presence (backward compatible with legacy puzzles).
    explanation = getattr(p, "explanation", None)
    if not explanation:
        try:
            board = chess.Board(p.fen)
            try:
                best_move = board.parse_san(p.best_move_san)
            except Exception:
                best_move = chess.Move.from_uci(uci)

            puzzle_type = getattr(p, "puzzle_type", None)
            if isinstance(puzzle_type, str):
                # Defensive: old serialized puzzles might store enum as string
                from puzzles.puzzle_types import PuzzleType

                puzzle_type = PuzzleType(puzzle_type)

            explanation = generate_puzzle_explanation(
                board=board,
                best_move=best_move,
                eval_loss_cp=int(getattr(p, "eval_loss_cp", 0) or 0),
                puzzle_type=puzzle_type,
                phase=str(getattr(p, "phase", "middlegame") or "middlegame"),
            )
        except Exception:
            explanation = "Explanation unavailable for this puzzle."

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
        white=(game_players or {}).get(int(getattr(p, "source_game_index", 0) or 0), ("", ""))[0],
        black=(game_players or {}).get(int(getattr(p, "source_game_index", 0) or 0), ("", ""))[1],
    )


def from_legacy_puzzles(
    puzzles: List[Puzzle],
    *,
    game_players: dict[int, tuple[str, str]] | None = None,
) -> List[PuzzleDefinition]:
    return [from_legacy_puzzle(p, game_players=game_players) for p in puzzles]
