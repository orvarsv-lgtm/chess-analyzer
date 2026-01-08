"""
Quick Wins & UI Enhancements

Features:
- Export analysis to CSV
- Dark mode toggle  
- Keyboard shortcuts
- Share analysis link
- Time trouble detection
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, List
import json
from datetime import datetime
import hashlib


def add_export_button(analysis_data: Dict[str, Any], username: str):
    """Add export to CSV button (Quick Win)."""
    
    # Prepare export data
    export_rows = []
    
    for game in analysis_data.get('games', []):
        game_summary = {
            'Date': game.get('date'),
            'Opening': game.get('opening'),
            'Result': game.get('result'),
            'Player_Color': game.get('focus_color'),
            'Player_Elo': game.get('focus_player_rating'),
            'Moves': game.get('moves'),
        }
        
        # Add phase stats if available
        moves_table = game.get('moves_table', [])
        if moves_table:
            cpl_vals = [m.get('cp_loss', 0) for m in moves_table if m.get('cp_loss', 0) > 0]
            game_summary['Avg_CPL'] = round(sum(cpl_vals) / len(cpl_vals), 1) if cpl_vals else 0
            
            blunders = sum(1 for m in moves_table if m.get('cp_loss', 0) >= 300)
            mistakes = sum(1 for m in moves_table if m.get('cp_loss', 0) >= 150)
            game_summary['Blunders'] = blunders
            game_summary['Mistakes'] = mistakes
        
        export_rows.append(game_summary)
    
    df = pd.DataFrame(export_rows)
    
    # Convert to CSV
    csv = df.to_csv(index=False)
    
    # Download button
    st.download_button(
        label="📥 Export Analysis to CSV",
        data=csv,
        file_name=f"chess_analysis_{username}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        help="Download your analysis results as CSV for Excel/Google Sheets"
    )


def add_dark_mode_toggle():
    """Add dark mode toggle (Quick Win)."""
    
    # Check current theme
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = False
    
    # Toggle button in sidebar
    with st.sidebar:
        st.write("---")
        
        if st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode):
            st.session_state.dark_mode = True
            _apply_dark_mode_css()
        else:
            st.session_state.dark_mode = False


def _apply_dark_mode_css():
    """Apply custom CSS for dark mode."""
    st.markdown("""
        <style>
        /* Dark mode overrides */
        .stApp {
            background-color: #1E1E1E;
            color: #E0E0E0;
        }
        
        .stMarkdown {
            color: #E0E0E0;
        }
        
        .stDataFrame {
            background-color: #2D2D2D;
        }
        
        /* Chess board looks better on dark background */
        .chessboard {
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        
        /* Metric cards */
        .stMetric {
            background-color: #2D2D2D;
            padding: 10px;
            border-radius: 5px;
        }
        </style>
    """, unsafe_allow_html=True)


def add_keyboard_shortcuts():
    """Add keyboard shortcuts for navigation (Quick Win)."""
    
    # JavaScript for keyboard shortcuts
    st.markdown("""
        <script>
        document.addEventListener('keydown', function(event) {
            // N = Next puzzle
            if (event.key === 'n' || event.key === 'N') {
                // Find and click next button
                const nextBtn = document.querySelector('[data-testid="stButton"]:contains("Next")');
                if (nextBtn) nextBtn.click();
            }
            
            // R = Reveal answer
            if (event.key === 'r' || event.key === 'R') {
                const revealBtn = document.querySelector('[data-testid="stButton"]:contains("Reveal")');
                if (revealBtn) revealBtn.click();
            }
            
            // Space = Skip
            if (event.key === ' ') {
                event.preventDefault();
                const skipBtn = document.querySelector('[data-testid="stButton"]:contains("Skip")');
                if (skipBtn) skipBtn.click();
            }
            
            // Arrow keys for game replayer
            if (event.key === 'ArrowLeft') {
                const prevBtn = document.querySelector('[data-testid="stButton"]:contains("Back")');
                if (prevBtn) prevBtn.click();
            }
            if (event.key === 'ArrowRight') {
                const nextBtn = document.querySelector('[data-testid="stButton"]:contains("Next")');
                if (nextBtn) nextBtn.click();
            }
        });
        </script>
    """, unsafe_allow_html=True)
    
    # Show keyboard shortcuts help in sidebar
    with st.sidebar:
        with st.expander("⌨️ Keyboard Shortcuts"):
            st.markdown("""
            **Puzzle Trainer:**
            - `N` - Next puzzle
            - `R` - Reveal answer
            - `Space` - Skip puzzle
            
            **Game Replayer:**
            - `←` - Previous move
            - `→` - Next move
            """)


def create_shareable_link(analysis_data: Dict[str, Any], username: str) -> str:
    """Create shareable link to analysis (Quick Win)."""
    
    # Generate unique ID from analysis data
    data_str = json.dumps(analysis_data, sort_keys=True)
    analysis_id = hashlib.md5(data_str.encode()).hexdigest()[:12]
    
    # Store in session cache (in production, use database)
    if 'shared_analyses' not in st.session_state:
        st.session_state.shared_analyses = {}
    
    st.session_state.shared_analyses[analysis_id] = {
        'username': username,
        'data': analysis_data,
        'created_at': datetime.now().isoformat()
    }
    
    # Generate shareable URL (placeholder - would be actual domain in production)
    base_url = "http://localhost:8501"  # Replace with actual domain
    share_url = f"{base_url}/?analysis={analysis_id}"
    
    return share_url


def add_share_button(analysis_data: Dict[str, Any], username: str):
    """Add share button to generate shareable link (Quick Win)."""
    
    if st.button("🔗 Share Analysis"):
        share_url = create_shareable_link(analysis_data, username)
        
        st.success("✓ Shareable link created!")
        st.code(share_url, language=None)
        
        st.info("📋 Copy this link to share your analysis with friends or coaches")
        
        # Optional: QR code generation
        # try:
        #     import qrcode
        #     qr = qrcode.make(share_url)
        #     st.image(qr)
        # except ImportError:
        #     pass


def detect_time_trouble(move_evals: List[Dict[str, Any]], time_control: str) -> Dict[str, Any]:
    """
    Detect time trouble and blunders in time pressure (NEW: #7).
    
    Args:
        move_evals: List of move evaluations with time_remaining field
        time_control: Time control string (e.g., "600+0", "180+2")
    
    Returns:
        {
            'time_trouble_detected': bool,
            'time_trouble_blunders': int,
            'low_time_threshold': int (seconds),
            'moves_in_time_trouble': int,
            'avg_cpl_normal': float,
            'avg_cpl_time_trouble': float,
            'time_trouble_moves': List[Dict],  # Specific moves in time trouble
        }
    """
    
    # Parse time control to determine low-time threshold
    # Format: "initial+increment" (e.g., "600+0" = 10min blitz, "180+2" = 3min+2sec blitz)
    try:
        parts = time_control.split('+')
        initial_seconds = int(parts[0])
        
        # Define "time trouble" based on time control
        if initial_seconds >= 900:  # 15+ minutes (rapid/classical)
            low_time_threshold = 60  # Under 1 minute
        elif initial_seconds >= 300:  # 5-15 minutes (blitz)
            low_time_threshold = 30  # Under 30 seconds
        else:  # < 5 minutes (bullet)
            low_time_threshold = 10  # Under 10 seconds
    except:
        low_time_threshold = 30  # Default fallback
    
    # Analyze moves
    time_trouble_blunders = 0
    moves_in_time_trouble = 0
    time_trouble_move_details = []
    
    normal_cpls = []
    time_trouble_cpls = []
    
    for move_eval in move_evals:
        time_remaining = move_eval.get('time_remaining')
        
        if time_remaining is None:
            # No time data, skip
            normal_cpls.append(move_eval.get('cp_loss', 0))
            continue
        
        cp_loss = move_eval.get('cp_loss', 0)
        
        if time_remaining <= low_time_threshold:
            # In time trouble
            moves_in_time_trouble += 1
            time_trouble_cpls.append(cp_loss)
            
            if move_eval.get('blunder_type') == 'blunder':
                time_trouble_blunders += 1
                time_trouble_move_details.append({
                    'move_number': move_eval.get('move_num'),
                    'san': move_eval.get('san'),
                    'cp_loss': cp_loss,
                    'time_remaining': time_remaining,
                    'blunder_subtype': move_eval.get('blunder_subtype'),
                })
        else:
            # Normal time
            normal_cpls.append(cp_loss)
    
    # Calculate averages
    avg_cpl_normal = sum(normal_cpls) / len(normal_cpls) if normal_cpls else 0
    avg_cpl_time_trouble = sum(time_trouble_cpls) / len(time_trouble_cpls) if time_trouble_cpls else 0
    
    time_trouble_detected = time_trouble_blunders > 0 or (avg_cpl_time_trouble > avg_cpl_normal * 1.5)
    
    return {
        'time_trouble_detected': time_trouble_detected,
        'time_trouble_blunders': time_trouble_blunders,
        'low_time_threshold': low_time_threshold,
        'moves_in_time_trouble': moves_in_time_trouble,
        'avg_cpl_normal': round(avg_cpl_normal, 1),
        'avg_cpl_time_trouble': round(avg_cpl_time_trouble, 1),
        'time_trouble_moves': time_trouble_move_details,
    }


def render_time_trouble_analysis(time_trouble_data: Dict[str, Any]):
    """Display time trouble analysis results."""
    
    if not time_trouble_data.get('time_trouble_detected'):
        st.success("✅ No significant time trouble issues detected")
        return
    
    st.warning("⏰ Time Trouble Detected")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Blunders in Time Trouble",
            time_trouble_data['time_trouble_blunders'],
            help=f"Blunders made with <{time_trouble_data['low_time_threshold']}s remaining"
        )
    
    with col2:
        st.metric(
            "Moves in Time Trouble",
            time_trouble_data['moves_in_time_trouble']
        )
    
    with col3:
        normal_cpl = time_trouble_data['avg_cpl_normal']
        trouble_cpl = time_trouble_data['avg_cpl_time_trouble']
        delta = trouble_cpl - normal_cpl
        st.metric(
            "CPL Increase",
            f"+{delta:.1f}cp",
            delta=f"{trouble_cpl:.1f} vs {normal_cpl:.1f}",
            help="Average CPL in time trouble vs normal time"
        )
    
    # Show specific time trouble moves
    if time_trouble_data['time_trouble_moves']:
        with st.expander("🔍 Time Trouble Blunders", expanded=True):
            for move in time_trouble_data['time_trouble_moves']:
                st.error(
                    f"Move {move['move_number']}: **{move['san']}** "
                    f"({move['cp_loss']}cp loss, {move['time_remaining']}s remaining) - "
                    f"{move.get('blunder_subtype', 'Unknown').replace('_', ' ').title()}"
                )
    
    # Recommendations
    st.info("""
    **💡 Recommendations:**
    - Practice blitz/bullet games to improve time management
    - Set time checkpoints (e.g., "30 seconds per move in opening")
    - Pre-move in obvious positions to save time
    - Focus on fast pattern recognition training
    """)


def add_save_analysis_feature():
    """Save analysis to account to prevent losing results on refresh (Quick Win)."""
    
    # Check if user is logged in (placeholder - implement authentication)
    if 'username' not in st.session_state:
        st.info("💾 Sign in to save analysis results permanently")
        return
    
    # Saved analyses stored in session state (in production: database)
    if 'saved_analyses' not in st.session_state:
        st.session_state.saved_analyses = []
    
    if st.button("💾 Save Analysis"):
        # Save current analysis
        analysis_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        st.session_state.saved_analyses.append({
            'id': analysis_id,
            'timestamp': datetime.now().isoformat(),
            'data': st.session_state.get('analysis_result')
        })
        
        st.success(f"✓ Analysis saved! ID: {analysis_id}")
    
    # Show saved analyses
    if st.session_state.saved_analyses:
        with st.sidebar:
            st.write("---")
            st.write("**📁 Saved Analyses**")
            
            for analysis in st.session_state.saved_analyses[-5:]:  # Show last 5
                timestamp = datetime.fromisoformat(analysis['timestamp'])
                if st.button(f"📊 {timestamp.strftime('%Y-%m-%d %H:%M')}", key=analysis['id']):
                    st.session_state.analysis_result = analysis['data']
                    st.rerun()
