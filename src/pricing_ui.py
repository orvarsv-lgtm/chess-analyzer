"""Pricing page with tier comparison cards."""

from __future__ import annotations

import streamlit as st

from src.paddle_integration import (
    init_paddle,
    render_checkout_button,
    get_user_tier,
    PADDLE_PRICES,
    PADDLE_CLIENT_TOKEN,
)
from src.auth import get_current_user, is_logged_in


def render_pricing_page() -> None:
    """Render a beautiful pricing page with tier comparison."""
    
    # Initialize Paddle.js
    init_paddle()
    
    # Get current user info
    user = get_current_user()
    user_email = user.get("email") if user else None
    current_tier = get_user_tier(user_email) if user_email else "free"
    
    st.header("💎 Choose Your Plan")
    st.caption("Unlock deeper analysis and accelerate your chess improvement")
    
    if current_tier != "free":
        st.success(f"✅ You're currently on the **{current_tier.title()}** plan")
    
    # Custom CSS for pricing cards - equal height and symmetrical
    st.markdown("""
    <style>
    /* Make Streamlit native buttons rounded on pricing page */
    div[data-testid="column"] button, div.stButton > button {
        border-radius: 12px !important;
    }
    .pricing-container {
        display: flex;
        align-items: stretch;
        gap: 16px;
    }
    .pricing-card {
        border-radius: 16px;
        padding: 20px 16px;
        margin: 8px 0;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
        min-height: 420px;
        display: flex;
        flex-direction: column;
    }
    .pricing-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.15);
    }
    .pricing-free {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
    }
    .pricing-basic {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
    }
    .pricing-plus {
        background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
        color: white;
        border: 3px solid #fbbf24;
        position: relative;
    }
    .pricing-pro {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
    }
    .price-amount {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 12px 0;
    }
    .price-period {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .tier-name {
        font-size: 1.3rem;
        font-weight: 700;
        margin-bottom: 4px;
        min-height: 32px;
    }
    .tier-badge-space {
        min-height: 28px;
    }
    .feature-list {
        text-align: left;
        margin: 16px 0;
        padding: 0;
        list-style: none;
        flex-grow: 1;
    }
    .feature-list li {
        padding: 6px 0;
        border-bottom: 1px solid rgba(255,255,255,0.2);
        font-size: 0.85rem;
        line-height: 1.3;
    }
    .feature-list li:last-child {
        border-bottom: none;
    }
    .popular-badge {
        background: #fbbf24;
        color: #1f2937;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        display: inline-block;
    }
    .tier-tagline {
        font-size: 0.8rem;
        opacity: 0.9;
        font-style: italic;
        margin-top: auto;
        padding-top: 12px;
        border-top: 1px solid rgba(255,255,255,0.2);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create 4 columns for pricing cards
    col1, col2, col3, col4 = st.columns(4)
    
    # Free Tier
    with col1:
        st.markdown("""
        <div class="pricing-card pricing-free">
            <div class="tier-badge-space"></div>
            <div class="tier-name">🟢 Free</div>
            <div class="price-amount">€0<span class="price-period">/mo</span></div>
            <ul class="feature-list">
                <li>✅ 50 games / month</li>
                <li>✅ Max depth: 10</li>
                <li>✅ 1 AI review / month</li>
                <li>✅ Unlimited puzzles</li>
                <li>✅ Batch: 100 games</li>
                <li>❌ No career analysis</li>
            </ul>
            <div class="tier-tagline">Perfect to get started</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("Get Started Free", key="btn_free", use_container_width=True):
            if current_tier == "free":
                st.info("You're already on the Free plan!")
            else:
                st.info("You're on a paid plan. Manage your subscription below.")
    
    # Basic Tier
    with col2:
        st.markdown("""
        <div class="pricing-card pricing-basic">
            <div class="tier-badge-space"></div>
            <div class="tier-name">🔵 Basic</div>
            <div class="price-amount">€9<span class="price-period">/mo</span></div>
            <ul class="feature-list">
                <li>✅ 500 games / month</li>
                <li>✅ Max depth: 16</li>
                <li>✅ 10 AI reviews / month</li>
                <li>✅ Unlimited puzzles</li>
                <li>✅ Batch: 500 games</li>
                <li>❌ No career analysis</li>
            </ul>
            <div class="tier-tagline">💡 For casual players</div>
        </div>
        """, unsafe_allow_html=True)
        
        _render_tier_button("basic", current_tier, user_email)
    
    # Plus Tier (Most Popular)
    with col3:
        st.markdown("""
        <div class="pricing-card pricing-plus">
            <div class="tier-badge-space"><span class="popular-badge">⭐ BEST VALUE</span></div>
            <div class="tier-name">🟣 Plus</div>
            <div class="price-amount">€19<span class="price-period">/mo</span></div>
            <ul class="feature-list">
                <li>✅ 2,000 games / month</li>
                <li>✅ Max depth: 18–20</li>
                <li>✅ 15 AI reviews / month</li>
                <li>✅ 1 career analysis / mo</li>
                <li>✅ Batch: 1,000 games</li>
                <li>✅ Priority support</li>
            </ul>
            <div class="tier-tagline">💡 For serious players</div>
        </div>
        """, unsafe_allow_html=True)
        
        _render_tier_button("plus", current_tier, user_email)
    
    # Pro Tier
    with col4:
        st.markdown("""
        <div class="pricing-card pricing-pro">
            <div class="tier-badge-space"></div>
            <div class="tier-name">🔴 Pro</div>
            <div class="price-amount">€29<span class="price-period">/mo</span></div>
            <ul class="feature-list">
                <li>✅ 10,000 games / month</li>
                <li>✅ Max depth: 20–22</li>
                <li>✅ Unlimited AI reviews</li>
                <li>✅ 5 career analyses / mo</li>
                <li>✅ Batch: 2,000 games</li>
                <li>✅ Priority support</li>
            </ul>
            <div class="tier-tagline">💡 For dedicated pros</div>
        </div>
        """, unsafe_allow_html=True)
        
        _render_tier_button("pro", current_tier, user_email)
    
    # Feature comparison table
    st.divider()
    st.subheader("📋 Feature Comparison")
    
    comparison_data = {
        "Feature": [
            "Games per month",
            "Analysis depth",
            "AI game reviews / month",
            "Career analysis / month",
            "Batch limit",
            "Puzzles",
            "Priority support",
        ],
        "🟢 Free": [
            "50",
            "10",
            "1",
            "❌",
            "100",
            "✅ Unlimited",
            "❌",
        ],
        "🔵 Basic (€9)": [
            "500",
            "16",
            "10",
            "❌",
            "500",
            "✅ Unlimited",
            "❌",
        ],
        "🟣 Plus (€19)": [
            "2,000",
            "18–20",
            "15",
            "1",
            "1,000",
            "✅ Unlimited",
            "✅",
        ],
        "🔴 Pro (€29)": [
            "10,000",
            "20–22",
            "Unlimited",
            "5",
            "2,000",
            "✅ Unlimited",
            "✅",
        ],
    }
    
    import pandas as pd
    df = pd.DataFrame(comparison_data)
    
    # Style the dataframe
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
    )
    
    # FAQ section
    st.divider()
    st.subheader("❓ Frequently Asked Questions")
    
    with st.expander("What is 'analysis depth'?"):
        st.write("""
        Analysis depth determines how deeply Stockfish examines each position. 
        Higher depth means more accurate evaluations but takes longer to compute.
        - **Depth 10**: Quick analysis, good for blunder detection
        - **Depth 16**: Solid analysis for most players
        - **Depth 18-20**: Tournament-quality analysis
        - **Depth 20-22**: Professional-level precision
        """)
    
    with st.expander("What is a 'career analysis'?"):
        st.write("""
        Career analysis examines your entire game history to identify long-term patterns:
        - Opening repertoire trends and success rates
        - Phase-by-phase performance over time
        - Recurring tactical weaknesses
        - Improvement trajectory and rating correlation
        """)
    
    with st.expander("Can I cancel anytime?"):
        st.write("""
        Yes! All subscriptions are month-to-month with no long-term commitment.
        Cancel anytime and you'll retain access until the end of your billing period.
        """)
    
    with st.expander("What payment methods do you accept?"):
        st.write("""
        We accept all major credit cards, debit cards, and PayPal through our 
        secure payment processor (Paddle). All transactions are encrypted and secure.
        """)


