"""
AI Coach Tab UI for Streamlit App

Premium feature integration for GPT-4 powered coaching insights.
"""

import streamlit as st
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.ai_coach import (
    generate_game_review,
    generate_demo_review,
    generate_career_analysis,
    check_ai_coach_quota,
    increment_ai_coach_usage,
    AICoachResponse,
)


def render_ai_coach_tab(aggregated: Dict[str, Any]) -> None:
    """
    Render the AI Coach tab with premium gate and quota management.
    
    Args:
        aggregated: Analyzed games data
    """
    st.header("🤖 AI Chess Coach")
    st.caption("GPT-4 powered personalized coaching insights")
    
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
        _render_career_analysis(games, focus_player, user_id)
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


def _render_career_analysis(games: List[Dict], player_name: str, user_id: str) -> None:
    """Render full career analysis interface."""
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
    🔍 **Career Analysis Will Include:**
    - Overall win rate and performance trends
    - Opening repertoire analysis (which openings work best for you)
    - Phase-by-phase breakdown (opening, middlegame, endgame)
    - Your biggest strengths and weaknesses
    - Personalized weekly training plan
    - Rating improvement estimate
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
                        player_rating=player_rating
                    )
                    
                    # Cache the result
                    st.session_state[cache_key] = result
                    
                    st.success(f"✅ Career analysis complete! ({result['tokens_used']} tokens, ~${result['cost_cents']/100:.2f})")
                    _render_career_analysis_result(result)
                    
                except Exception as e:
                    st.error(f"❌ Failed to generate career analysis: {str(e)}")
                    st.info("Try again or check if your OpenAI API key is valid.")


