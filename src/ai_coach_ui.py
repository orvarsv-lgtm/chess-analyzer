"""
AI Coach Tab UI for Streamlit App

Premium feature integration for GPT-powered coaching insights.
"""

import streamlit as st
from typing import Any, Dict, List, Optional
from datetime import datetime
import io
import re

from src.ai_coach import (
    generate_game_review,
    generate_demo_review,
    generate_career_analysis,
    check_ai_coach_quota,
    increment_ai_coach_usage,
    AICoachResponse,
)


def _split_long_line(line, max_len=100):
    # Splits a long line into chunks of max_len, breaking at spaces if possible
    if len(line) <= max_len:
        return [line]
    out = []
    while len(line) > max_len:
        # Try to break at the last space before max_len
        idx = line.rfind(' ', 0, max_len)
        if idx == -1:
            idx = max_len
        out.append(line[:idx])
        line = line[idx:].lstrip()
    if line:
        out.append(line)
    return out


def _sanitize_for_pdf(text: str) -> str:
    """
    Replace Unicode characters with ASCII equivalents for PDF compatibility.
    Helvetica font doesn't support many Unicode characters.
    """
    replacements = {
        '—': '-',      # em-dash
        '–': '-',      # en-dash
        ''': "'",      # curly apostrophe
        ''': "'",      # curly apostrophe
        '"': '"',      # curly quote
        '"': '"',      # curly quote
        '…': '...',    # ellipsis
        '≥': '>=',     # greater than or equal
        '≤': '<=',     # less than or equal
        '±': '+/-',    # plus-minus
        '×': 'x',      # multiplication
        '→': '->',     # arrow
        '←': '<-',     # arrow
        '↑': '^',      # up arrow
        '↓': 'v',      # down arrow
        '•': '*',      # bullet
        '✓': '[x]',    # checkmark
        '✅': '[OK]',  # green check
        '⚠️': '[!]',   # warning
        '🔴': '[!]',   # red circle
        '🎯': '[>]',   # target
        '📊': '',      # chart emoji
        '📋': '',      # clipboard
        '📄': '',      # document
        '🧠': '',      # brain
        '🚀': '',      # rocket
        '🔄': '',      # refresh
        '📥': '',      # download
        'ℹ️': '[i]',   # info
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    # Remove any remaining non-ASCII characters
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text


def _generate_pdf_report(analysis_text: str, player_name: str, stats: Dict[str, Any]) -> bytes:
    """
    Generate a PDF report from the AI Coach analysis.
    
    Args:
        analysis_text: The markdown analysis text
        player_name: Player's username
        stats: Statistics dictionary
        
    Returns:
        PDF file as bytes
    """
    try:
        from fpdf import FPDF
    except ImportError:
        # Return None if fpdf not installed
        return None
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.cell(0, 10, 'Chess Coach Analysis Report', align='C', new_x='LMARGIN', new_y='NEXT')
            self.ln(5)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', align='C')
    
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Sanitize player name for PDF
    player_name = _sanitize_for_pdf(player_name)
    
    # Title section
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, f'Player: {player_name}', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(5)
    
    # Key stats
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, 'Key Statistics', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    
    total_games = stats.get('total_games', 0)
    win_rate = stats.get('win_rate', 0)
    conversion_rate = stats.get('conversion_rate', 0)
    blunder_rate = stats.get('blunder_rate', 0)
    
    pdf.cell(0, 6, f'Games Analyzed: {total_games}', new_x='LMARGIN', new_y='NEXT')
    pdf.cell(0, 6, f'Win Rate: {win_rate:.0%}', new_x='LMARGIN', new_y='NEXT')
    pdf.cell(0, 6, f'Conversion Rate: {conversion_rate:.0f}%', new_x='LMARGIN', new_y='NEXT')
    pdf.cell(0, 6, f'Blunders per 100 moves: {blunder_rate:.1f}', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(8)
    
    # Analysis section
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, 'Analysis', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)
    
    # Process markdown text for PDF - sanitize first
    text = _sanitize_for_pdf(analysis_text)
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            pdf.ln(3)
            continue
        # Handle headers
        if line.startswith('## '):
            pdf.ln(5)
            pdf.set_font('Helvetica', 'B', 12)
            header_text = line[3:].strip()
            header_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', header_text)
            header_text = re.sub(r'\*([^*]+)\*', r'\1', header_text)
            for chunk in _split_long_line(header_text):
                pdf.multi_cell(0, 8, chunk)
            pdf.set_font('Helvetica', '', 10)
            continue
        # Handle blockquotes (the ONE RULE)
        if line.startswith('>'):
            pdf.set_font('Helvetica', 'BI', 10)
            quote_text = line[1:].strip()
            quote_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', quote_text)
            quote_text = re.sub(r'\*([^*]+)\*', r'\1', quote_text)
            for chunk in _split_long_line(quote_text):
                pdf.multi_cell(0, 6, f'  {chunk}')
            pdf.set_font('Helvetica', '', 10)
            continue
        # Regular text - remove markdown formatting
        clean_line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # Bold
        clean_line = re.sub(r'\*([^*]+)\*', r'\1', clean_line)  # Italic
        clean_line = re.sub(r'`([^`]+)`', r'\1', clean_line)  # Code
        for chunk in _split_long_line(clean_line):
            pdf.multi_cell(0, 6, chunk)
    
    # Return PDF as bytes
    return pdf.output()

def render_ai_coach_tab(aggregated: Dict[str, Any]) -> None:
    """
    Render the AI Coach tab with premium gate and quota management.
    
    Args:
        aggregated: Analyzed games data
    """
    st.header("🤖 AI Chess Coach")
    st.caption("GPT-powered personalized coaching insights")
    
    # Check if user has analyzed games
    games = aggregated.get("games", [])
    if not games:
        st.info("📊 No games analyzed yet. Run an analysis first to get AI coaching insights!")
        return
    
    # Premium gate + quota check
    # TODO: Replace with real user authentication
    # TESTING MODE: Paywall disabled for testing
    user_tier = st.session_state.get('user_tier', 'coach')  # Default to unlimited for testing
    user_id = st.session_state.get('user_id', 'demo_user')
    
    has_quota, remaining = check_ai_coach_quota(user_tier, user_id)
    
    # Show tier status (informational only during testing)
    st.info("🧪 **Testing Mode**: AI Coach paywall is disabled. All users have unlimited access.")
    
    # Paywall disabled for testing
    # if not has_quota:
    #     _render_upgrade_prompt()
    #     return
    
    # Main AI Coach interface
    st.markdown("---")
    
    # Mode selector: Single Game vs Career Analysis
    analysis_mode = st.radio(
        "Analysis Mode",
        ["📄 Single Game Review", "📊 Full Career Analysis"],
        horizontal=True,
        help="Single game reviews analyze one game in depth. Career analysis looks at all your games to identify patterns and trends."
    )
    
    focus_player = aggregated.get('focus_player', '')
    
    if analysis_mode == "📊 Full Career Analysis":
        _render_career_analysis(games, focus_player, user_id, aggregated=aggregated)
    else:
        _render_single_game_review(games, aggregated, user_id)


def _render_single_game_review(games: List[Dict], aggregated: Dict, user_id: str) -> None:
    """Render single game review interface."""
    st.subheader("📄 Single Game Review")
    
    game_options = []
    for i, game in enumerate(games):
        white = game.get('white', '?')
        black = game.get('black', '?')
        result = game.get('result', '?')
        date = game.get('date', '?')
        opening = game.get('opening_name', 'Unknown Opening')
        
        label = f"Game {i+1}: {white} vs {black} ({result}) - {opening} - {date}"
        game_options.append(label)
    
    selected_idx = st.selectbox(
        "Choose a game",
        range(len(game_options)),
        format_func=lambda x: game_options[x]
    )
    
    selected_game = games[selected_idx]
    
    # Show game preview
    with st.expander("📋 Game Info", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Opening", selected_game.get('opening_name', 'Unknown'))
        with col2:
            st.metric("Result", selected_game.get('result', '?'))
        with col3:
            st.metric("Moves", len(selected_game.get('moves_table', [])))
    
    # Determine player color
    focus_player = aggregated.get('focus_player', '')
    player_color = selected_game.get('focus_color', 'white')
    
    # Get player rating if available
    if player_color == 'white':
        player_rating = selected_game.get('white_elo') or selected_game.get('white_rating')
    else:
        player_rating = selected_game.get('black_elo') or selected_game.get('black_rating')
    
    # Generate AI review button
    st.markdown("---")
    
    # Check if already reviewed (cache in session)
    cache_key = f"ai_review_{selected_idx}_{user_id}"
    cached_review = st.session_state.get(cache_key)
    
    if cached_review:
        st.success("✅ Review already generated (using cached version)")
        _render_ai_review(cached_review)
        
        if st.button("🔄 Generate New Review", help="This will use another AI review credit"):
            # Clear cache and regenerate
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()
    else:
        # Show what will be analyzed
        st.info(f"🎯 Analyzing your game as **{player_color.title()}** (Rating: {player_rating or 'Unknown'})")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button("🚀 Generate AI Coach Review", type="primary", use_container_width=True):
                _generate_and_display_review(
                    selected_game,
                    player_color,
                    player_rating,
                    'coach',
                    user_id,
                    cache_key,
                    999
                )


def _render_career_analysis(games: List[Dict], player_name: str, user_id: str, aggregated: Optional[Dict[str, Any]] = None) -> None:
    """Render full career analysis interface.
    
    Args:
        games: List of analyzed game dicts
        player_name: Player username
        user_id: User ID for caching
        aggregated: Full aggregated data from Analysis tab (includes phase_stats, opening_rates, etc.)
    """
    st.subheader("📊 Full Career Analysis")
    st.write(f"Analyzing **{len(games)} games** for comprehensive career insights.")
    
    # Get player rating from first game
    player_rating = None
    if games:
        first_game = games[0]
        focus_color = first_game.get('focus_color', 'white')
        if focus_color == 'white':
            player_rating = first_game.get('white_elo') or first_game.get('white_rating')
        else:
            player_rating = first_game.get('black_elo') or first_game.get('black_rating')
    
    # Show what will be analyzed
    st.info(f"""
    🧠 **AI Diagnostic Reasoning**
    
    The AI Coach analyzes your data to identify:
    - **ONE primary cause** of your rating plateau (not a list of issues)
    - **Why it happens** — the cognitive/behavioral mechanism
    - **The failure loop** — the exact pattern you repeat
    - **ONE behavioral fix** — not "study more" but a concrete rule
    
    _This is diagnostic coaching, not statistics recitation._
    """)
    
    # Cache key for career analysis
    cache_key = f"career_analysis_{player_name}_{len(games)}_{user_id}"
    cached_analysis = st.session_state.get(cache_key)
    
    if cached_analysis:
        st.success("✅ Career analysis already generated (using cached version)")
        _render_career_analysis_result(cached_analysis)
        
        if st.button("🔄 Regenerate Career Analysis"):
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()
    else:
        if st.button("🚀 Generate Career Analysis", type="primary", use_container_width=True):
            with st.spinner("🤖 AI Coach is analyzing your entire chess career... (this may take 30-60 seconds)"):
                try:
                    import os
                    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
                    
                    # Try Streamlit secrets too
                    if not has_api_key:
                        try:
                            has_api_key = bool(st.secrets.get('OPENAI_API_KEY'))
                        except:
                            pass
                    
                    if not has_api_key:
                        st.warning("⚠️ OpenAI API key not configured. Cannot generate real analysis.")
                        st.info("Add OPENAI_API_KEY to Streamlit secrets to enable AI analysis.")
                        return
                    
                    result = generate_career_analysis(
                        all_games=games,
                        player_name=player_name or "Player",
                        player_rating=player_rating,
                        aggregated_data=aggregated,
                    )
                    
                    # Cache the result
                    st.session_state[cache_key] = result
                    
                    # Note: Using the configured model for diagnostic reasoning
                    tokens = result.get('tokens_used', 0)
                    cost = result.get('cost_cents', 0)
                    if tokens > 0:
                        st.success(f"✅ AI Coach analysis complete! ({tokens} tokens, ~${cost/100:.2f})")
                    else:
                        st.success("✅ Analysis complete (fallback mode)")
                        # Show error details if available
                        last_error = st.session_state.get("_ai_coach_last_error")
                        if last_error:
                            st.warning(f"⚠️ AI error: {last_error}")
                    _render_career_analysis_result(result)
                    
                except Exception as e:
                    st.error(f"❌ Failed to generate career analysis: {str(e)}")
                    st.info("Try again or check if your OpenAI API key is valid.")


def _render_career_analysis_result(result: Dict[str, Any]) -> None:
    """Render the career analysis result - focused on data-driven insights."""
    
    stats = result.get('stats', {})
    
    # Show primary issue prominently if available
    primary_issue = result.get('primary_issue', '')
    if primary_issue and primary_issue != "No dominant weakness identified":
        st.error(f"**🎯 Primary Issue**: {primary_issue}")
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Games", stats.get('total_games', 0))
    with col2:
        win_rate = stats.get('win_rate', 0)
        st.metric("Win Rate", f"{win_rate:.0%}")
    with col3:
        conversion_rate = stats.get('conversion_rate', 0)
        conv_icon = "✅" if conversion_rate >= 70 else "⚠️" if conversion_rate >= 50 else "🔴"
        st.metric(f"{conv_icon} Conversion", f"{conversion_rate:.0f}%", help="% of winning positions (≥+1.5) converted to wins")
    with col4:
        blunder_rate = stats.get('blunder_rate', 0)
        br_icon = "✅" if blunder_rate < 4 else "⚠️" if blunder_rate < 7 else "🔴"
        st.metric(f"{br_icon} Blunders/100", f"{blunder_rate:.1f}")
    
    st.markdown("---")
    
    # Show the main analysis
    st.markdown("### 📊 Your Analysis")
    st.markdown(result.get('analysis', 'No analysis available'))
    
    # PDF Download button
    analysis_text = result.get('analysis', '')
    if analysis_text:
        player_name = stats.get('player_name', 'Player')
        pdf_bytes = _generate_pdf_report(analysis_text, player_name, stats)
        if pdf_bytes:
            st.download_button(
                label="📥 Download Report as PDF",
                data=pdf_bytes,
                file_name=f"chess_coach_report_{player_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.caption("_PDF download requires 'fpdf2' package. Install with: pip install fpdf2_")
    
    # Show data sources used
    data_sources = result.get('data_sources', [])
    if data_sources:
        with st.expander("📋 Data sources used in this analysis", expanded=False):
            st.caption("Every claim above is derived from these data points:")
            for ds in data_sources[:10]:
                st.caption(f"• `{ds}`")
    
    # Put all the detailed stats in a collapsible section
    with st.expander("📊 Detailed Statistics (for reference)", expanded=False):
        # PPI Section
        st.markdown("**Phase Performance Index**")
        st.caption("PPI normalizes CPL for phase difficulty. Near 1.0 = average.")
        
        ppi = stats.get('ppi', {})
        baselines = stats.get('phase_baselines', {'opening': 45, 'middlegame': 95, 'endgame': 130})
        
        ppi_col1, ppi_col2, ppi_col3 = st.columns(3)
        with ppi_col1:
            opening_ppi = ppi.get('opening', 0)
            ppi_icon = "✅" if opening_ppi <= 0.9 else "⚠️" if opening_ppi <= 1.1 else "🔴"
            st.metric(f"{ppi_icon} Opening", f"{opening_ppi:.2f}" if opening_ppi > 0 else "N/A")
        with ppi_col2:
            mid_ppi = ppi.get('middlegame', 0)
            ppi_icon = "✅" if mid_ppi <= 0.9 else "⚠️" if mid_ppi <= 1.1 else "🔴"
            st.metric(f"{ppi_icon} Middlegame", f"{mid_ppi:.2f}" if mid_ppi > 0 else "N/A")
        with ppi_col3:
            end_ppi = ppi.get('endgame', 0)
            ppi_icon = "✅" if end_ppi <= 0.9 else "⚠️" if end_ppi <= 1.1 else "🔴"
            st.metric(f"{ppi_icon} Endgame", f"{end_ppi:.2f}" if end_ppi > 0 else "N/A")
        
        st.markdown("---")
        
        # Conversion
        st.markdown("**Conversion Analysis**")
        conversion_stats_data = stats.get('conversion_stats', {})
        winning_pos = conversion_stats_data.get('winning_positions', 0)
        converted = conversion_stats_data.get('converted_wins', 0)
        if winning_pos > 0:
            conv_pct = converted / winning_pos * 100
            st.caption(f"Winning positions: {winning_pos} | Converted: {converted} ({conv_pct:.0f}%)")
        
        st.markdown("---")
        
        # Color split
        st.markdown("**Performance by Color**")
        white_stats = stats.get('white_stats', {})
        black_stats = stats.get('black_stats', {})
        st.caption(f"White: {white_stats.get('games', 0)}g, {white_stats.get('win_rate', 0):.0%} WR | Black: {black_stats.get('games', 0)}g, {black_stats.get('win_rate', 0):.0%} WR")
        
        st.markdown("---")
        
        # Openings
        openings = stats.get('openings', {})
        if openings:
            st.markdown("**Opening Results**")
            sorted_openings = sorted(openings.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
            for name, data in sorted_openings:
                if name and name != 'Unknown':
                    games = data['games']
                    wr = data['wins'] / games if games > 0 else 0
                    st.caption(f"• {name}: {games}g, {wr:.0%} WR")
    
    # Metadata at the bottom
    with st.expander("ℹ️ Analysis Metadata", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Tokens Used", result.get('tokens_used', 0))
        with col2:
            st.metric("Cost", f"${result.get('cost_cents', 0)/100:.2f}")
        with col3:
            ts = result.get('timestamp')
            if ts:
                st.metric("Generated", ts.strftime("%Y-%m-%d %H:%M"))


def _render_tier_status(user_tier: str, remaining: int):
    """Show user's current tier and quota status."""
    tier_info = {
        'free': ('🆓 Free', 'No AI coach access', '#999'),
        'hobbyist': ('⭐ Hobbyist', f'{remaining}/2 reviews this month', '#4CAF50'),
        'serious': ('💎 Serious', f'{remaining}/5 reviews this month', '#2196F3'),
        'coach': ('👑 Coach', 'Unlimited reviews', '#FF9800'),
    }
    
    tier_label, tier_desc, tier_color = tier_info.get(user_tier, tier_info['free'])
    
    st.markdown(f"""
    <div style="padding: 1rem; background-color: {tier_color}22; border-left: 4px solid {tier_color}; border-radius: 4px; margin-bottom: 1rem;">
        <strong>{tier_label}</strong> • {tier_desc}
    </div>
    """, unsafe_allow_html=True)


def _render_upgrade_prompt():
    """Show upgrade prompt for free users or users out of quota."""
    st.warning("🔒 AI Coach is a premium feature")
    
    st.markdown("""
    ### Why upgrade?
    
    Get personalized coaching insights powered by GPT:
    
    - 🎯 **Natural language game reviews** - Understand exactly what went wrong and why
    - 📈 **Personalized training plans** - AI analyzes your weaknesses and suggests daily exercises
    - 🧠 **Strategic & tactical feedback** - Learn patterns specific to your playing style
    - 💡 **Position explanations** - Get "coach-like" advice for critical moments
    
    ### Pricing
    
    | Tier | Price | AI Reviews/Month | Other Features |
    |------|-------|------------------|----------------|
    | **Hobbyist** | $9.99/mo | 2 reviews | 50 games/mo, unlimited puzzles |
    | **Serious** | $19.99/mo | 5 reviews | Unlimited games, opening lab |
    | **Coach** | $49.99/mo | Unlimited | + Student management, API access |
    """)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🚀 Upgrade Now", type="primary", use_container_width=True):
            st.info("🔜 Payment integration coming soon! Contact support for early access.")
    
    # Demo mode toggle
    st.markdown("---")
    if st.checkbox("🎬 Try Demo Mode (see example AI review)"):
        st.info("Demo mode shows a sample AI review. Your actual game will not be analyzed.")
        demo_game = {'opening_name': 'Sicilian Defense: Najdorf Variation'}
        demo_review = generate_demo_review(demo_game)
        _render_ai_review(demo_review)


def _generate_and_display_review(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int],
    user_tier: str,
    user_id: str,
    cache_key: str,
    remaining: int
):
    """Generate AI review and display results."""
    
    # Check for API key
    import os
    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
    
    if not has_api_key:
        st.warning("⚠️ OpenAI API key not configured. Using demo mode.")
        st.info("To enable real AI reviews, set OPENAI_API_KEY environment variable.")
        review = generate_demo_review(game_data)
    else:
        # Show progress
        with st.spinner("🤖 AI Coach is analyzing your game... (this may take 10-30 seconds)"):
            try:
                review = generate_game_review(
                    game_data=game_data,
                    player_color=player_color,
                    player_rating=player_rating
                )
            except Exception as e:
                st.error(f"❌ Failed to generate AI review: {str(e)}")
                st.info("Falling back to demo mode...")
                review = generate_demo_review(game_data)
    
    # Increment usage counter
    increment_ai_coach_usage(user_id)
    
    # Cache the review
    st.session_state[cache_key] = review
    
    # Display
    st.success(f"✅ Review generated! ({review.tokens_used} tokens, ~${review.cost_cents/100:.2f})")
    st.caption(f"💎 You have **{remaining - 1}** reviews remaining this month")
    
    _render_ai_review(review)


def _render_ai_review(review: AICoachResponse):
    """Render the AI coach review in a nice format."""
    
    # Game Summary
    st.markdown("### 📝 Game Summary")
    st.write(review.game_summary)
    
    # Key Moments
    if review.key_moments:
        st.markdown("### 🎯 Key Moments")
        for i, moment in enumerate(review.key_moments, 1):
            with st.expander(f"Critical Moment #{i} - Move {moment.get('move', '?')}", expanded=i==1):
                st.write(moment.get('advice', ''))
    
    # Opening Advice
    st.markdown("### 📚 Opening Advice")
    st.info(review.opening_advice)
    
    # Strategic Advice
    st.markdown("### ♟️ Strategic Advice")
    st.info(review.strategic_advice)
    
    # Tactical Advice
    st.markdown("### ⚡ Tactical Advice")
    st.warning(review.tactical_advice)
    
    # Training Recommendations
    st.markdown("### 🎯 Training Recommendations")
    st.markdown("Your AI coach suggests:")
    for rec in review.training_recommendations:
        st.markdown(f"- {rec}")
    
    # Metadata
    with st.expander("ℹ️ Review Metadata", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Tokens Used", review.tokens_used)
        with col2:
            st.metric("Cost", f"${review.cost_cents/100:.2f}")
        with col3:
            st.metric("Generated", review.timestamp.strftime("%Y-%m-%d %H:%M"))


# =============================================================================
# TIER MANAGEMENT (DEMO)
# =============================================================================


def render_tier_selector_sidebar():
    """
    Demo tier selector for testing (in sidebar).
    Remove this in production - replace with real authentication.
    """
    with st.sidebar:
        st.markdown("---")
        st.subheader("🎛️ Demo: Tier Selector")
        st.caption("(Remove in production)")
        
        current_tier = st.session_state.get('user_tier', 'free')
        
        tier = st.selectbox(
            "Simulate tier",
            ['free', 'hobbyist', 'serious', 'coach'],
            index=['free', 'hobbyist', 'serious', 'coach'].index(current_tier)
        )
        
        if tier != current_tier:
            st.session_state['user_tier'] = tier
            st.rerun()
        
        # Reset quota button
        if st.button("🔄 Reset monthly quota"):
            # Clear all AI review counters
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith('ai_reviews_')]
            for k in keys_to_clear:
                del st.session_state[k]
            st.success("Quota reset!")
            st.rerun()
