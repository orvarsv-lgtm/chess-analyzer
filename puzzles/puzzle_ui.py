"""
Puzzle UI Components for Streamlit

Interactive chessboard rendering and puzzle solving interface.
Uses python-chess SVG rendering with custom Streamlit components.

All UI is deterministic - no AI/LLM, move validation is rule-based.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, FrozenSet
from functools import lru_cache
import base64
import io
import re

import chess
import chess.svg
import streamlit as st

from .puzzle_types import Puzzle, PuzzleSession, PuzzleAttempt, Difficulty, PuzzleType
from .difficulty import get_difficulty_emoji, get_difficulty_description


# =============================================================================
# CONSTANTS
# =============================================================================

# Board rendering size (pixels)
BOARD_SIZE = 400

# Highlight colors for squares
HIGHLIGHT_LAST_MOVE = "#aaa23a88"  # Yellow-ish for last move
HIGHLIGHT_CORRECT = "#4ade8088"   # Green for correct
HIGHLIGHT_INCORRECT = "#ef444488"  # Red for incorrect
HIGHLIGHT_LEGAL = "#3b82f688"     # Blue for legal moves
HIGHLIGHT_SELECTED = "#7fa650"    # Green for selected piece
HIGHLIGHT_LEGAL_DOT = "#00000033" # Semi-transparent for move dots

# Square colors
LIGHT_SQUARE = "#f0d9b5"
DARK_SQUARE = "#b58863"

# Piece unicode symbols (global for reuse)
PIECE_SYMBOLS = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚',
}

# Free tier limits
IS_PREMIUM_DEFAULT = False
MAX_FREE_PUZZLES = 5


# =============================================================================
# PUZZLE UI STATE MANAGEMENT
# =============================================================================


@dataclass
class PuzzleUIState:
    """
    Manages UI state for puzzle solving in Streamlit.
    
    Uses st.session_state for persistence across reruns.
    """
    session_key: str = "puzzle_session"
    
    @classmethod
    def initialize(cls, puzzles: List[Puzzle], is_premium: bool = False) -> PuzzleSession:
        """
        Initialize or retrieve puzzle session from Streamlit state.
        
        Args:
            puzzles: List of puzzles to use for this session
            is_premium: Whether user has premium access
        
        Returns:
            PuzzleSession object
        """
        key = cls.session_key
        
        # Check if we need to reset (new puzzles)
        if key in st.session_state:
            existing = st.session_state[key]
            if isinstance(existing, PuzzleSession):
                # Check if puzzles changed
                existing_ids = {p.puzzle_id for p in existing.puzzles}
                new_ids = {p.puzzle_id for p in puzzles}
                if existing_ids == new_ids:
                    # Same puzzles, return existing session
                    return existing
        
        # Create new session
        session = PuzzleSession(
            puzzles=puzzles,
            is_premium=is_premium,
        )
        st.session_state[key] = session
        return session
    
    @classmethod
    def get_session(cls) -> Optional[PuzzleSession]:
        """Get existing session if available."""
        return st.session_state.get(cls.session_key)
    
    @classmethod
    def clear_session(cls) -> None:
        """Clear the puzzle session."""
        if cls.session_key in st.session_state:
            del st.session_state[cls.session_key]
    
    @classmethod
    def get_selected_square(cls) -> Optional[int]:
        """Get currently selected square."""
        return st.session_state.get("puzzle_selected_square")
    
    @classmethod
    def set_selected_square(cls, square: Optional[int]) -> None:
        """Set selected square."""
        st.session_state["puzzle_selected_square"] = square
    
    @classmethod
    def clear_selected_square(cls) -> None:
        """Clear selected square."""
        if "puzzle_selected_square" in st.session_state:
            del st.session_state["puzzle_selected_square"]
    
    @classmethod
    def get_last_result(cls) -> Optional[str]:
        """Get last move result ('correct', 'incorrect', or None)."""
        return st.session_state.get("puzzle_last_result")
    
    @classmethod
    def set_last_result(cls, result: Optional[str]) -> None:
        """Set last move result."""
        st.session_state["puzzle_last_result"] = result
    
    @classmethod
    def clear_last_result(cls) -> None:
        """Clear last result."""
        if "puzzle_last_result" in st.session_state:
            del st.session_state["puzzle_last_result"]
    
    @classmethod
    def get_solution_sequence_pos(cls) -> int:
        """Get current position in multi-move puzzle solution sequence (0-indexed)."""
        return st.session_state.get("puzzle_solution_pos", 0)
    
    @classmethod
    def set_solution_sequence_pos(cls, pos: int) -> None:
        """Set position in solution sequence."""
        st.session_state["puzzle_solution_pos"] = pos
    
    @classmethod
    def reset_solution_sequence_pos(cls) -> None:
        """Reset to start of solution sequence."""
        st.session_state["puzzle_solution_pos"] = 0

    @classmethod
    def get_opponent_played_msg(cls) -> Optional[str]:
        return st.session_state.get("puzzle_opponent_played")

    @classmethod
    def set_opponent_played_msg(cls, msg: Optional[str]) -> None:
        if msg:
            st.session_state["puzzle_opponent_played"] = msg
        elif "puzzle_opponent_played" in st.session_state:
            del st.session_state["puzzle_opponent_played"]

    @classmethod
    def clear_opponent_played_msg(cls) -> None:
        if "puzzle_opponent_played" in st.session_state:
            del st.session_state["puzzle_opponent_played"]


# =============================================================================
# PERFORMANCE-OPTIMIZED LEGAL MOVE COMPUTATION
# =============================================================================


@lru_cache(maxsize=256)
def _get_legal_destinations_cached(fen: str, from_square: int) -> FrozenSet[int]:
    """
    Get legal destination squares for a piece (cached for performance).
    
    Args:
        fen: Board position FEN string
        from_square: Square index of the piece
        
    Returns:
        Frozenset of legal destination square indices
    """
    board = chess.Board(fen)
    destinations = set()
    for move in board.legal_moves:
        if move.from_square == from_square:
            destinations.add(move.to_square)
    return frozenset(destinations)


@lru_cache(maxsize=256)
def _get_pieces_with_moves_cached(fen: str) -> FrozenSet[int]:
    """
    Get squares of pieces that have at least one legal move (cached).
    
    Args:
        fen: Board position FEN string
        
    Returns:
        Frozenset of square indices with movable pieces
    """
    board = chess.Board(fen)
    pieces_with_moves = set()
    for move in board.legal_moves:
        pieces_with_moves.add(move.from_square)
    return frozenset(pieces_with_moves)


def get_legal_destinations(board: chess.Board, from_square: int) -> set:
    """Get all legal destination squares for a piece."""
    return set(_get_legal_destinations_cached(board.fen(), from_square))


def get_pieces_with_moves(board: chess.Board) -> set:
    """Get squares of pieces that have at least one legal move."""
    return set(_get_pieces_with_moves_cached(board.fen()))


# =============================================================================
# CHESSBOARD RENDERING
# =============================================================================


def render_board_svg(
    board: chess.Board,
    size: int = BOARD_SIZE,
    flipped: bool = False,
    last_move: Optional[chess.Move] = None,
    highlight_squares: Optional[dict] = None,
    arrows: Optional[List[Tuple[int, int, str]]] = None,
) -> str:
    """
    Render chess board as SVG.
    
    Args:
        board: Chess board to render
        size: Size in pixels
        flipped: Whether to flip board (black perspective)
        last_move: Optional last move to highlight
        highlight_squares: Dict of square -> color for highlighting
        arrows: List of (from_sq, to_sq, color) tuples for arrows
    
    Returns:
        SVG string
    """
    # Build fill dict for square highlights
    fill = {}
    if highlight_squares:
        for sq, color in highlight_squares.items():
            fill[sq] = color
    
    # Build arrows list
    svg_arrows = []
    if arrows:
        for from_sq, to_sq, color in arrows:
            svg_arrows.append(chess.svg.Arrow(from_sq, to_sq, color=color))
    
    # Render SVG
    svg = chess.svg.board(
        board,
        size=size,
        flipped=flipped,
        lastmove=last_move,
        fill=fill,
        arrows=svg_arrows,
    )
    
    return svg


def display_board(
    board: chess.Board,
    flipped: bool = False,
    highlight_squares: Optional[dict] = None,
    arrows: Optional[List[Tuple[int, int, str]]] = None,
    key: str = "puzzle_board",
) -> None:
    """
    Display chess board in Streamlit.
    
    Uses st.markdown with HTML to embed SVG.
    """
    svg = render_board_svg(
        board=board,
        size=BOARD_SIZE,
        flipped=flipped,
        highlight_squares=highlight_squares,
        arrows=arrows,
    )
    
    # Display SVG in centered container
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; margin: 1rem 0;">
            {svg}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _encode_svg_base64(svg: str) -> str:
    """Encode SVG as base64 for img tag."""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


# =============================================================================
# MOVE INPUT AND VALIDATION
# =============================================================================


def validate_move(board: chess.Board, move_input: str) -> Tuple[bool, Optional[chess.Move], str]:
    """
    Validate a move input against the current position.
    
    Accepts both SAN (e.g., "Nf3") and UCI (e.g., "g1f3") notation.
    
    Args:
        board: Current board position
        move_input: User's move input string
    
    Returns:
        (is_valid, move_object, message)
    """
    move_input = move_input.strip()
    if not move_input:
        return False, None, "Please enter a move"
    
    # Try SAN first
    try:
        move = board.parse_san(move_input)
        if move in board.legal_moves:
            return True, move, ""
        else:
            return False, None, "Illegal move"
    except chess.InvalidMoveError:
        pass
    except chess.AmbiguousMoveError:
        return False, None, "Ambiguous move - please be more specific"
    except Exception:
        pass
    
    # Try UCI
    try:
        move = board.parse_uci(move_input)
        if move in board.legal_moves:
            return True, move, ""
        else:
            return False, None, "Illegal move"
    except Exception:
        pass
    
    return False, None, f"Could not parse move: {move_input}"


def check_puzzle_answer(
    board: chess.Board,
    user_move: chess.Move,
    correct_move_san: str,
    solution_moves: Optional[List[str]] = None,
    solution_index: int = 0,
) -> Tuple[bool, str]:
    """
    Check if user's move matches the puzzle's correct answer.
    
    Simple logic:
    1. Get the expected move (from solution_moves or correct_move_san)
    2. Compare user's move UCI to expected move UCI
    3. Return correct/incorrect
    
    Args:
        board: Current board position
        user_move: User's move object
        correct_move_san: Correct answer in SAN (the best move)
        solution_moves: Full solution sequence (UCI moves) for multi-move puzzles
        solution_index: Current position in solution sequence (0-indexed)
    
    Returns:
        (is_correct, message)
    """
    user_uci = user_move.uci()
    
    # Determine what the expected move is
    expected_uci = None
    expected_san = None
    expected_display = correct_move_san  # Default display
    
    # For multi-move puzzles, get the expected move at current index
    if solution_moves and len(solution_moves) > 0:
        if 0 <= solution_index < len(solution_moves):
            expected_uci = solution_moves[solution_index]
            # Try to get SAN for display and comparison
            try:
                expected_move_obj = chess.Move.from_uci(expected_uci)
                if expected_move_obj in board.legal_moves:
                    expected_san = board.san(expected_move_obj)
                    expected_display = expected_san
            except Exception:
                expected_display = expected_uci
    
    # If no expected_uci from solution_moves, parse from correct_move_san
    if not expected_uci:
        try:
            expected_move_obj = board.parse_san(correct_move_san)
            expected_uci = expected_move_obj.uci()
            expected_san = correct_move_san
            expected_display = correct_move_san
        except Exception:
            # Last resort: just use the SAN as-is for comparison
            expected_uci = None
            expected_san = correct_move_san
            expected_display = correct_move_san
    
    # Compare moves - UCI comparison is primary
    if expected_uci and user_uci == expected_uci:
        return True, "Correct! ✅"
    
    # Also try direct SAN comparison as fallback (use expected_san, NOT correct_move_san)
    if expected_san:
        try:
            user_san = board.san(user_move)
            clean_user = re.sub(r"[+#?!]+$", "", user_san).strip()
            clean_expected = re.sub(r"[+#?!]+$", "", expected_san).strip()
            if clean_user == clean_expected:
                return True, "Correct! ✅"
        except Exception:
            pass
        pass
    
    return False, f"Incorrect. The best move was {expected_display}"


def _parse_solution_move(board: chess.Board, move_str: str) -> Optional[chess.Move]:
    candidate = (move_str or "").strip()
    if not candidate:
        return None
    if re.match(r"^[a-h][1-8][a-h][1-8][qrbn]?$", candidate):
        try:
            move = chess.Move.from_uci(candidate)
            if move in board.legal_moves:
                return move
        except Exception:
            pass
    try:
        return board.parse_san(candidate)
    except Exception:
        try:
            cleaned = re.sub(r"[+#?!]+$", "", candidate)
            return board.parse_san(cleaned)
        except Exception:
            return None


def _build_board_for_sequence(puzzle: Puzzle, sequence_pos: int) -> chess.Board:
    board = chess.Board(puzzle.fen)
    if not puzzle.solution_moves:
        return board
    limit = min(sequence_pos, len(puzzle.solution_moves))
    for idx in range(limit):
        move = _parse_solution_move(board, puzzle.solution_moves[idx])
        if not move:
            break
        if move not in board.legal_moves:
            break
        board.push(move)
    return board


def get_legal_moves_display(board: chess.Board) -> List[str]:
    """Get list of legal moves in SAN notation."""
    return [board.san(move) for move in board.legal_moves]


def get_square_from_name(name: str) -> Optional[int]:
    """Convert square name (e.g., 'e4') to square index."""
    try:
        return chess.parse_square(name.lower())
    except Exception:
        return None


# =============================================================================
# PUZZLE INFO DISPLAY
# =============================================================================


def render_puzzle_info(puzzle: Puzzle) -> None:
    """Display puzzle metadata."""
    # Show forcing position indicator prominently if applicable
    if puzzle.is_forcing:
        st.success(f"⚡ **FORCING POSITION!** Only one move keeps the advantage (gap: {puzzle.move_gap_cp}cp)")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        emoji = get_difficulty_emoji(puzzle.difficulty)
        st.metric("Difficulty", f"{emoji} {puzzle.difficulty.value.title()}")
    
    with col2:
        type_display = puzzle.puzzle_type.value.replace("_", " ").title()
        st.metric("Type", type_display)
    
    with col3:
        st.metric("Phase", puzzle.phase.title())
    
    # Show eval loss
    st.caption(f"Eval loss: {puzzle.eval_loss_cp}cp | Move {puzzle.move_number} | {puzzle.side_to_move.title()} to move")


def render_puzzle_hint(puzzle: Puzzle) -> None:
    """Display a hint for the puzzle based on tactical patterns."""
    
    # Try to use tactical pattern for better hint
    if puzzle.tactical_patterns:
        patterns = puzzle.tactical_patterns
        
        # Get composite pattern for specific hint
        composite = patterns.get("composite_pattern")
        if composite:
            pattern_hints = {
                "fork": "💡 Look for a move that attacks two pieces at once!",
                "pin": "💡 Can you pin a piece to the king or a more valuable piece?",
                "skewer": "💡 Attack a valuable piece that must move, exposing something behind!",
                "back_rank_mate": "💡 The back rank is weak - can you exploit it?",
                "smothered_mate": "💡 The king is surrounded by its own pieces!",
                "discovered_check": "💡 Move a piece to reveal an attack on the king!",
                "double_check": "💡 Two pieces can give check at once!",
                "removing_the_guard": "💡 Capture the piece that's defending something important!",
                "zwischenzug": "💡 Before recapturing, is there an in-between move?",
                "windmill": "💡 Repeated discovered attacks can win material!",
                "greek_gift": "💡 A bishop sacrifice on h7/h2 might work!",
            }
            hint = pattern_hints.get(composite)
            if hint:
                st.info(hint)
                return
        
        # Get primary constraint for hint
        primary_constraints = patterns.get("primary_constraints", [])
        if primary_constraints:
            constraint = primary_constraints[0].get("constraint", "")
            constraint_hints = {
                "double_attack": "💡 One piece can attack two targets!",
                "defender_pinned": "💡 A key defender cannot move!",
                "defender_overloaded": "💡 A piece has too many duties!",
                "king_in_check": "💡 Give check and see what happens!",
                "king_confined": "💡 The king has very few escape squares!",
                "no_flight_squares": "💡 A piece is trapped with nowhere to go!",
                "piece_trapped": "💡 Look for a trapped piece!",
            }
            hint = constraint_hints.get(constraint)
            if hint:
                st.info(hint)
                return
    
    # Fallback to basic hints
    hints = {
        PuzzleType.MISSED_TACTIC: "💡 Look for captures, checks, or forks!",
        PuzzleType.ENDGAME_TECHNIQUE: "💡 Think about pawn promotion or piece activity",
        PuzzleType.OPENING_ERROR: "💡 Consider development and center control",
    }
    
    hint = hints.get(puzzle.puzzle_type, "💡 Find the best move!")
    st.info(hint)


# =============================================================================
# MAIN PUZZLE UI COMPONENTS
# =============================================================================


def render_puzzle_board(
    puzzle: Puzzle,
    show_solution: bool = False,
    last_result: Optional[str] = None,
) -> None:
    """
    Render the puzzle board with appropriate highlighting.
    
    Args:
        puzzle: The puzzle to display
        show_solution: Whether to show the solution arrow
        last_result: 'correct', 'incorrect', or None
    """
    try:
        board = chess.Board(puzzle.fen)
    except Exception:
        st.error(f"Invalid FEN: {puzzle.fen}")
        return
    
    # Determine if board should be flipped (black perspective)
    flipped = puzzle.side_to_move == "black"
    
    # Build highlights
    highlights = {}
    arrows = []
    
    if show_solution:
        # Show solution with arrow
        try:
            solution_move = board.parse_san(puzzle.best_move_san)
            arrows.append((solution_move.from_square, solution_move.to_square, "#22c55e"))
            highlights[solution_move.from_square] = HIGHLIGHT_CORRECT
            highlights[solution_move.to_square] = HIGHLIGHT_CORRECT
        except Exception:
            pass
    elif last_result == "correct":
        # Show green highlight
        try:
            solution_move = board.parse_san(puzzle.best_move_san)
            highlights[solution_move.from_square] = HIGHLIGHT_CORRECT
            highlights[solution_move.to_square] = HIGHLIGHT_CORRECT
        except Exception:
            pass
    elif last_result == "incorrect":
        # Show red highlight on wrong squares (if available)
        pass  # Could track the wrong move and highlight it
    
    # Display board
    display_board(
        board=board,
        flipped=flipped,
        highlight_squares=highlights,
        arrows=arrows,
    )


def render_puzzle_controls(
    session: PuzzleSession,
) -> Optional[str]:
    """
    Render puzzle controls and handle user input.
    
    Returns the user's move input if submitted, None otherwise.
    
    Args:
        session: Current puzzle session
    
    Returns:
        User's move string if submitted, None otherwise
    """
    puzzle = session.current_puzzle
    if puzzle is None:
        st.warning("No puzzle available")
        return None
    
    # Check free limit
    if session.is_at_limit:
        st.warning("🔒 Free puzzle limit reached!")
        st.info(
            f"You've completed {session.MAX_FREE_PUZZLES} free puzzles. "
            "Upgrade to premium for unlimited puzzle access!"
        )
        _render_upgrade_placeholder()
        return None
    
    # Move input
    st.subheader("Your Move")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        move_input = st.text_input(
            "Enter move (e.g., Nf3 or g1f3)",
            key="puzzle_move_input",
            placeholder="Type your move...",
        )
    
    with col2:
        submit = st.button("Submit", type="primary", key="puzzle_submit")
    
    if submit and move_input:
        return move_input
    
    return None


def render_puzzle_result(
    is_correct: bool,
    message: str,
    puzzle: Puzzle,
) -> None:
    """Display the result of a puzzle attempt with tactical pattern analysis."""
    if is_correct:
        st.success(message)
        # Show tactical pattern explanation after correct answer
        if puzzle.tactical_patterns:
            patterns = puzzle.tactical_patterns
            pattern_name = patterns.get("pattern_summary", "")
            why_it_works = patterns.get("why_it_works", "")
            
            if pattern_name or why_it_works:
                explanation = f"**{pattern_name}**" if pattern_name else ""
                if why_it_works:
                    explanation += f" - {why_it_works}" if explanation else why_it_works
                st.info(f"💡 {explanation}")
        elif puzzle.explanation:
            st.info(f"💡 **Why this works:** {puzzle.explanation}")
        st.balloons()
    else:
        st.error(message)
        
        # Show the played move that was a mistake
        st.caption(f"The mistake played was: **{puzzle.played_move_san}**")
        
        # Show tactical pattern explanation for the correct move
        if puzzle.tactical_patterns:
            patterns = puzzle.tactical_patterns
            pattern_name = patterns.get("pattern_summary", "")
            why_it_works = patterns.get("why_it_works", "")
            
            if pattern_name or why_it_works:
                explanation = f"**{pattern_name}**" if pattern_name else ""
                if why_it_works:
                    explanation += f" - {why_it_works}" if explanation else why_it_works
                st.info(f"💡 **The key idea:** {explanation}")
        elif puzzle.explanation:
            st.info(f"💡 **Explanation:** {puzzle.explanation}")


def render_puzzle_navigation(session: PuzzleSession) -> Tuple[bool, bool, bool]:
    """
    Render navigation controls between puzzles.
    
    Returns:
        (next_clicked, prev_clicked, reset_clicked)
    """
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    prev_clicked = False
    next_clicked = False
    reset_clicked = False
    
    with col1:
        prev_disabled = session.current_index <= 0
        if st.button("⬅️ Back", disabled=prev_disabled, key="puzzle_prev"):
            prev_clicked = True
    
    with col2:
        st.markdown(f"<div style='text-align:center;padding-top:5px;'><b>{session.current_index + 1}</b> / {session.available_puzzle_count}</div>", unsafe_allow_html=True)
    
    with col3:
        next_disabled = (
            session.current_index >= session.total_puzzles - 1 or
            session.is_at_limit
        )
        if st.button("Next ➡️", disabled=next_disabled, key="puzzle_next"):
            next_clicked = True
    
    with col4:
        if st.button("🔄 Reset", key="puzzle_reset_nav"):
            reset_clicked = True
    
    return next_clicked, prev_clicked, reset_clicked


def render_puzzle_stats(session: PuzzleSession) -> None:
    """Display session statistics."""
    stats = session.get_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Puzzles Solved", stats["puzzles_solved"])
    
    with col2:
        st.metric("Attempted", stats["puzzles_attempted"])
    
    with col3:
        total = stats["total_attempts"]
        solved = stats["puzzles_solved"]
        rate = f"{(solved/total)*100:.0f}%" if total > 0 else "0%"
        st.metric("Success Rate", rate)
    
    with col4:
        remaining = session.available_puzzle_count - session.current_index
        st.metric("Remaining", remaining)


def _render_upgrade_placeholder() -> None:
    """Render placeholder for premium upgrade."""
    st.markdown(
        """
        <div style="
            border: 2px dashed #f59e0b;
            border-radius: 8px;
            padding: 2rem;
            text-align: center;
            background-color: #fef3c7;
            margin: 1rem 0;
        ">
            <h3 style="color: #d97706; margin: 0;">🏆 Upgrade to Premium</h3>
            <p style="color: #92400e;">Get unlimited puzzles and advanced analytics!</p>
            <p style="color: #78350f; font-size: 0.9em;">(Premium features coming soon)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# MAIN PUZZLE PAGE COMPONENT