def _render_career_analysis_result(result: Dict[str, Any]) -> None:
    """Render the career analysis result."""
    
    # Show stats summary
    stats = result.get('stats', {})
    
    # Main metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Games Analyzed", stats.get('total_games', 0))
    with col2:
        win_rate = stats.get('win_rate', 0)
        st.metric("Win Rate", f"{win_rate:.1%}")
    with col3:
        st.metric("Best Phase", stats.get('best_phase', 'N/A').title())
    with col4:
        st.metric("Worst Phase", stats.get('worst_phase', 'N/A').title())
    
    # Performance by color
    st.markdown("#### ♔ Performance by Color")
    white_stats = stats.get('white_stats', {})
    black_stats = stats.get('black_stats', {})
    
    color_col1, color_col2 = st.columns(2)
    with color_col1:
        w_games = white_stats.get('games', 0)
        w_wr = white_stats.get('win_rate', 0)
        w_cpl = white_stats.get('avg_cpl', 0)
        st.markdown(f"""
        **⬜ As White**: {w_games} games  
        Win Rate: **{w_wr:.0%}** | Avg CPL: **{w_cpl:.0f}**
        """)
    with color_col2:
        b_games = black_stats.get('games', 0)
        b_wr = black_stats.get('win_rate', 0)
        b_cpl = black_stats.get('avg_cpl', 0)
        st.markdown(f"""
        **⬛ As Black**: {b_games} games  
        Win Rate: **{b_wr:.0%}** | Avg CPL: **{b_cpl:.0f}**
        """)
    
    # Show detailed phase CPL with visual indicator
    st.markdown("#### 📊 Phase Performance (Average CPL)")
    opening_cpl = stats.get('opening_cpl', 0)
    mid_cpl = stats.get('middlegame_cpl', 0)
    end_cpl = stats.get('endgame_cpl', 0)
    
    cpl_col1, cpl_col2, cpl_col3 = st.columns(3)
    with cpl_col1:
        color = "🟢" if opening_cpl < 50 else "🟡" if opening_cpl < 100 else "🔴"
        st.metric(f"{color} Opening", f"{opening_cpl:.0f}" if opening_cpl > 0 else "N/A")
    with cpl_col2:
        color = "🟢" if mid_cpl < 80 else "🟡" if mid_cpl < 150 else "🔴"
        st.metric(f"{color} Middlegame", f"{mid_cpl:.0f}" if mid_cpl > 0 else "N/A")
    with cpl_col3:
        color = "🟢" if end_cpl < 80 else "🟡" if end_cpl < 150 else "🔴"
        st.metric(f"{color} Endgame", f"{end_cpl:.0f}" if end_cpl > 0 else "N/A")
    
    # Show error rates with context
    st.markdown("#### ⚠️ Error Analysis")
    err_col1, err_col2, err_col3 = st.columns(3)
    with err_col1:
        br = stats.get('blunder_rate', 0)
        color = "🟢" if br < 5 else "🟡" if br < 10 else "🔴"
        st.metric(f"{color} Blunders/100 moves", f"{br:.1f}")
    with err_col2:
        mr = stats.get('mistake_rate', 0)
        color = "🟢" if mr < 10 else "🟡" if mr < 15 else "🔴"
        st.metric(f"{color} Mistakes/100 moves", f"{mr:.1f}")
    with err_col3:
        total_b = stats.get('total_blunders', 0)
        st.metric("Total Blunders", total_b)
    
    # Blunder distribution by phase
    blunder_phases = stats.get('blunder_phases', {})
    if blunder_phases and stats.get('total_blunders', 0) > 0:
        total_b = stats.get('total_blunders', 1)
        st.caption(f"Blunder distribution: Opening {blunder_phases.get('opening', 0)} ({blunder_phases.get('opening', 0)/total_b*100:.0f}%) | Middlegame {blunder_phases.get('middlegame', 0)} ({blunder_phases.get('middlegame', 0)/total_b*100:.0f}%) | Endgame {blunder_phases.get('endgame', 0)} ({blunder_phases.get('endgame', 0)/total_b*100:.0f}%)")
    
    # Show top openings
    openings = stats.get('openings', {})
    if openings:
        st.markdown("#### 📚 Top Openings")
        # Filter unknown and sort
        filtered = {k: v for k, v in openings.items() if k and k != 'Unknown'}
        if not filtered:
            filtered = openings
        sorted_openings = sorted(filtered.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
        
        for name, data in sorted_openings:
            games = data['games']
            wins = data['wins']
            losses = data.get('losses', 0)
            blunders = data.get('blunders', 0)
            total_moves = data.get('total_moves', games * 30)
            win_rate = wins / games if games > 0 else 0
            avg_cpl = data['total_cpl'] / total_moves if total_moves > 0 else 0
            
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                warning = " ⚠️" if blunders >= 3 else ""
                st.write(f"**{name}**{warning}")
            with col2:
                st.write(f"{games} games")
            with col3:
                wr_color = "🟢" if win_rate >= 0.6 else "🟡" if win_rate >= 0.4 else "🔴"
                st.write(f"{wr_color} {win_rate:.0%} W")
            with col4:
                cpl_color = "🟢" if avg_cpl < 80 else "🟡" if avg_cpl < 130 else "🔴"
                st.write(f"{cpl_color} CPL: {avg_cpl:.0f}")
    
    # Show best and worst games
    best_games = stats.get('best_games', [])
    worst_games = stats.get('worst_games', [])
    
    if best_games or worst_games:
        st.markdown("#### 🎯 Game Highlights")
        
        game_col1, game_col2 = st.columns(2)
        with game_col1:
            st.markdown("**✅ Best Performed Games**")
            for g in best_games[:3]:
                result_emoji = "🏆" if g.get('is_win') else "📊"
                st.caption(f"{result_emoji} Game {g.get('index', '?')}: {g.get('opening', 'Unknown')[:25]} - CPL: {g.get('avg_cpl', 0):.0f}")
        with game_col2:
            st.markdown("**⚠️ Games to Review**")
            for g in worst_games[:3]:
                result_emoji = "❌" if not g.get('is_win') else "📊"
                st.caption(f"{result_emoji} Game {g.get('index', '?')}: {g.get('opening', 'Unknown')[:25]} - CPL: {g.get('avg_cpl', 0):.0f}, {g.get('blunders', 0)} blunders")
    
    st.markdown("---")
    
    # Show the full analysis
    st.markdown("### 🤖 AI Career Analysis")
    st.markdown(result.get('analysis', 'No analysis available'))
    
    # Metadata
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
    
    Get personalized coaching insights powered by GPT-4:
    
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
