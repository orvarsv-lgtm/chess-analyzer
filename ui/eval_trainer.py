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
    all_eligible_positions: List[EvalPosition] = field(default_factory=list)  # Pool to sample from
    current_index: int = 0
    score: int = 0
    total_attempts: int = 0
    last_guess: Optional[str] = None
    revealed: bool = False
    games_fingerprint: str = ""  # Track which games positions came from


_STATE_KEY = "eval_trainer_state_v1"


def _get_state() -> EvalTrainerState:
    """Get or create trainer state."""
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = EvalTrainerState()
    return st.session_state[_STATE_KEY]


def _reset_state() -> None:
    """Reset trainer state - keeps eligible positions but samples new ones."""
    old_state = st.session_state.get(_STATE_KEY)
    new_state = EvalTrainerState()
    
    # Preserve the pool of eligible positions and fingerprint
    if old_state:
        all_eligible = getattr(old_state, 'all_eligible_positions', [])
        new_state.all_eligible_positions = all_eligible
        new_state.games_fingerprint = getattr(old_state, 'games_fingerprint', "")
        
        # Sample new positions from the pool
        if all_eligible:
            sample_size = min(50, len(all_eligible))
            new_state.positions = random.sample(all_eligible, sample_size)
            random.shuffle(new_state.positions)
    
    st.session_state[_STATE_KEY] = new_state


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


def _extract_positions_from_games(games: List[Dict[str, Any]], max_positions: int = 500) -> List[EvalPosition]:
    """
    Extract complex positions with evaluations from analyzed games.
    Focuses on middlegame/endgame positions (move 12+) for complexity.
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
    
    for game in games:
        # Use moves_table which contains the analysis data
        moves = game.get("moves_table", [])
        if not moves or not isinstance(moves, list):
            continue

        # Attach FENs from per-game FEN list if available, then reconstruct from SAN if needed
        fens_after_ply = game.get("fens_after_ply", [])
        if fens_after_ply and isinstance(fens_after_ply, list):
            moves = _attach_fens_from_game(moves, fens_after_ply)

        moves = _ensure_fens_in_moves_table(moves)
        if not moves:
            continue
        
        game_id = game.get("index", game.get("game_id", "unknown"))
        
        for move_data in moves:
            if not isinstance(move_data, dict):
                continue
            
            # Get eval (score_cp) and FEN from moves_table structure
            eval_cp = move_data.get("score_cp")
            fen = move_data.get("fen")
            ply = move_data.get("ply", 0)
            move_num = (ply + 1) // 2  # Convert ply to move number
            
            if eval_cp is None or fen is None:
                continue
            
            # Skip opening positions (move 1-11) - focus on complex middlegame/endgame
            if move_num < 12:
                continue
            
            # Convert cp to pawns
            eval_pawns = eval_cp / 100.0
            
            # Filter to defined range
            if abs(eval_pawns) > 3.0:
                continue
            
            position = EvalPosition(
                fen=fen,
                eval_cp=eval_cp,
                source_game=str(game_id),
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


def _ensure_fens_in_moves_table(moves_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure moves_table entries include FENs by reconstructing from SAN if needed."""
    if not moves_table:
        return []

    # If we already have FENs, return as-is
    if any(isinstance(m, dict) and m.get("fen") for m in moves_table):
        return moves_table

    board = chess.Board()
    enriched = []
    for move_data in moves_table:
        if not isinstance(move_data, dict):
            continue
        san = move_data.get("move_san")
        if not san:
            continue
        try:
            board.push_san(san)
        except Exception:
            # Stop reconstruction if SAN is invalid
            break
        enriched_move = dict(move_data)
        enriched_move["fen"] = board.fen()
        enriched.append(enriched_move)

    return enriched


