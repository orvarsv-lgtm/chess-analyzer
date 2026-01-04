from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import chess
import streamlit as st

from puzzles.puzzle_store import PuzzleDefinition
from ui.chessboard_component import render_chessboard


@dataclass
class PuzzleProgress:
    current_index: int = 0
    solved: int = 0
    last_result: Optional[str] = None  # "correct" | "incorrect" | None
    last_uci: Optional[str] = None
    current_fen: Optional[str] = None  # tracks accepted position
    active_puzzle_index: Optional[int] = None


_STATE_KEY = "puzzle_progress_v2"


def _get_progress() -> PuzzleProgress:
    if _STATE_KEY not in st.session_state or not isinstance(
        st.session_state[_STATE_KEY], PuzzleProgress
    ):
        st.session_state[_STATE_KEY] = PuzzleProgress()
    return st.session_state[_STATE_KEY]


def _reset_progress() -> None:
    st.session_state[_STATE_KEY] = PuzzleProgress()


def _legal_moves_uci(fen: str) -> List[str]:
    board = chess.Board(fen)
    return [m.uci() for m in board.legal_moves]


def render_puzzle_trainer(puzzles: List[PuzzleDefinition]) -> None:
    """Render the new JS-board-based puzzle trainer."""

    if not puzzles:
        st.info("No puzzles to show.")
        return

    progress = _get_progress()

    # Clamp index
    if progress.current_index < 0:
        progress.current_index = 0
    if progress.current_index >= len(puzzles):
        progress.current_index = len(puzzles) - 1

    puzzle = puzzles[progress.current_index]

    # Reset accepted position when switching puzzles
    if progress.active_puzzle_index != progress.current_index:
        progress.active_puzzle_index = progress.current_index
        progress.last_result = None
        progress.last_uci = None
        progress.current_fen = puzzle.fen

    board_fen = progress.current_fen or puzzle.fen
    board = chess.Board(board_fen)

    # Keep orientation fixed per puzzle (based on side-to-move in the initial FEN)
    try:
        base_turn = chess.Board(puzzle.fen).turn
        orientation = "white" if base_turn == chess.WHITE else "black"
    except Exception:
        orientation = "white"
    side_to_move = "w" if board.turn == chess.WHITE else "b"

    legal_moves = _legal_moves_uci(board_fen)

    highlights = {
        "correct_squares": [],
        "incorrect_squares": [],
    }

    if progress.last_result == "correct" and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            highlights["correct_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    if progress.last_result == "incorrect" and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            highlights["incorrect_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    cols = st.columns([2, 1])
    with cols[0]:
        hint = "Drag a piece or click-to-move." if progress.last_result is None else ""
        uci = render_chessboard(
            fen=board_fen,
            legal_moves=legal_moves,
            orientation=orientation,
            side_to_move=side_to_move,
            highlights=highlights,
            hint=hint,
            key=f"chessboard_v2_{progress.current_index}",
        )

        # Process move only once
        if uci and uci != progress.last_uci:
            progress.last_uci = uci
            progress.last_result = None

            # Validate legality with python-chess
            try:
                move = chess.Move.from_uci(uci)
            except Exception:
                progress.last_result = "incorrect"
                st.rerun()

            if move not in board.legal_moves:
                progress.last_result = "incorrect"
                st.rerun()

            # Validate correctness against solution
            expected = puzzle.solution_moves[0]
            if uci == expected:
                board.push(move)
                progress.current_fen = board.fen()
                progress.last_result = "correct"
                progress.solved += 1
            else:
                progress.last_result = "incorrect"

            st.rerun()

    with cols[1]:
        st.subheader("Puzzle")
        st.write(f"Theme: **{puzzle.theme}**")
        st.write(f"Difficulty: **{puzzle.difficulty}**")
        st.write(f"Progress: **{progress.current_index + 1} / {len(puzzles)}**")
        st.write(f"Solved: **{progress.solved}**")

        if progress.last_result == "correct":
            st.success("Correct!")
        elif progress.last_result == "incorrect":
            st.error("Incorrect. Try again.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Next", use_container_width=True):
                progress.current_index = min(progress.current_index + 1, len(puzzles) - 1)
                # active_puzzle_index reset will run on next render
                st.rerun()
        with c2:
            if st.button("Reset", use_container_width=True):
                progress.last_result = None
                progress.last_uci = None
                progress.current_fen = puzzle.fen
                st.rerun()

        if st.button("Restart Session", use_container_width=True):
            _reset_progress()
            st.rerun()