def _render_tier_button(tier: str, current_tier: str, user_email: str | None) -> None:
    """Render the appropriate button for a pricing tier."""
    tier_order = {"free": 0, "basic": 1, "plus": 2, "pro": 3}
    tier_names = {"basic": "Basic", "plus": "Plus", "pro": "Pro"}
    tier_prices = {"basic": "€9", "plus": "€19", "pro": "€29"}
    
    current_level = tier_order.get(current_tier, 0)
    target_level = tier_order.get(tier, 1)
    
    price_id = PADDLE_PRICES.get(tier, "")
    
    if current_tier == tier:
        # Already on this plan
        st.button(
            "✅ Current Plan",
            key=f"btn_{tier}",
            use_container_width=True,
            disabled=True,
        )
    elif target_level < current_level:
        # Downgrade (not typically supported via checkout)
        st.button(
            "Manage Subscription",
            key=f"btn_{tier}",
            use_container_width=True,
            disabled=True,
            help="Contact support to downgrade",
        )
    elif not user_email:
        # Not logged in
        if st.button(
            f"Upgrade to {tier_names.get(tier, tier.title())}",
            key=f"btn_{tier}",
            use_container_width=True,
            type="primary",
        ):
            st.warning("🔒 Please sign in first to upgrade your plan.")
    elif not price_id:
        # Price ID not configured
        if st.button(
            f"Upgrade to {tier_names.get(tier, tier.title())}",
            key=f"btn_{tier}",
            use_container_width=True,
            type="primary",
        ):
            st.info("⏳ This plan will be available soon!")
    else:
        # Show Paddle checkout button
        render_checkout_button(
            price_id=price_id,
            customer_email=user_email,
            button_text=f"Upgrade to {tier_names.get(tier, tier.title())} ({tier_prices.get(tier, '')})",
        )
