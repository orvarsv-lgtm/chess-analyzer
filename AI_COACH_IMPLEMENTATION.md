# AI Coach Implementation Guide

## Overview

The AI Coach feature is now ready for integration! Here's everything you need to know to enable GPT-4 powered coaching insights in your Chess Analyzer app.

## Files Created

1. **`src/ai_coach.py`** - Core AI Coach logic (558 lines)
   - GPT-4 API integration
   - Game review generation
   - Position insight generation
   - Training plan generation
   - Quota/usage tracking
   - Demo mode (works without API key)

2. **`src/ai_coach_ui.py`** - Streamlit UI components (298 lines)
   - Premium gating
   - Tier status display
   - Game selection interface
   - Review rendering
   - Upgrade prompts
   - Demo tier selector (for testing)

3. **Updated `streamlit_app.py`**:
   - Added AI Coach tab to navigation
   - Integrated premium tier system

## How It Works

### Architecture

```
User selects game → Check tier/quota → Call GPT-4 → Parse response → Display review
```

### Premium Tiers & Quotas

| Tier | Price | AI Reviews/Month | Cost per Review |
|------|-------|------------------|-----------------|
| Free | $0 | 0 | - |
| Hobbyist | $9.99/mo | 2 | ~$5/review |
| Serious | $19.99/mo | 5 | ~$4/review |
| Coach | $49.99/mo | Unlimited | N/A |

**Note**: Actual cost to you is ~$0.03-$0.05 per review (GPT-4 Turbo API). The quota limits create scarcity and drive upgrades.

### What AI Coach Provides

1. **Game Summary** - 2-3 sentence overview
2. **Key Moments** - 3-5 critical positions with specific advice
3. **Opening Advice** - Opening-specific feedback
4. **Strategic Advice** - Plans, piece placement, pawn structures
5. **Tactical Advice** - Pattern recognition, calculation
6. **Training Recommendations** - Specific exercises to practice

## Setup Instructions

### 1. Install Dependencies

```bash
pip install openai
```

Or add to `requirements.txt`:
```
openai>=1.0.0
```

### 2. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Set environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

For Streamlit Cloud deployment:
- Go to Settings → Secrets
- Add:
  ```toml
  OPENAI_API_KEY = "sk-..."
  ```

### 3. Test Demo Mode (No API Key Required)

The AI Coach works without an API key in demo mode:

```python
from src.ai_coach import generate_demo_review

game_data = {'opening_name': 'Sicilian Defense'}
review = generate_demo_review(game_data)
print(review.game_summary)
```

### 4. Run the App

```bash
streamlit run streamlit_app.py
```

Navigate to **🤖 AI Coach** tab.

### 5. Test Different Tiers

Use the sidebar "Demo: Tier Selector" to simulate different subscription levels:
- Free: No access, shows upgrade prompt
- Hobbyist: 2 reviews/month
- Serious: 5 reviews/month
- Coach: Unlimited

## Where to Implement (Integration Points)

### Option 1: New Navigation Tab (DONE ✅)

Already integrated! The AI Coach appears as a top-level tab in the navigation.