# =============================================================================


def _load_solution_moves_for_puzzle(puzzle: Puzzle) -> Optional[List[str]]:
    """
    Load the full solution line for a puzzle from the global store.
    
    Args:
        puzzle: The puzzle to load the solution for
    
    Returns:
        List of UCI moves if available, else None
    """
    if puzzle.solution_moves:
        # Already loaded
        return puzzle.solution_moves
    
    try:
        from puzzles.global_supabase_store import get_cached_solution_line
        # Compute puzzle_key same way as in global_puzzle_store.py
        puzzle_key = f"{puzzle.source_game_index}_{puzzle.move_number}_{puzzle.puzzle_id}"
        solution_line = get_cached_solution_line(puzzle_key)
        return solution_line
    except Exception:
        # Supabase not available or solution not found
        return None


def render_puzzle_page(
    puzzles: List[Puzzle],
    is_premium: bool = False,
) -> None:
    """
    Render the complete puzzle solving page with a single interactive SVG board.
    
    Main entry point for the puzzle UI.
    
    Args:
        puzzles: List of puzzles available to solve
        is_premium: Whether user has premium access
    """
    st.header("♟️ Chess Puzzles")
    st.caption("Practice tactical patterns from your analyzed games")
    
    if not puzzles:
        st.info("No puzzles available. Analyze some games to generate puzzles!")
        return
    
    # Initialize session
    session = PuzzleUIState.initialize(puzzles, is_premium)
    puzzle = session.current_puzzle
    
    if puzzle is None:
        st.info("All puzzles completed! 🎉")
        render_puzzle_stats(session)
        if st.button("🔄 Reset Puzzles", key="puzzle_reset_all"):
            session.reset()
            PuzzleUIState.clear_selected_square()
            PuzzleUIState.reset_solution_sequence_pos()
            st.rerun()
        return
    
    # Load solution_moves from Supabase if not already loaded
    if not puzzle.solution_moves:
        solution_moves = _load_solution_moves_for_puzzle(puzzle)
        if solution_moves:
            puzzle.solution_moves = solution_moves
    
    # Check if already solved current puzzle
    current_attempts = session.get_attempts_for_current()
    already_solved = any(a.is_correct for a in current_attempts)
    last_result = PuzzleUIState.get_last_result()
    opponent_played_msg = PuzzleUIState.get_opponent_played_msg()
    selected_square = PuzzleUIState.get_selected_square()
    
    # Free limit check
    if session.is_at_limit:
        st.warning("🔒 Free puzzle limit reached!")
        st.info(f"You've completed {session.MAX_FREE_PUZZLES} free puzzles.")
        _render_upgrade_placeholder()
        return
    
    # Layout
    col_board, col_info = st.columns([2, 1])
    
    with col_info:
        # Puzzle info
        render_puzzle_info(puzzle)
        
        # Hint button
        if st.checkbox("💡 Show hint", key="puzzle_show_hint"):
            render_puzzle_hint(puzzle)

        # Explanation (deterministic, derived from the position)
        if st.checkbox("📖 Show explanation", key="puzzle_show_explanation"):
            # Try new tactical pattern explanation first
            if puzzle.tactical_patterns:
                patterns = puzzle.tactical_patterns
                
                # Show pattern name prominently
                pattern_name = patterns.get("pattern_summary", "")
                if pattern_name:
                    st.markdown(f"### 🎯 {pattern_name}")
                
                # Show composite pattern if different
                composite = patterns.get("composite_pattern")
                if composite and composite != pattern_name.lower().replace(" ", "_"):
                    st.markdown(f"**Pattern:** {composite.replace('_', ' ').title()}")
                
                # Show why it works
                why_it_works = patterns.get("why_it_works")
                if why_it_works:
                    st.info(f"💡 **Why it works:** {why_it_works}")
                
                # Show primary constraints
                primary_constraints = patterns.get("primary_constraints", [])
                if primary_constraints:
                    with st.expander("🔍 Constraint Analysis", expanded=False):
                        for c in primary_constraints[:3]:
                            desc = c.get("description", "")
                            conf = c.get("confidence", 0)
                            constraint_type = c.get("constraint", "").replace("_", " ").title()
                            if desc:
                                st.markdown(f"- **{constraint_type}** ({conf:.0%}): {desc}")
                
                # Show outcome
                outcome = patterns.get("primary_outcome")
                if outcome:
                    st.markdown(f"**Outcome:** {outcome.replace('_', ' ').title()}")
            
            elif puzzle.explanation:
                st.info(puzzle.explanation)
            else:
                st.info("Explanation will appear once puzzles are regenerated.")
    
    with col_board:
        try:
            sequence_pos = PuzzleUIState.get_solution_sequence_pos()
            board = _build_board_for_sequence(puzzle, sequence_pos)
        except Exception:
            st.error(f"Invalid FEN: {puzzle.fen}")
            return
        
        flipped = puzzle.side_to_move == "black"
        show_solution = already_solved or last_result == "incorrect"
        
        # Single interactive board
        move_made = render_interactive_svg_board(
            board=board,
            flipped=flipped,
            selected_square=selected_square,
            show_solution=show_solution,
            solution_move_san=puzzle.best_move_san,
        )
        
        # Process move if made
        if move_made and not already_solved:
            from_sq, to_sq = move_made
            
            # Create move (check for pawn promotion)
            move = chess.Move(from_sq, to_sq)
            piece = board.piece_at(from_sq)
            
            if piece and piece.piece_type == chess.PAWN:
                to_rank = chess.square_rank(to_sq)
                if (piece.color == chess.WHITE and to_rank == 7) or \
                   (piece.color == chess.BLACK and to_rank == 0):
                    move = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
            
            if move in board.legal_moves:
                solution_index = PuzzleUIState.get_solution_sequence_pos()
                is_correct, result_msg = check_puzzle_answer(
                    board, move, puzzle.best_move_san,
                    solution_moves=puzzle.solution_moves,
                    solution_index=solution_index,
                )
                user_san = board.san(move)
                session.record_attempt(user_san, is_correct)
                
                # If correct and multi-move puzzle, advance sequence
                if is_correct and puzzle.solution_moves:
                    next_pos = solution_index + 1
                    opponent_msg = None
                    puzzle_complete = False
                    
                    if next_pos < len(puzzle.solution_moves):
                        # There's an opponent move - play it automatically
                        board_after = board.copy()
                        board_after.push(move)
                        opponent_move = _parse_solution_move(board_after, puzzle.solution_moves[next_pos])
                        if opponent_move and opponent_move in board_after.legal_moves:
                            opponent_san = board_after.san(opponent_move)
                            opponent_msg = f"Opponent has played {opponent_san}."
                            board_after.push(opponent_move)
                            next_pos += 1
                            
                            # Check if there are more player moves after opponent's move
                            if next_pos >= len(puzzle.solution_moves):
                                # No more moves - puzzle complete!
                                puzzle_complete = True
                        else:
                            # Opponent move couldn't be parsed - puzzle complete
                            puzzle_complete = True
                    else:
                        # No more moves in solution - puzzle complete
                        puzzle_complete = True
                    
                    PuzzleUIState.set_solution_sequence_pos(next_pos)
                    PuzzleUIState.set_opponent_played_msg(opponent_msg)
                    
                    # Set result based on whether puzzle is complete
                    if puzzle_complete:
                        PuzzleUIState.set_last_result("correct")
                    else:
                        PuzzleUIState.set_last_result("continue")
                elif is_correct:
                    # Single-move puzzle - correct means complete
                    PuzzleUIState.set_last_result("correct")
                    PuzzleUIState.clear_opponent_played_msg()
                else:
                    # Incorrect move
                    PuzzleUIState.set_last_result("incorrect")
                    PuzzleUIState.clear_opponent_played_msg()
                
                PuzzleUIState.clear_selected_square()
                st.rerun()
    
    # DEBUG: Show state values
    st.caption(f"DEBUG: last_result={last_result}, solution_moves={puzzle.solution_moves}, seq_pos={PuzzleUIState.get_solution_sequence_pos()}")
    
    # Show result if available
    if last_result:
        st.divider()
        if last_result == "correct":
            # Puzzle fully complete
            render_puzzle_result(True, "Correct! ✅", puzzle)
        elif last_result == "continue":
            # Intermediate correct move - puzzle continues
            st.success("Good move! ✅")
            if opponent_played_msg:
                st.info(opponent_played_msg)
            st.caption("Continue solving...")
        else:
            # Incorrect
            render_puzzle_result(
                False,
                f"Incorrect. The best move was **{puzzle.best_move_san}**",
                puzzle,
            )
    
    # Navigation
    st.divider()
    next_clicked, prev_clicked, reset_clicked = render_puzzle_navigation(session)
    
    if next_clicked:
        if session.advance_to_next():
            PuzzleUIState.clear_last_result()
            PuzzleUIState.clear_selected_square()
            PuzzleUIState.reset_solution_sequence_pos()  # Reset for new puzzle
            PuzzleUIState.clear_opponent_played_msg()
            st.rerun()
    
    if prev_clicked:
        if session.current_index > 0:
            session.current_index -= 1
            PuzzleUIState.clear_last_result()
            PuzzleUIState.clear_selected_square()
            PuzzleUIState.reset_solution_sequence_pos()  # Reset for new puzzle
            PuzzleUIState.clear_opponent_played_msg()
            st.rerun()
    
    if reset_clicked:
        session.reset()
        PuzzleUIState.clear_last_result()
        PuzzleUIState.clear_selected_square()
        PuzzleUIState.reset_solution_sequence_pos()  # Reset for new puzzle
        PuzzleUIState.clear_opponent_played_msg()
        st.rerun()
    
    # Stats at bottom
    st.divider()
    render_puzzle_stats(session)


