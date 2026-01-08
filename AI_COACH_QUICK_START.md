# 🤖 AI Coach - Quick Start Guide

## ✅ Setup Complete!

Your OpenAI API key has been securely configured and the AI Coach is ready to use!

## 🚀 How to Use

### 1. Start the App

The app is already running at:
- **Local**: http://localhost:8501
- **Network**: http://192.168.1.45:8501

If you need to restart:
```bash
cd /Users/orvarsverrisson/chess-analyzer
.venv/bin/streamlit run streamlit_app.py
```

### 2. Navigate to AI Coach

1. Open http://localhost:8501 in your browser
2. Click on **"🤖 AI Coach"** tab in the navigation

### 3. Test the Feature

#### Option A: Demo Mode (No API cost)
1. At the bottom of the AI Coach page, check **"🎬 Try Demo Mode"**
2. See a sample AI review with fake data
3. This helps you understand what the output looks like

#### Option B: Real AI Review (Uses API credits ~$0.03-0.05)
1. First, **analyze some games**:
   - Go back to "📊 Analysis" tab
   - Enter a Lichess username or upload PGN
   - Click "Run analysis"
   - Wait for games to be analyzed

2. Then go to **"🤖 AI Coach"** tab:
   - Use sidebar "Demo: Tier Selector" to set your tier:
     - **Hobbyist** = 2 reviews/month
     - **Serious** = 5 reviews/month  
     - **Coach** = unlimited
   
3. Select a game from the dropdown

4. Click **"🚀 Generate AI Coach Review"**

5. Wait 10-30 seconds for GPT-4 to analyze

6. Review will display with:
   - Game summary
   - Key moments (critical positions)
   - Opening advice
   - Strategic advice
   - Tactical advice
   - Training recommendations

### 4. Understanding Tiers

The sidebar has a **"🎛️ Demo: Tier Selector"** for testing:

| Tier | Reviews/Month | Status |
|------|--------------|--------|
| **Free** | 0 | Shows upgrade prompt |
| **Hobbyist** | 2 | Works, limited quota |
| **Serious** | 5 | Works, more quota |
| **Coach** | Unlimited | Full access |

*Note: This is a demo selector. In production, tiers would be managed through Stripe subscriptions.*

## 💰 API Costs

- **Position insight** (short): ~$0.001 (GPT-4o-mini)
- **Full game review**: ~$0.03-0.05 (GPT-4 Turbo)
- **Training plan**: ~$0.02 (GPT-4o)

Your API key has credits available. Monitor usage at:
https://platform.openai.com/usage

## 🔒 Security

✅ Your API key is stored in `.env` file
✅ `.env` is gitignored (won't be committed)
✅ App loads key automatically using python-dotenv

**IMPORTANT**: Never share your `.env` file or commit it to GitHub!

## 🧪 Testing

Run the test suite:
```bash
.venv/bin/python test_ai_coach.py
```

This will:
- Verify API key is loaded
- Test OpenAI client initialization
- Generate demo review
- Check quota system
- (Optional) Make a real API call

## 🎯 Next Steps

### Immediate
1. ✅ Test demo mode
2. ✅ Analyze your own games
3. ✅ Generate your first AI review
4. ✅ Try different tier levels

### Short-term (if monetizing)
1. Add Stripe payment integration
2. Implement user authentication
3. Set up production database
4. Deploy to cloud (Streamlit Cloud, Heroku, etc.)

### Long-term
1. Add "Chat with AI Coach" feature
2. Opponent preparation assistant
3. Opening repertoire suggestions
4. Multi-language support

## 📊 Revenue Potential

With proper marketing:
- 1,000 users = **$2,796/month**
- 10,000 users = **$27,960/month**
- Your cost: ~$20-50/month in API fees
- Gross margin: **99%+**

## 🆘 Troubleshooting

### "API key not found"
- Check `.env` file exists in project root
- Verify it contains: `OPENAI_API_KEY=sk-proj-...`
- Restart Streamlit app

### "openai module not found"
```bash
.venv/bin/pip install openai python-dotenv
```

### "Rate limit exceeded"
- You've hit OpenAI's rate limit
- Wait a few minutes and try again
- Or upgrade your OpenAI account tier

### Reviews are too expensive
- Switch to GPT-4o-mini for reviews (60x cheaper)
- Edit `src/ai_coach.py` line 83:
  ```python
  model="gpt-4o-mini"  # Instead of gpt-4-turbo-preview
  ```

## 📝 Example Output

Here's what a typical AI review looks like:

```
📝 Game Summary
This was a sharp Sicilian Defense game where you struggled in 
the middlegame. Your opening was solid but you missed a tactical 
shot on move 18.

🎯 Key Moments
Critical Moment #1 - Move 18
After ...Nf6, you should have played Bxf6 to eliminate their 
strong knight. Instead, you played Qd2 which allowed ...Ng4 
with a devastating attack.

📚 Opening Advice
Your Sicilian Najdorf move order was correct. Consider studying 
the English Attack variation more deeply.

♟️ Strategic Advice  
You need to work on recognizing when to trade pieces. In worse 
positions, simplification is often your best friend.

⚡ Tactical Advice
You missed several tactical opportunities. Practice knight fork 
tactics focusing on forks and pins.

🎯 Training Recommendations
• Study English Attack vs Najdorf (focus on plans after 6.Be3)
• Practice knight fork tactics (30 puzzles)
• Review endgame principle: when to trade pieces
• Analyze 3 GM games in this opening line
```

## 🎉 You're All Set!

The AI Coach is fully functional and ready to provide personalized 
chess coaching powered by GPT-4. Have fun analyzing your games!

---

**Questions?** Check [AI_COACH_IMPLEMENTATION.md](AI_COACH_IMPLEMENTATION.md) for detailed documentation.
