"""
Evaluation Trainer - Guess the position evaluation.

Users are shown a position (eval between -3 and +3) and must guess
if it's losing, slightly worse, equal, slightly better, or winning
from the perspective of the player to move.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import chess
import streamlit as st

from ui.chessboard_component import render_chessboard


# Evaluation ranges (from perspective of side to move)
# Positive = good for side to move, negative = bad
EVAL_RANGES = {
    "losing": (-3.0, -1.8),       # -3.0 to -1.8
    "slightly_worse": (-1.8, -0.6),  # -1.8 to -0.6
    "equal": (-0.6, 0.6),         # -0.6 to 0.6
    "slightly_better": (0.6, 1.8),   # 0.6 to 1.8
    "winning": (1.8, 3.0),        # 1.8 to 3.0
}

BUTTON_LABELS = {
    "losing": "😰 Losing",
    "slightly_worse": "😕 Slightly Worse",
    "equal": "😐 Equal",
    "slightly_better": "🙂 Slightly Better",
    "winning": "😄 Winning",
}


@dataclass
class EvalPosition:
    """A position for evaluation training."""
    fen: str
    eval_cp: int  # Centipawns from WHITE's perspective (standard)
    source_game: Optional[str] = None
    move_number: Optional[int] = None


@dataclass
class EvalTrainerState:
    """State for the evaluation trainer."""
    positions: List[EvalPosition] = field(default_factory=list)
    current_index: int = 0
    score: int = 0
    total_attempts: int = 0
    last_guess: Optional[str] = None
    revealed: bool = False
    session_id: str = ""  # Track when positions were loaded


_STATE_KEY = "eval_trainer_state_v1"


def _get_state() -> EvalTrainerState:
    """Get or create trainer state."""
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = EvalTrainerState()
    return st.session_state[_STATE_KEY]


def _reset_state() -> None:
    """Reset trainer state."""
    st.session_state[_STATE_KEY] = EvalTrainerState()


def _get_eval_for_side_to_move(eval_cp: int, turn: chess.Color) -> float:
    """
    Convert eval (from white's perspective) to eval from side-to-move perspective.
    Returns eval in pawns (not centipawns).
    """
    eval_pawns = eval_cp / 100.0
    if turn == chess.BLACK:
        eval_pawns = -eval_pawns
    return eval_pawns


def _classify_eval(eval_pawns: float) -> str:
    """Classify an evaluation into a category."""
    if eval_pawns <= -1.8:
        return "losing"
    elif eval_pawns <= -0.6:
        return "slightly_worse"
    elif eval_pawns <= 0.6:
        return "equal"
    elif eval_pawns <= 1.8:
        return "slightly_better"
    else:
        return "winning"


def _format_eval(eval_pawns: float) -> str:
    """Format evaluation for display."""
    if eval_pawns > 0:
        return f"+{eval_pawns:.1f}"
    return f"{eval_pawns:.1f}"


def _extract_positions_from_games(games: List[Dict[str, Any]], max_positions: int = 50) -> List[EvalPosition]:
    """
    Extract positions with evaluations from analyzed games.
    Distributes positions evenly across EVAL_RANGES categories.
    """
    positions_by_category = {
        "losing": [],
        "slightly_worse": [],
        "equal": [],
        "slightly_better": [],
        "winning": []
    }
    
    if not games:
        return []
    
    # Limit iterations to speed up extraction for large game sets
    max_moves_per_game = 30
    max_games_to_scan = 200  # Stop scanning after enough positions found
    moves_scanned = 0
    
    for game in games:
        if len([p for positions in positions_by_category.values() for p in positions]) > max_positions * 3:
            break  # Stop if we have enough positions
            
        moves = game.get("moves", [])
        if not moves or not isinstance(moves, list):
            continue
        
        # Limit moves per game for performance
        moves = moves[:max_moves_per_game]
        game_id = game.get("game_id", "unknown")
        
        for move_data in moves:
            if not isinstance(move_data, dict):
                continue
            
            eval_cp = move_data.get("eval_before")
            fen = move_data.get("fen_before")
            move_num = move_data.get("move_num", 0)
            
            if eval_cp is None or fen is None:
                continue
            
            # Convert cp to pawns
            eval_pawns = eval_cp / 100.0
            
            # Filter to defined range
            if abs(eval_pawns) > 3.0:
                continue
            
            position = EvalPosition(
                fen=fen,
                eval_cp=eval_cp,
                source_game=game_id,
                move_number=move_num,
            )
            
            # Categorize by evaluation using EVAL_RANGES
            if eval_pawns < EVAL_RANGES["losing"][1]:
                positions_by_category["losing"].append(position)
            elif eval_pawns < EVAL_RANGES["slightly_worse"][1]:
                positions_by_category["slightly_worse"].append(position)
            elif eval_pawns <= EVAL_RANGES["equal"][1]:
                positions_by_category["equal"].append(position)
            elif eval_pawns <= EVAL_RANGES["slightly_better"][1]:
                positions_by_category["slightly_better"].append(position)
            else:
                positions_by_category["winning"].append(position)
    
    # Distribute positions evenly across categories
    target_per_category = max_positions // 5
    all_positions = []
    
    # Shuffle each category separately and take equal amounts
    for category in positions_by_category.values():
        random.shuffle(category)
        all_positions.extend(category[:target_per_category])
    
    # Fill any remaining slots from categories with extras
    filled = len(all_positions)
    if filled < max_positions:
        extras = []
        for category in positions_by_category.values():
            extras.extend(category[target_per_category:])
        random.shuffle(extras)
        all_positions.extend(extras[:max_positions - filled])
    
    # Final shuffle to randomize order
    random.shuffle(all_positions)
    return all_positions[:max_positions]


def _generate_sample_positions() -> List[EvalPosition]:
    """
    Generate sample positions when no games are available.
    These are classic positions with known evaluations.
    """
    # A variety of positions with different evaluations
    samples = [
        # Equal positions
        EvalPosition(fen="r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", eval_cp=30),  # Italian Game
        EvalPosition(fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", eval_cp=10),  # Open Game
        EvalPosition(fen="rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2", eval_cp=40),  # Alekhine's Defense
        
        # Slightly better for white
        EvalPosition(fen="r1bqkb1r/pppp1ppp/2n2n2/4p3/2BPP3/5N2/PPP2PPP/RNBQK2R b KQkq - 0 4", eval_cp=80),
        EvalPosition(fen="r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R b KQkq - 0 5", eval_cp=100),
        
        # Slightly worse for white
        EvalPosition(fen="r1bqkb1r/pppp1ppp/2n5/4p3/2BnP3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4", eval_cp=-70),
        EvalPosition(fen="rnbqkb1r/ppp2ppp/4pn2/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR w KQkq d6 0 4", eval_cp=-90),
        
        # Winning for white
        EvalPosition(fen="r1b1kb1r/pppp1ppp/2n2n2/4N3/2B1P3/8/PPPP1PPP/RNBQK2R b KQkq - 0 4", eval_cp=200),
        EvalPosition(fen="r1bqk2r/pppp1Bpp/2n2n2/2b1p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 0 4", eval_cp=250),
        
        # Losing for white (winning for black)
        EvalPosition(fen="rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3", eval_cp=-200),
        EvalPosition(fen="r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 4", eval_cp=-180),
        
        # More varied positions
        EvalPosition(fen="r2qkb1r/ppp2ppp/2n1bn2/3pp3/4P3/1PN2N2/PBPP1PPP/R2QKB1R w KQkq - 2 6", eval_cp=50),
        EvalPosition(fen="r1bq1rk1/ppp2ppp/2n1pn2/3p4/1bPP4/2NBPN2/PP3PPP/R1BQK2R w KQ - 2 7", eval_cp=120),
        EvalPosition(fen="rnbq1rk1/ppp1bppp/4pn2/3p4/2PP4/2N2N2/PP2PPPP/R1BQKB1R w KQ - 4 5", eval_cp=-60),
        EvalPosition(fen="r1bqk2r/ppppbppp/2n2n2/4p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 1 5", eval_cp=70),
    ]
    
    random.shuffle(samples)
    return samples


def render_eval_trainer(games: List[Dict[str, Any]] = None) -> None:
    """
    Render the evaluation trainer UI.
    
    Args:
        games: Optional list of analyzed games to extract positions from
    """
    st.header("🎯 Evaluation Trainer")
    st.caption("Guess the position's evaluation from the side to move's perspective")
    
    state = _get_state()
    
    # Generate a unique session identifier for this render
    import hashlib
    current_session = hashlib.md5(str(id(games) if games else "sample").encode()).hexdigest()[:8]
    
    # Initialize or refresh positions if this is a new session
    if not state.positions or state.session_id != current_session:
        if games:
            state.positions = _extract_positions_from_games(games)
        
        # Fall back to sample positions if no games or no valid positions extracted
        if not state.positions:
            state.positions = _generate_sample_positions()
        
        # Shuffle positions for variety
        random.shuffle(state.positions)
        state.session_id = current_session
        state.current_index = 0
        state.score = 0
        state.total_attempts = 0
    
    # Sidebar controls
    with st.sidebar:
        st.subheader("⚙️ Eval Trainer")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Score", f"{state.score}/{state.total_attempts}")
        with col2:
            accuracy = (state.score / state.total_attempts * 100) if state.total_attempts > 0 else 0
            st.metric("Accuracy", f"{accuracy:.0f}%")
        
        if st.button("🔄 New Set", use_container_width=True):
            _reset_state()
            st.rerun()
        
        st.markdown("---")
        st.markdown("""
        **Evaluation Ranges:**
        - 😰 **Losing**: < -1.8
        - 😕 **Slightly Worse**: -1.8 to -0.6
        - 😐 **Equal**: -0.6 to +0.6
        - 🙂 **Slightly Better**: +0.6 to +1.8
        - 😄 **Winning**: > +1.8
        """)
    
    # Check if we have positions
    if not state.positions:
        st.warning("No positions available. Analyze some games first, or try the sample positions.")
        return
    
    # Current position
    if state.current_index >= len(state.positions):
        # Completed all positions
        st.success(f"🎉 Training complete! Final score: {state.score}/{state.total_attempts}")
        accuracy = (state.score / state.total_attempts * 100) if state.total_attempts > 0 else 0
        
        if accuracy >= 80:
            st.balloons()
            st.info("🏆 Excellent evaluation skills!")
        elif accuracy >= 60:
            st.info("👍 Good job! Keep practicing to improve.")
        else:
            st.info("💪 Keep practicing - evaluation intuition improves with time!")
        
        if st.button("🔄 Start New Training", use_container_width=True):
            _reset_state()
            st.rerun()
        return
    
    position = state.positions[state.current_index]
    board = chess.Board(position.fen)
    
    # Determine side to move and eval from their perspective
    side_to_move = board.turn
    side_name = "White" if side_to_move == chess.WHITE else "Black"
    eval_for_side = _get_eval_for_side_to_move(position.eval_cp, side_to_move)
    correct_category = _classify_eval(eval_for_side)
    
    # Layout
    col_board, col_info = st.columns([2, 1])
    
    with col_board:
        # Show board from perspective of side to move
        orientation = "white" if side_to_move == chess.WHITE else "black"
        
        render_chessboard(
            fen=position.fen,
            legal_moves=[],  # No moves - just viewing
            orientation=orientation,
            side_to_move="w" if side_to_move == chess.WHITE else "b",
            key=f"eval_board_{state.current_index}",
        )
    
    with col_info:
        st.subheader(f"Position {state.current_index + 1}/{len(state.positions)}")
        
        # Whose move
        st.markdown(f"### {side_name} to move")
        
        if position.move_number:
            st.caption(f"Move {position.move_number}")
        
        st.markdown("---")
        
        # Guess buttons (only if not revealed)
        if not state.revealed:
            st.markdown("**What's the evaluation?**")
            
            # Create button grid
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button(BUTTON_LABELS["losing"], key="btn_losing", use_container_width=True):
                    state.last_guess = "losing"
                    state.revealed = True
                    state.total_attempts += 1
                    if state.last_guess == correct_category:
                        state.score += 1
                    st.rerun()
                
                if st.button(BUTTON_LABELS["slightly_worse"], key="btn_sw", use_container_width=True):
                    state.last_guess = "slightly_worse"
                    state.revealed = True
                    state.total_attempts += 1
                    if state.last_guess == correct_category:
                        state.score += 1
                    st.rerun()
                
                if st.button(BUTTON_LABELS["equal"], key="btn_equal", use_container_width=True):
                    state.last_guess = "equal"
                    state.revealed = True
                    state.total_attempts += 1
                    if state.last_guess == correct_category:
                        state.score += 1
                    st.rerun()
            
            with col2:
                if st.button(BUTTON_LABELS["slightly_better"], key="btn_sb", use_container_width=True):
                    state.last_guess = "slightly_better"
                    state.revealed = True
                    state.total_attempts += 1
                    if state.last_guess == correct_category:
                        state.score += 1
                    st.rerun()
                
                if st.button(BUTTON_LABELS["winning"], key="btn_winning", use_container_width=True):
                    state.last_guess = "winning"
                    state.revealed = True
                    state.total_attempts += 1
                    if state.last_guess == correct_category:
                        state.score += 1
                    st.rerun()
        
        else:
            # Show result
            is_correct = state.last_guess == correct_category
            
            if is_correct:
                st.success("✅ Correct!")
            else:
                st.error("❌ Incorrect")
            
            # Show actual eval
            st.markdown(f"**Actual eval:** {_format_eval(eval_for_side)}")
            st.markdown(f"**Category:** {BUTTON_LABELS[correct_category]}")
            
            if not is_correct:
                st.caption(f"You guessed: {BUTTON_LABELS[state.last_guess]}")
            
            st.markdown("---")
            
            # Next button
            if st.button("➡️ Next Position", use_container_width=True, type="primary"):
                state.current_index += 1
                state.revealed = False
                state.last_guess = None
                st.rerun()
