from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import chess
import streamlit as st

from puzzles.puzzle_store import PuzzleDefinition
from ui.chessboard_component import render_chessboard


@dataclass
class PuzzleProgress:
    current_index: int = 0
    solved: int = 0
    last_result: Optional[str] = None  # "correct" | "incorrect" | "continue" | None
    last_uci: Optional[str] = None
    current_fen: Optional[str] = None  # tracks accepted position
    active_puzzle_index: Optional[int] = None
    # Multi-move puzzle tracking
    solution_move_index: int = 0  # Which player move we're on (0, 2, 4, ...)
    opponent_just_moved: bool = False  # True if we just auto-played opponent's move


_STATE_KEY = "puzzle_progress_v2"


def _get_progress() -> PuzzleProgress:
    if _STATE_KEY not in st.session_state or not isinstance(
        st.session_state[_STATE_KEY], PuzzleProgress
    ):
        st.session_state[_STATE_KEY] = PuzzleProgress()
    return st.session_state[_STATE_KEY]


def _reset_progress() -> None:
    st.session_state[_STATE_KEY] = PuzzleProgress()


def _reset_puzzle_progress(progress: PuzzleProgress, puzzle_fen: str) -> None:
    """Reset progress for a new puzzle."""
    progress.last_result = None
    progress.last_uci = None
    progress.current_fen = puzzle_fen
    progress.solution_move_index = 0
    progress.opponent_just_moved = False


def _get_player_move_indices(solution_moves: List[str]) -> List[int]:
    """Get indices of player moves in solution (0, 2, 4, ...)."""
    return list(range(0, len(solution_moves), 2))


def _get_next_player_move_index(current_index: int, solution_moves: List[str]) -> Optional[int]:
    """Get the next player move index after current, or None if done."""
    next_idx = current_index + 2  # Skip opponent's response
    if next_idx < len(solution_moves):
        return next_idx
    return None


def _apply_opponent_response(board: chess.Board, solution_moves: List[str], 
                             current_player_index: int) -> Optional[str]:
    """
    Apply opponent's response move if one exists.
    
    Returns the opponent's UCI move if applied, None otherwise.
    """
    opponent_idx = current_player_index + 1
    if opponent_idx < len(solution_moves):
        opponent_uci = solution_moves[opponent_idx]
        try:
            move = chess.Move.from_uci(opponent_uci)
            if move in board.legal_moves:
                board.push(move)
                return opponent_uci
        except Exception:
            pass
    return None


def _legal_moves_uci(fen: str) -> List[str]:
    board = chess.Board(fen)
    return [m.uci() for m in board.legal_moves]


def render_puzzle_trainer(puzzles: List[PuzzleDefinition]) -> None:
    """Render the new JS-board-based puzzle trainer with multi-move support."""

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
    
    # Calculate total player moves in this puzzle
    player_move_indices = _get_player_move_indices(puzzle.solution_moves)
    total_player_moves = len(player_move_indices)
    current_player_move_num = (progress.solution_move_index // 2) + 1

    # Reset accepted position when switching puzzles
    if progress.active_puzzle_index != progress.current_index:
        progress.active_puzzle_index = progress.current_index
        _reset_puzzle_progress(progress, puzzle.fen)

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

    # Highlight opponent's last move if they just moved
    if progress.opponent_just_moved and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            # Use a neutral highlight for opponent moves (we'll show it as "correct" color)
            highlights["correct_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    cols = st.columns([2, 1])
    with cols[0]:
        # Show hint based on state
        if progress.last_result == "correct":
            hint = "Puzzle complete!"
        elif progress.opponent_just_moved:
            hint = "Your turn. Find the best move."
        elif progress.last_result is None:
            hint = "Drag a piece or click-to-move."
        else:
            hint = ""
            
        uci = render_chessboard(
            fen=board_fen,
            legal_moves=legal_moves,
            orientation=orientation,
            side_to_move=side_to_move,
            highlights=highlights,
            hint=hint,
            key=f"chessboard_v2_{progress.current_index}_{progress.solution_move_index}",
        )

        # Process move only once (and not if puzzle is complete)
        if uci and uci != progress.last_uci and progress.last_result != "correct":
            progress.last_uci = uci
            progress.opponent_just_moved = False

            # Validate legality with python-chess
            try:
                move = chess.Move.from_uci(uci)
            except Exception:
                progress.last_result = "incorrect"
                st.rerun()

            if move not in board.legal_moves:
                progress.last_result = "incorrect"
                st.rerun()

            # Check against expected move at current solution index
            expected = puzzle.solution_moves[progress.solution_move_index]
            if uci == expected:
                # Correct move!
                board.push(move)
                
                # Check if there's a continuation (opponent response + more player moves)
                next_player_idx = _get_next_player_move_index(
                    progress.solution_move_index, puzzle.solution_moves
                )
                
                if next_player_idx is not None:
                    # Apply opponent's response
                    opponent_uci = _apply_opponent_response(
                        board, puzzle.solution_moves, progress.solution_move_index
                    )
                    
                    if opponent_uci:
                        # Update state for continuation
                        progress.current_fen = board.fen()
                        progress.solution_move_index = next_player_idx
                        progress.last_uci = opponent_uci  # Store opponent's move for highlighting
                        progress.last_result = None  # Not complete yet
                        progress.opponent_just_moved = True
                    else:
                        # No valid opponent response, puzzle complete
                        progress.current_fen = board.fen()
                        progress.last_result = "correct"
                        progress.solved += 1
                else:
                    # No more moves - puzzle complete!
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
        
        # Show move progress for multi-move puzzles
        if total_player_moves > 1:
            if progress.last_result == "correct":
                st.write(f"Moves: **{total_player_moves} / {total_player_moves}** ✓")
            else:
                st.write(f"Moves: **{current_player_move_num} / {total_player_moves}**")
        
        st.write(f"Progress: **{progress.current_index + 1} / {len(puzzles)}**")
        st.write(f"Solved: **{progress.solved}**")

        show_explanation = st.checkbox("📖 Show explanation", key="puzzle_show_explanation_v2")

        if progress.last_result == "correct":
            st.success("Correct!" if total_player_moves == 1 else f"Correct! ({total_player_moves} moves)")
            if puzzle.explanation:
                st.info(f"💡 {puzzle.explanation}")
        elif progress.last_result == "incorrect":
            st.error("Incorrect. Try again.")
            if show_explanation:
                st.info(f"💡 {puzzle.explanation or 'Explanation unavailable for this puzzle.'}")
        elif progress.opponent_just_moved:
            st.info("Opponent played. Find the next best move!")

        if progress.last_result is None and not progress.opponent_just_moved and show_explanation:
            st.info(f"💡 {puzzle.explanation or 'Explanation unavailable for this puzzle.'}")

        nav1, nav2, nav3 = st.columns(3)
        with nav1:
            if st.button("Back", use_container_width=True, disabled=progress.current_index <= 0):
                progress.current_index = max(progress.current_index - 1, 0)
                st.rerun()
        with nav2:
            if st.button("Next", use_container_width=True, disabled=progress.current_index >= len(puzzles) - 1):
                progress.current_index = min(progress.current_index + 1, len(puzzles) - 1)
                st.rerun()
        with nav3:
            # Full reset: clears index, solved, last result, last move, accepted position.
            if st.button("Reset", use_container_width=True):
                _reset_progress()
                st.rerun()
