"""
Interactive Game Replayer with Chessboard (NEW: #4)

Features:
- Step through moves with forward/back buttons
- Click on move list to jump to position
- Evaluation graph showing advantage over time
- Highlight blunders/mistakes in move list
- Show engine suggestion on hover
"""

import streamlit as st
import chess
import chess.pgn
import chess.svg
from typing import List, Dict, Any, Optional
import io


def render_game_replayer(game_data: Dict[str, Any], move_evals: List[Dict[str, Any]]):
    """
    Render interactive game replayer.
    
    Args:
        game_data: Game metadata (white, black, result, opening, etc.)
        move_evals: List of move evaluations with CP scores
    """
    st.subheader("🎮 Game Replayer")
    
    # Parse game into board positions
    moves_pgn = game_data.get('moves_pgn', '')
    if not moves_pgn:
        st.warning("No moves available for this game")
        return
    
    # Create board and move list
    board = chess.Board()
    positions = [board.fen()]  # Starting position
    san_moves = []
    
    for move_san in moves_pgn.split():
        try:
            move = board.parse_san(move_san)
            board.push(move)
            positions.append(board.fen())
            san_moves.append(move_san)
        except:
            continue
    
    max_ply = len(san_moves)
    
    # Initialize session state for current position
    if 'replay_ply' not in st.session_state:
        st.session_state.replay_ply = 0
    
    # Ensure replay_ply is an integer and bounds check (in case it's from a previous game)
    try:
        current_ply = int(st.session_state.replay_ply)
        if current_ply > max_ply or current_ply < 0:
            current_ply = 0
            st.session_state.replay_ply = 0
    except (TypeError, ValueError):
        current_ply = 0
        st.session_state.replay_ply = 0
    
    # ======= LAYOUT =======
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Chessboard display
        current_fen = positions[current_ply]
        
        # Get current move eval for later display
        current_eval = None
        if current_ply > 0 and current_ply <= len(move_evals):
            current_eval = move_evals[current_ply - 1]
        
        # Quality badge above chessboard
        if current_eval:
            cp_loss = current_eval.get('actual_cp_loss') or current_eval.get('cp_loss', 0)
            quality = _classify_move_quality(cp_loss)
            quality_colors = {
                'Best': '#28a745',
                'Excellent': '#5cb85c',
                'Good': '#90EE90',
                'Inaccuracy': '#ffc107',
                'Mistake': '#fd7e14',
                'Blunder': '#dc3545'
            }
            quality_color = quality_colors.get(quality, '#6c757d')
            st.markdown(
                f'<div style="background-color: {quality_color}; color: white; '
                f'padding: 8px 16px; border-radius: 6px; text-align: center; '
                f'font-weight: bold; font-size: 18px; margin-bottom: 10px;">{quality} ({cp_loss}cp)</div>',
                unsafe_allow_html=True
            )
        
        # Render chessboard using simple SVG display
        board_at_ply = chess.Board(current_fen)
        
        # Display using chess.svg (simpler, no interactive component)
        try:
            svg_board = chess.svg.board(
                board=board_at_ply,
                size=400,
                orientation=chess.WHITE if game_data.get('focus_color') == 'white' else chess.BLACK
            )
            st.markdown(f'<div style="display: flex; justify-content: center;">{svg_board}</div>', unsafe_allow_html=True)
        except Exception:
            # Fallback to text representation
            st.code(str(board_at_ply))
        
        # Move navigation with slider
        st.write("")  # Spacing
        
        move_num = (current_ply + 1) // 2
        turn = "White" if current_ply % 2 == 0 else "Black"
        
        # Navigation buttons
        btn_cols = st.columns([1, 1])
        with btn_cols[0]:
            if st.button("◀️ Back", use_container_width=True, disabled=(current_ply == 0), key=f"back_{id(game_data)}"):
                st.session_state.replay_ply = max(0, current_ply - 1)
                st.rerun()
        with btn_cols[1]:
            if st.button("Next ▶️", use_container_width=True, disabled=(current_ply >= max_ply), key=f"next_{id(game_data)}"):
                st.session_state.replay_ply = min(max_ply, current_ply + 1)
                st.rerun()
        
        # Single slider for navigation
        st.session_state.replay_ply = st.slider(
            f"Move {move_num} - {turn}",
            min_value=0,
            max_value=max_ply,
            value=current_ply,
            key=f"replay_slider_{id(game_data)}"
        )
        
        # Current position info
        if current_ply > 0 and current_eval:
            st.write("---")
            eval_cols = st.columns(4)
            
            with eval_cols[0]:
                eval_before = current_eval.get('eval_before')
                if eval_before is not None:
                    st.metric("Eval Before", f"{eval_before:+d}cp")
            
            with eval_cols[1]:
                cp_loss = current_eval.get('cp_loss', 0)
                st.metric("CP Loss", f"{cp_loss}cp")
            
            with eval_cols[2]:
                eval_after = current_eval.get('eval_after')
                if eval_after is not None:
                    st.metric("Eval After", f"{eval_after:+d}cp")
            
            with eval_cols[3]:
                phase = current_eval.get('phase', 'middlegame')
                st.metric("Phase", phase.title())
            
            # Show best move suggestion
            best_move = current_eval.get('best_move_san')
            if best_move:
                st.info(f"💡 **Best Move:** `{best_move}`")
            
            # Show engine suggestion for blunders/mistakes
            if current_eval.get('blunder_type') in ['blunder', 'mistake']:
                blunder_subtype = current_eval.get('blunder_subtype', 'Unknown')
                st.error(f"⚠️ {current_eval['blunder_type'].title()}: {blunder_subtype.replace('_', ' ').title()}")
    
    with col2:
        # Move list with clickable moves
        st.write("**📋 Move List**")
        
        # Create scrollable container
        move_list_html = _generate_move_list_html(san_moves, move_evals, current_ply, game_data.get('color'))
        
        st.markdown(
            f"""
            <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px;">
                {move_list_html}
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Evaluation graph
        st.write("---")
        st.write("**📊 Evaluation Graph**")
        
        _render_eval_graph(move_evals)


def _get_highlight_squares(ply: int, san_moves: List[str], current_eval: Optional[Dict]) -> List[str]:
    """Get squares to highlight (last move)."""
    if ply == 0 or ply > len(san_moves):
        return []
    
    # Parse the last move to get from/to squares
    # This is simplified - proper implementation would track UCI moves
    return []


def _generate_move_list_html(san_moves: List[str], move_evals: List[Dict], current_ply: int, user_color: str) -> str:
    """Generate HTML for move list with color-coded quality and clickable moves."""
    html = "<table style='width: 100%; font-size: 14px;'>"
    
    for i in range(0, len(san_moves), 2):
        move_num = (i // 2) + 1
        html += f"<tr>"
        html += f"<td style='text-align: right; padding: 4px; font-weight: bold;'>{move_num}.</td>"
        
        # White's move
        white_move = san_moves[i]
        white_eval = move_evals[i] if i < len(move_evals) else {}
        white_cp_loss = white_eval.get('actual_cp_loss') or white_eval.get('cp_loss', 0)
        white_quality = _classify_move_quality(white_cp_loss)
        white_color = _get_quality_color(white_quality)
        white_style = f"background-color: {white_color}; padding: 4px 8px; border-radius: 3px; color: white; text-shadow: -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000; font-weight: bold; cursor: pointer; user-select: none;"
        if i + 1 == current_ply:
            white_style += " border: 2px solid #000;"
        
        html += f"<td style='{white_style}' data-ply='{i + 1}' title='{white_quality} ({white_cp_loss}cp loss)'>{white_move}</td>"
        
        # Black's move
        if i + 1 < len(san_moves):
            black_move = san_moves[i + 1]
            black_eval = move_evals[i + 1] if i + 1 < len(move_evals) else {}
            black_cp_loss = black_eval.get('actual_cp_loss') or black_eval.get('cp_loss', 0)
            black_quality = _classify_move_quality(black_cp_loss)
            black_color = _get_quality_color(black_quality)
            black_style = f"background-color: {black_color}; padding: 4px 8px; border-radius: 3px; color: white; text-shadow: -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000; font-weight: bold; cursor: pointer; user-select: none;"
            if i + 2 == current_ply:
                black_style += " border: 2px solid #000;"
            
            html += f"<td style='{black_style}' data-ply='{i + 2}' title='{black_quality} ({black_cp_loss}cp loss)'>{black_move}</td>"
        else:
            html += "<td></td>"
        
        html += "</tr>"
    
    html += "</table>"
    return html


def _get_quality_color(quality: str) -> str:
    """Get background color for move quality."""
    colors = {
        'Best': '#4CAF50',       # Rich green
        'Excellent': '#8BC34A',  # Light green
        'Good': '#CDDC39',       # Lime
        'Inaccuracy': '#FFEB3B', # Yellow
        'Mistake': '#FF9800',    # Orange
        'Blunder': '#F44336',    # Red
    }
    return colors.get(quality, '#FFFFFF')


def _classify_move_quality(cp_loss: int) -> str:
    """Classify move quality based on centipawn loss."""
    if cp_loss is None or cp_loss < 0:
        return "Unknown"
    elif cp_loss <= 10:
        return "Best"
    elif cp_loss <= 20:
        return "Excellent"
    elif cp_loss <= 40:
        return "Good"
    elif cp_loss <= 90:
        return "Inaccuracy"
    elif cp_loss <= 200:
        return "Mistake"
    else:
        return "Blunder"


def _render_eval_graph(move_evals: List[Dict]):
    """Render evaluation graph (CP over moves)."""
    import pandas as pd
    
    if not move_evals:
        st.info("No evaluation data available")
        return
    
    # Extract evals - use score_cp field from moves_table
    evals = []
    for i, move_eval in enumerate(move_evals):
        score_cp = move_eval.get('score_cp')
        if score_cp is not None and abs(score_cp) < 9000:  # Filter out mate scores
            evals.append({
                'Move': i + 1,
                'Evaluation': score_cp
            })
    
    if not evals:
        st.info("No evaluation data available")
        return
    
    df = pd.DataFrame(evals)
    
    # Create line chart
    st.line_chart(df.set_index('Move')['Evaluation'], height=200)
    st.caption("Positive = White advantage | Negative = Black advantage")


def render_game_replayer_simple(moves_pgn: str, move_evals: List[Dict[str, Any]], game_info: Dict[str, Any]):
    """
    Simplified game replayer without heavy dependencies.
    
    Use this if the custom chessboard component is not available.
    """
    st.subheader("🎮 Game Replayer (Simplified)")
    
    # Split into two columns: board (text) and moves
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # Initialize position index
        if 'replay_ply' not in st.session_state:
            st.session_state.replay_ply = 0
        
        # Parse moves
        san_moves = moves_pgn.split()
        max_ply = len(san_moves)
        
        # Build board position
        board = chess.Board()
        for i in range(st.session_state.replay_ply):
            if i < len(san_moves):
                try:
                    move = board.parse_san(san_moves[i])
                    board.push(move)
                except:
                    break
        
        # Display board as ASCII (fallback)
        st.code(str(board), language=None)
        
        # Navigation
        nav_cols = st.columns(3)
        with nav_cols[0]:
            if st.button("◀️ Prev"):
                st.session_state.replay_ply = max(0, st.session_state.replay_ply - 1)
                st.rerun()
        with nav_cols[1]:
            move_num = (st.session_state.replay_ply + 1) // 2
            st.write(f"Move {move_num}/{(max_ply + 1) // 2}")
        with nav_cols[2]:
            if st.button("Next ▶️"):
                st.session_state.replay_ply = min(max_ply, st.session_state.replay_ply + 1)
                st.rerun()
        
        # Slider
        new_ply = st.slider("Position", 0, max_ply, st.session_state.replay_ply, label_visibility="collapsed")
        if new_ply != st.session_state.replay_ply:
            st.session_state.replay_ply = new_ply
            st.rerun()
    
    with col2:
        st.write("**Move List**")
        
        # Display moves
        for i, move_san in enumerate(san_moves):
            eval_data = move_evals[i] if i < len(move_evals) else {}
            quality = eval_data.get('move_quality', 'Good')
            cp_loss = eval_data.get('cp_loss', 0)
            
            # Color code by quality
            if quality == 'Blunder':
                st.error(f"{i+1}. {move_san} (Blunder, -{cp_loss}cp)")
            elif quality == 'Mistake':
                st.warning(f"{i+1}. {move_san} (Mistake, -{cp_loss}cp)")
            elif quality == 'Inaccuracy':
                st.info(f"{i+1}. {move_san} (Inaccuracy, -{cp_loss}cp)")
            else:
                st.text(f"{i+1}. {move_san}")