def _attach_fens_from_game(moves_table: List[Dict[str, Any]], fens_after_ply: List[str]) -> List[Dict[str, Any]]:
    """Attach FENs to moves_table using per-ply FENs when available."""
    if not moves_table or not fens_after_ply:
        return moves_table

    enriched = []
    for move_data in moves_table:
        if not isinstance(move_data, dict):
            continue
        ply = move_data.get("ply")
        fen = None
        if isinstance(ply, int) and ply > 0 and ply - 1 < len(fens_after_ply):
            fen = fens_after_ply[ply - 1]

        enriched_move = dict(move_data)
        if fen:
            enriched_move["fen"] = fen
        enriched.append(enriched_move)

    return enriched


def render_eval_trainer(games: List[Dict[str, Any]] = None) -> None:
    """
    Render the evaluation trainer UI.
    
    Args:
        games: Optional list of analyzed games to extract positions from
    """
    st.header("🎯 Evaluation Trainer")
    st.caption("Guess the position's evaluation from the side to move's perspective")
    
    # Track navigation - detect when user just arrived at this tab
    last_view_key = "last_rendered_view"
    current_view = "Evaluations"
    previous_view = st.session_state.get(last_view_key, "")
    just_entered = previous_view != current_view
    st.session_state[last_view_key] = current_view
    
    state = _get_state()
    
    # Track which games we're working with (by game count and first game ID)
    games_fingerprint = ""
    games_with_moves = 0
    total_moves_found = 0
    
    if games:
        game_ids = [str(g.get("index", g.get("game_id", ""))) for g in games[:5]]
        games_fingerprint = f"{len(games)}_{','.join(game_ids)}"
        
        # Count games that have moves_table entries with FENs, SANs, or fens_after_ply
        for g in games:
            moves_table = g.get("moves_table", [])
            fens_after_ply = g.get("fens_after_ply", [])
            if moves_table and isinstance(moves_table, list):
                has_fen = any(isinstance(m, dict) and m.get("fen") for m in moves_table)
                has_san = any(isinstance(m, dict) and m.get("move_san") for m in moves_table)
                has_fens_list = isinstance(fens_after_ply, list) and len(fens_after_ply) > 0
                if has_fen or has_san or has_fens_list:
                    games_with_moves += 1
                    total_moves_found += len(moves_table)
    
    # Check if we need to rebuild the position pool:
    # Different games being analyzed (user ran new analysis)
    previous_fingerprint = getattr(state, 'games_fingerprint', None)
    different_games = previous_fingerprint != games_fingerprint
    
    if different_games or not getattr(state, 'all_eligible_positions', None):
        # Extract ALL eligible positions from games
        all_eligible = []
        if games:
            all_eligible = _extract_positions_from_games(games, max_positions=500)
        
        # Store all eligible positions for random sampling
        if all_eligible:
            state.all_eligible_positions = all_eligible
            state.using_sample = False
        else:
            state.all_eligible_positions = _generate_sample_positions()
            state.using_sample = True
        state.games_fingerprint = games_fingerprint
        just_entered = True  # Force new sample when games change
    
    # Pick a fresh random sample when first entering the trainer
    if just_entered and getattr(state, 'all_eligible_positions', None):
        pool = state.all_eligible_positions
        sample_size = min(50, len(pool))
        state.positions = random.sample(pool, sample_size)
        random.shuffle(state.positions)
        state.current_index = 0
        state.score = 0
        state.total_attempts = 0
    elif not state.positions:
        # Fallback if no positions
        state.positions = _generate_sample_positions()
        state.using_sample = True
    
    # Show info about position source
    using_sample = getattr(state, 'using_sample', True)
    pool_size = len(getattr(state, 'all_eligible_positions', []))
    
    if using_sample:
        st.info(
            f"📚 Using sample positions (no game positions found with evaluation data). "
            f"Games: {len(games) if games else 0}, with moves_table: {games_with_moves}"
        )
    else:
        st.success(f"🎮 Using {pool_size} positions from your analyzed games")
    
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
