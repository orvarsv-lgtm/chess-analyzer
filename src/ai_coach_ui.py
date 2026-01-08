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
    st.caption("GPT-4 powered personalized coaching insights • Premium Feature")
    
    # Check if user has analyzed games
    games = aggregated.get("games", [])
    if not games:
        st.info("📊 No games analyzed yet. Run an analysis first to get AI coaching insights!")
        return
    
    # Premium gate + quota check
    # TODO: Replace with real user authentication
    user_tier = st.session_state.get('user_tier', 'free')
    user_id = st.session_state.get('user_id', 'demo_user')
    
    has_quota, remaining = check_ai_coach_quota(user_tier, user_id)
    
    # Show tier status
    _render_tier_status(user_tier, remaining)
    
    if not has_quota:
        _render_upgrade_prompt()
        return
    
    # Main AI Coach interface
    st.markdown("---")
    
    # Game selector
    st.subheader("Select a game to review")
    
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
                    user_tier,
                    user_id,
                    cache_key,
                    remaining
                )
        
        with col2:
            st.caption(f"💎 Reviews remaining: **{remaining}**")


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