**Location**: [streamlit_app.py](streamlit_app.py#L1724)

### Option 2: In-Game Replayer Integration

Add AI insights directly in the game replayer:

```python
# In _render_game_replayer_tab():
if st.button("🤖 Get AI Coach Review"):
    review = generate_game_review(current_game, player_color, rating)
    _render_ai_review(review)
```

### Option 3: Puzzle Explanations

Enhance puzzle explanations with AI:

```python
# In puzzles/puzzle_ui.py:
if show_explanation and user_tier in ['serious', 'coach']:
    ai_explanation = generate_position_insight(
        fen=puzzle.fen,
        eval_before=puzzle.eval_before,
        eval_after=puzzle.eval_after,
        best_move_san=puzzle.best_move_san,
        played_move_san=puzzle.played_move_san,
        phase=puzzle.phase
    )
    st.info(f"🤖 AI Coach says: {ai_explanation}")
```

### Option 4: Post-Analysis Summary

After analyzing games, offer AI review:

```python
# After game analysis completes:
st.success("✅ Analysis complete!")
if user_tier != 'free':
    if st.button("🤖 Get AI Summary of All Games"):
        # Generate summary of performance across all games
        training_plan = generate_training_plan(performance_summary, rating)
        # Display weekly training plan
```

## Revenue Model

### Pricing Strategy

**Why these tiers work**:
1. **Free → Hobbyist ($9.99)**: Low barrier, casual players who want AI insights
2. **Hobbyist → Serious ($19.99)**: Power users who analyze frequently
3. **Serious → Coach ($49.99)**: Coaches analyzing student games, high volume users

### Cost Structure

- **Your cost**: $0.03-$0.05 per review (GPT-4 Turbo)
- **Hobbyist tier**: 2 reviews = $0.10 cost, $9.99 revenue = **$9.89 profit**
- **Serious tier**: 5 reviews = $0.25 cost, $19.99 revenue = **$19.74 profit**
- **Margins**: 99%+ gross margin

### Estimated Revenue

If you get 1,000 users:
- 800 free (0 revenue)
- 150 Hobbyist ($1,498/mo)
- 40 Serious ($799/mo)
- 10 Coach ($499/mo)

**Total MRR: $2,796/month = $33,552/year**

With 10,000 users (realistic for a good chess app):
- **MRR: $27,960/month = $335,520/year**

## API Cost Management

### Rate Limiting

```python
# In src/ai_coach.py, add to generate_game_review():

import time
last_call_time = st.session_state.get('last_ai_call', 0)
now = time.time()

if now - last_call_time < 10:  # 10 second cooldown
    st.warning("Please wait 10 seconds between AI reviews")
    st.stop()

st.session_state['last_ai_call'] = now
```

### Cost Monitoring

```python
# Track total API costs
total_cost = st.session_state.get('total_ai_cost_cents', 0)
total_cost += review.cost_cents
st.session_state['total_ai_cost_cents'] = total_cost

# Alert if exceeding budget
if total_cost > 10000:  # $100 limit
    send_alert_email("AI cost exceeded $100")
```

### Switching to Cheaper Models

For position explanations (short text):
```python
# Use GPT-4o-mini instead of GPT-4 Turbo
model="gpt-4o-mini"  # 60x cheaper, fast, good for short responses
```

## Payment Integration (Next Steps)

### Option 1: Stripe (Recommended)

```bash
pip install stripe
```

See [IMPROVEMENT_IDEAS_AND_PRICING.md](IMPROVEMENT_IDEAS_AND_PRICING.md#payment-integration-stripe) for full implementation.

### Option 2: Lemon Squeezy (Easier)

```bash
pip install lemonsqueezy
```

Pros: Handles VAT, simpler setup
Cons: Higher fees (5% vs Stripe's 2.9%)

### Option 3: Manual (Bootstrap)

Start with manual payments:
1. User emails you
2. You send PayPal/Venmo invoice
3. Manually upgrade their account in database
4. Not scalable, but works for first 10-50 customers

## Database Schema (For Production)

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    tier TEXT DEFAULT 'free',  -- free, hobbyist, serious, coach
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stripe_customer_id TEXT
);

CREATE TABLE ai_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    game_index INTEGER,
    tokens_used INTEGER,
    cost_cents INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_ai_reviews_user_month 
ON ai_reviews(user_id, created_at);
```

Query monthly usage:
```python
def get_monthly_review_count(user_id):
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    return db.execute(
        "SELECT COUNT(*) FROM ai_reviews WHERE user_id = ? AND created_at >= ?",
        (user_id, month_start)
    ).fetchone()[0]
```

## Testing Checklist

- [ ] AI Coach tab appears in navigation
- [ ] Free tier shows upgrade prompt
- [ ] Hobbyist tier allows 2 reviews/month
- [ ] Serious tier allows 5 reviews/month  
- [ ] Coach tier is unlimited
- [ ] Demo mode works without API key
- [ ] Quota resets monthly
- [ ] Reviews are cached (don't regenerate)
- [ ] Cost tracking works
- [ ] Review rendering looks good
- [ ] Mobile responsive

## Going Live

### Minimal Viable Product (MVP)

1. ✅ Core AI Coach logic (`src/ai_coach.py`)
2. ✅ Streamlit UI (`src/ai_coach_ui.py`)
3. ✅ Tab integration
4. ⏳ Stripe payment integration
5. ⏳ User authentication (email/password)
6. ⏳ Database for users & usage tracking

### Week 1: Core Feature

Days 1-2: **Already done!** Core logic + UI
Days 3-4: Test with real API key, polish UI
Days 5-7: User auth + database

### Week 2: Monetization

Days 1-3: Stripe integration
Days 4-5: Upgrade flows, email confirmations
Days 6-7: Beta testing with real users

### Week 3: Launch

Day 1-2: Marketing landing page
Day 3: ProductHunt launch
Day 4-7: Customer support, bug fixes

## Competitive Advantage

| Competitor | AI Coach? | Price | Your Edge |
|------------|-----------|-------|-----------|
| Chess.com | Basic hints | Free-$14.99 | Your AI is personalized, deeper |
| Lichess | None | Free | You offer premium AI insights |
| DecodeChess | Yes | $9.99 | You have puzzles + opening lab + more |
| ChessBase | None | $199 | Your AI is modern, conversational |

**Your positioning**: "The only chess analyzer with GPT-4 powered personal coaching"

## Cost Optimization Tips

1. **Batch reviews**: Allow users to "analyze all games" → generate one comprehensive report (cheaper than per-game)

2. **Caching**: Store AI reviews in database, never regenerate for same game

3. **Smart prompts**: Shorter prompts = lower cost. Current prompts are verbose for quality, can be optimized.

4. **Model selection**:
   - Full review: GPT-4 Turbo (~$0.04)
   - Position insight: GPT-4o-mini (~$0.001)
   - Training plan: GPT-4o (~$0.02)

5. **User education**: Teach users to ask better questions → more value per review

## Future Enhancements

### Phase 2: Advanced Features

1. **Chat with AI Coach**: "Why did I lose this endgame?"
2. **Opponent Prep**: Analyze opponent's games before tournament
3. **Opening Repertoire Builder**: AI suggests openings based on your style
4. **Voice Coach**: Text-to-speech reviews (Eleven Labs)
5. **Video Annotations**: AI generates chessboard videos with voice-over

### Phase 3: Scaling

1. **Tier-specific models**: Free/Hobbyist use GPT-4o-mini, Coach gets GPT-4
2. **Background processing**: Queue reviews, process async
3. **Multi-language**: Offer reviews in 10+ languages
4. **Mobile app**: Native iOS/Android with push notifications

## Support & Troubleshooting

### Common Issues

**"openai module not found"**
```bash
pip install openai
```

**"API key not found"**
```bash
export OPENAI_API_KEY="sk-..."
```

**"Rate limit exceeded"**
- Add delays between requests
- Use exponential backoff
- Switch to GPT-4o-mini for testing

**"Review is too generic"**
- Add more game context to prompt
- Increase `max_tokens` (currently 2000)
- Use GPT-4 instead of GPT-4 Turbo

## Contact

For questions about implementation:
- Check the code comments in `src/ai_coach.py`
- See examples in `src/ai_coach_ui.py`
- Reference pricing doc: `IMPROVEMENT_IDEAS_AND_PRICING.md`

## Summary

✅ **Core feature is ready to use**
✅ **Works in demo mode (no API key needed)**
✅ **Premium tier system implemented**
✅ **Integrated into main app**

**Next steps to go live**:
1. Set up OpenAI API key
2. Add Stripe payment integration
3. Implement user authentication
4. Launch to beta users

**Estimated time to revenue**: 2-3 weeks

**Estimated MRR at 1,000 users**: $2,796/month

**Your cost**: ~$20-50/month in API fees

**Gross margin**: 99%+

This is a high-value, high-margin feature that differentiates your app from competitors and creates recurring revenue. The infrastructure is built - now it's time to monetize! 🚀