# =============================================================================
# INTERACTIVE SQUARE SELECTION (Single Board - Click-to-move)
# =============================================================================


def render_interactive_chessboard(
    board: chess.Board,
    flipped: bool = False,
    selected_square: Optional[int] = None,
    show_solution: bool = False,
    solution_move_san: Optional[str] = None,
    board_id: str = "puzzle",
) -> Optional[Tuple[int, int]]:
    """
    Render a SINGLE interactive chessboard with proper chess colors.
    
    This is ONE board - the colored squares ARE the clickable buttons.
    Uses custom CSS to style Streamlit buttons to look like chess squares.
    
    Args:
        board: Current chess board position
        flipped: Whether to flip the board (black perspective)
        selected_square: Currently selected square (if any)
        show_solution: Whether to show the solution arrow
        solution_move_san: The solution move in SAN notation
        
    Returns:
        (from_square, to_square) tuple if a complete move was made, None otherwise
    """
    # Pre-compute legal moves
    pieces_with_moves = get_pieces_with_moves(board)
    legal_destinations = set()
    if selected_square is not None:
        legal_destinations = get_legal_destinations(board, selected_square)
    
    player_color = board.turn
    
    # Solution squares
    solution_from = None
    solution_to = None
    if show_solution and solution_move_san:
        try:
            solution_move = board.parse_san(solution_move_san)
            solution_from = solution_move.from_square
            solution_to = solution_move.to_square
        except Exception:
            pass
    
    # Instructions
    if show_solution:
        st.caption("✅ Solution shown below:")
    elif selected_square is not None:
        piece = board.piece_at(selected_square)
        piece_name = chess.piece_name(piece.piece_type).title() if piece else "Piece"
        sq_name = chess.square_name(selected_square).upper()
        st.success(f"**{piece_name}** on **{sq_name}** selected → Click a blue square to move")
    else:
        whose_turn = "White" if player_color == chess.WHITE else "Black"
        st.info(f"**{whose_turn} to move** → Click a piece to select it")
    
    # CSS to style the board
    st.markdown("""
    <style>
    /* Make all puzzle buttons look like chess squares */
    [data-testid="column"] > div > div > div > button {
        height: 50px !important;
        min-height: 50px !important;
        padding: 0 !important;
        font-size: 28px !important;
        border-radius: 0 !important;
        border: none !important;
        margin: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    clicked_square = None
    move_made = None
    
    ranks = range(7, -1, -1) if not flipped else range(8)
    files_order = list(range(8) if not flipped else range(7, -1, -1))
    
    # Add file labels (a-h)
    file_labels = [chr(ord('a') + f) for f in files_order]
    label_cols = st.columns(8)
    for i, label in enumerate(file_labels):
        with label_cols[i]:
            st.markdown(f"<div style='text-align:center;color:#666;font-weight:bold;'>{label}</div>", unsafe_allow_html=True)
    
    # Render the board - each row is a rank
    for rank in ranks:
        cols = st.columns(8)
        for col_idx, file in enumerate(files_order):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            
            # Determine square appearance
            is_light = (rank + file) % 2 == 1
            is_selected = square == selected_square
            is_legal_dest = square in legal_destinations
            is_solution = show_solution and (square == solution_from or square == solution_to)
            
            # Choose background color
            if is_solution:
                bg_color = "#86efac"  # Light green for solution
            elif is_selected:
                bg_color = "#7fa650"  # Green for selected
            elif is_legal_dest:
                bg_color = "#93c5fd"  # Light blue for legal moves
            elif is_light:
                bg_color = LIGHT_SQUARE
            else:
                bg_color = DARK_SQUARE
            
            # Piece symbol
            piece_symbol = PIECE_SYMBOLS.get(piece.symbol(), '') if piece else ''
            display_text = piece_symbol if piece_symbol else " "
            
            with cols[col_idx]:
                # Apply custom style to this specific button
                btn_key = f"{board_id}_{square}_{selected_square}_{show_solution}"
                
                # Custom CSS for this square
                st.markdown(f"""
                <style>
                [data-testid="stButton"][data-key="{btn_key}"] button {{
                    background-color: {bg_color} !important;
                    color: #000 !important;
                }}
                [data-testid="stButton"][data-key="{btn_key}"] button:hover {{
                    background-color: {bg_color} !important;
                    opacity: 0.9;
                }}
                </style>
                """, unsafe_allow_html=True)
                
                if not show_solution:
                    clicked = st.button(
                        display_text,
                        key=btn_key,
                        help=chess.square_name(square).upper(),
                        width='stretch',
                    )
                    if clicked:
                        clicked_square = square
                else:
                    # Non-interactive when showing solution
                    st.button(
                        display_text,
                        key=btn_key,
                        help=chess.square_name(square).upper(),
                        width='stretch',
                        disabled=True,
                    )
    
    # Add rank label on the right
    st.markdown(f"<div style='text-align:right;color:#666;font-size:0.8em;'>Ranks 1-8</div>", unsafe_allow_html=True)
    
    # Process click
    if clicked_square is not None and not show_solution:
        if selected_square is not None and clicked_square in legal_destinations:
            move_made = (selected_square, clicked_square)
            PuzzleUIState.clear_selected_square()
        elif clicked_square in pieces_with_moves:
            clicked_piece = board.piece_at(clicked_square)
            if clicked_piece and clicked_piece.color == player_color:
                new_selection = None if clicked_square == selected_square else clicked_square
                if new_selection is not None:
                    PuzzleUIState.set_selected_square(new_selection)
                else:
                    PuzzleUIState.clear_selected_square()
                st.rerun()
        elif selected_square is not None:
            PuzzleUIState.clear_selected_square()
            st.rerun()
    
    return move_made


# Aliases for compatibility
render_interactive_svg_board = render_interactive_chessboard
render_single_interactive_board = render_interactive_chessboard


def render_clickable_board(puzzle: Puzzle, on_move_callback: callable) -> None:
    """Legacy wrapper."""
    try:
        board = chess.Board(puzzle.fen)
    except Exception:
        st.error(f"Invalid FEN: {puzzle.fen}")
        return
    
    selected = PuzzleUIState.get_selected_square()
    flipped = puzzle.side_to_move == "black"
    
    result = render_interactive_chessboard(
        board=board,
        flipped=flipped,
        selected_square=selected,
    )
    
    if result and on_move_callback:
        on_move_callback(result[0], result[1])


def render_square_buttons(board: chess.Board, selected: Optional[int] = None) -> Optional[int]:
    """Legacy fallback."""
    clicked_square = None
    legal_destinations = get_legal_destinations(board, selected) if selected else set()
    
    for rank in range(7, -1, -1):
        cols = st.columns(8)
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            piece_symbol = PIECE_SYMBOLS.get(piece.symbol(), '') if piece else ''
            
            with cols[file]:
                if st.button(piece_symbol or "·", key=f"sq_{square}", help=chess.square_name(square)):
                    clicked_square = square
    
    return clicked_square
