# Chess Analyzer: Comprehensive Software Guide

## Executive Summary

**Chess Analyzer** is a sophisticated, deterministic chess analysis platform that fetches games from Lichess, analyzes them using Stockfish, and generates personalized, coach-ready reports and training content. The software is **100% free to use** and operates entirely without AI/LLM randomness—all analysis is rule-based, deterministic, and transparent.

The platform serves three distinct user needs:
1. **Game Analysis**: Detailed performance metrics, blunder detection, and phase-based error analysis
2. **Training Puzzles**: Automatically generated tactical exercises derived from your actual mistakes
3. **AI Coaching Reports** (optional premium tier): GPT-powered narrative insights into your play patterns

---

## Core Architecture Overview

The software is built on a **layered, modular architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Interface (Streamlit)               │
│         Desktop CLI (main.py) | Mobile-optimized UI        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer (app.py)               │
│  Game Caching | User Auth | Billing/Subscriptions         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Analytics & Coaching Layer                │
│  AI Coach Reports | Data-Driven Coaching | Training Plans  │
│  Blunder Classification | Opening Analysis | Playstyle     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Puzzle Generation & Training Layer             │
│  Tactical Pattern Detection | Difficulty Classification    │
│  Puzzle Explanation Engine | Supabase Puzzle Store         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Core Analytics & Metrics Layer                 │
│  Performance Metrics | Game Phase Classification           │
│  CPL Computation | Strength/Weakness Analysis              │
│  Opening Intelligence | Time Control Analysis              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│               Engine & Data Fetching Layer                  │
│  Lichess API Integration | Stockfish Engine Interface      │
│  PGN Parsing | Move-by-move Analysis                      │
│  Remote VPS Engine Support (cloud fallback)                │
└─────────────────────────────────────────────────────────────┘
```

---

## Feature Set (Comprehensive)

### **1. Game Fetching & Parsing**
- **Lichess API Integration** (`src/lichess_api.py`)
  - Fetch up to 50+ recent games per username
  - Parse PGN format with full move notation
  - Extract clock times, opening names, ELO ratings, results
  - Real-time validation: username exists on Lichess
  - Error handling for API timeouts and connection issues

### **2. Engine Analysis (Deterministic, No AI)**
- **Stockfish Integration** (`src/engine_analysis.py`)
  - Depth-15 analysis (configurable) of every move
  - Calculates centipawn loss (CP loss) for each move
  - Identifies best moves vs. played moves
  - Dual engine support:
    - **Local Stockfish**: `/opt/homebrew/bin/stockfish` (macOS/Linux)
    - **Remote VPS Engine**: Cloud-based analysis fallback for Streamlit Cloud environments
  - Move quality classification: Best → Excellent → Good → Inaccuracy → Mistake → Blunder

### **3. Blunder Detection & Classification**
- **Intelligent Categorization** (`src/engine_analysis.py` + `src/analytics/blunder_classifier.py`)
  - Automatic blunder subtype detection:
    - **Hanging Piece**: Moved piece becomes under-defended
    - **Missed Tactic**: Overlooked forcing moves (checks, captures)
    - **King Safety**: Move exposes or weakens king position
    - **Endgame Technique**: Low-material blunders with large swings
    - **Unknown**: Blunders that don't fit other categories
  - Normalized per 100 moves for fair comparison across game lengths
  - Severity tracking: average and maximum centipawn swings

### **4. Game Phase Classification**
- **Hybrid Phase Detector** (`src/performance_metrics.py`)
  - Rule-based, deterministic classification:
    - **Opening**: Moves 1–10 OR 2+ undeveloped minor pieces
    - **Middlegame**: Complex position with material still on board
    - **Endgame**: Total non-pawn material ≤ 13 points (~R+minor vs R+minor)
  - Every move mapped to exactly one phase (strict assertion prevents bugs)
  - Phase-specific performance metrics and error rates

### **5. Performance Metrics**
- **Centipawn Loss (CPL) Analysis** (`src/performance_metrics.py`)
  - Overall CPL: Average centipawn loss across all moves
  - Recent CPL: Last 10 games trend (improving/declining/stable)
  - Phase-wise CPL: Separate metrics for opening, middlegame, endgame
  - Blunder frequency: Per-100-move normalized rates
  - Mistake frequency: Differentiation between blunders (>300 CP) and mistakes (150-300 CP)
  - Winning threshold: Elo-based dynamic adjustment (beginners need bigger advantages to "win")

### **6. Strengths & Weaknesses Analysis**
- **Deterministic Heuristic Engine** (`src/performance_metrics.py`)
  - Identifies phase-specific strengths:
    - "Strong opening preparation" (if opening CPL ≤ 85% of baseline)
    - "Stable middlegame decision-making" (if middlegame CPL ≤ 85% of baseline)
    - "Solid endgame technique" (if endgame CPL ≤ 85% of baseline)
  - Identifies phase-specific weaknesses:
    - "Opening accuracy drops early" (CPL ≥ 115% of baseline)
    - "Middlegame accuracy drops under complexity"
    - "Endgame accuracy drops in simplified positions"
  - Blunder-rate signals:
    - "Low blunder rate" (≤ 1.0 per 100 moves)
    - "High blunder rate" (≥ 3.0 per 100 moves)
    - "Many medium-strength mistakes" (≥ 6.0 per 100 moves)

### **7. Opening Analysis & Repertoire Tracking**
- **Opening Classifier** (`src/opening_classifier.py`)
  - 40+ opening pattern recognition (ECO-based move sequences)
  - Covers: Ruy Lopez, Sicilian, French, Caro-Kann, Queen's Gambit, King's Indian, etc.
  - Per-opening statistics: Win rate, average CPL, frequency
  - Opening deviation detection (`src/analytics/opening_deviation.py`)
  - Opening outcomes aggregation: Favorite openings vs. problem openings

### **8. Opponent Strength & Rating-Adjusted Analysis**
- **Rating-Aware Performance** (`src/opponent_strength.py`)
  - Expected CPL adjusted by opponent rating
  - Performance vs. rating brackets: Under 1000, 1000–1500, 1500+
  - Identifies upsets (wins vs. much stronger opponents)
  - Identifies highlights (impressive performances)
  - Elo-based "winning threshold" adjustment for fair comparisons

### **9. Time Management Analysis**
- **Clock Time Tracking** (`src/time_analysis.py`)
  - Per-move clock time extraction from PGN comments
  - Time pressure detection: Moves made with <30 seconds remaining
  - Correlation: Blunders under time pressure vs. when ahead on the clock
  - Time control performance: Blitz vs. Rapid vs. Classical

### **10. Tactical Puzzle Generation**
- **Deterministic Puzzle Engine** (`puzzles/puzzle_engine.py`)
  - Automatically extract positions from analyzed games where mistakes occurred
  - Difficulty classification (`puzzles/difficulty.py`):
    - Bronze (1000–1200): Beginner tactics
    - Silver (1200–1600): Intermediate tactics
    - Gold (1600–2000): Advanced tactics
    - Platinum (2000+): Expert-level patterns
  - Puzzle types:
    - Tactical Win (clear best move beats opponent)
    - Defensive (escape bad position)
    - Opening Error (early deviation recovery)
    - Endgame Technique (material conversion)
  - Max 3 puzzles per game (prioritize highest-loss positions)

### **11. Tactical Pattern Detection**
- **Advanced Pattern Analysis** (`puzzles/tactical_patterns.py`)
  - Constraint-based pattern recognition:
    - Atomic constraints: Pin, Fork, Skewer, Promotion, Trapped piece, etc.
    - Composite patterns: Combination of multiple constraints
    - Advanced patterns: Quiet moves, prophylaxis, zugzwang
  - Pattern attribution: Why a move works (tactical motif breakdown)
  - Explanation engine: Convert patterns into human-readable descriptions
  - Recurring pattern detection: Which tactical themes appear in your blunders?

### **12. Puzzle Explanation Engine**
- **Multi-Level Explanations** (`puzzles/explanation_engine.py` + `puzzles/stockfish_explainer.py`)
  - Simple: "This is a fork" (basic pattern)
  - Detailed: "White's knight on d5 attacks both the rook on b6 and the king. Moving the knight forks the pieces."
  - Stockfish-enhanced: Engine-generated principal variation showing why the move wins
  - Solution lines: Best continuation after your move
  - Context-aware: Explains what you could have done instead

### **13. AI Coach Reports (Premium Feature)**
- **GPT-Powered Narrative Analysis** (`src/ai_coach.py`)
  - **Game Review**: Diagnostic narrative of what decided each game, what you learned
  - **Position Insight**: Deep analysis of key turning points
  - **Training Plan**: Personalized weekly study recommendations
  - **Career Analysis**: Long-term trends across 10+ games
  - Cost tracking: Estimated API costs per review (configurable)
  - Quota management: Free (0 reviews/month), Hobbyist ($9.99: 2/month), Serious ($19.99: 5/month), Coach ($49.99: Unlimited)
  - Fallback to deterministic coaching if API fails

### **14. Data-Driven Coaching (Deterministic, Non-AI)**
- **Rule-Based Coach** (`src/data_driven_coach.py`)
  - Game summary explanations (non-LLM)
  - Opening outcome analysis (where you struggle with which openings)
  - Failure pattern detection (patterns in your losses)
  - Tactical weakness identification
  - Training recommendations based on data
  - Structured coaching sections (LLM-ready JSON)

### **15. Playstyle Analysis**
- **Player Profile Detection** (`src/analytics/playstyle_analyzer.py`)
  - Identifies playing style:
    - Tactical player (high blunder rate but also high win rate in complications)
    - Solid player (low CPL, grinding style)
    - Aggressive player (many sacrifices, risky play)
  - Time management profile: Slow/rapid/blitz specialist
  - Opening preferences and success rates
  - Endgame confidence metrics

### **16. Recurring Pattern Detection**
- **Cross-Game Pattern Analysis** (`src/analytics/recurring_patterns.py`)
  - Identifies blunder patterns that repeat:
    - "You hang knights in the middlegame 5 times"
    - "You miss back-rank tactics in rapid games"
    - "You struggle against the Sicilian in blitz"
  - Helps prioritize training by frequency and impact

### **17. Population Benchmarking**
- **Peer Comparison** (`src/analytics/peer_benchmark.py`)
  - Compares your CPL to population norms
  - Rating-based percentile ranking (e.g., "Your CPL is better than 75% of 1500-rated players")
  - Anonymous, privacy-preserving population store
  - Helps contextualize your performance

### **18. Game Caching & Performance**
- **Persistent Cache** (`src/game_cache.py`)
  - Caches analyzed games to avoid re-analysis
  - Stores to CSV with moves, evals, blunders, phases
  - Game ID extraction and deduplication
  - Cache hit rate tracking

### **19. User Authentication & Billing**
- **Subscription Management** (`src/auth.py` + `src/paddle_integration.py`)
  - Email-based user accounts
  - Paddle payment integration (European payment processor)
  - Subscription tiers with feature gates
  - Usage tracking (AI Coach reviews per tier)
  - Seamless checkout flow

### **20. Mobile-Optimized UI**
- **Device Detection & Adaptation** (`src/mobile_detection.py`)
  - Detects device type (mobile, tablet, desktop)
  - User-agent parsing for platform identification
  - Responsive layout adjustment for small screens
  - Mobile-friendly board rendering
  - Touch-optimized buttons and controls

### **21. Web Application (Streamlit)**
- **Multi-page Streamlit App** (`streamlit_app.py`)
  - Home page: Username input, game fetching
  - Game analysis results: Interactive display of metrics
  - Puzzle page: Generated puzzles with board visualization
  - AI Coach reports: Narrative coaching insights
  - Pricing page: Subscription tier comparison
  - Legal pages: Terms of Service, Privacy Policy, Refund Policy

### **22. CLI Interface**
- **Command-Line Tool** (`main.py`)
  - Interactive prompts for username entry
  - Game fetching and batch analysis
  - CSV output for game data
  - TXT report output for human-readable analysis
  - Session logging and error recovery

---

## Data Flow & Processing Pipeline

### **Step 1: Game Fetching**
```
User enters Lichess username
    ↓
Fetch from Lichess API (lichess_api.py)
    ↓
Parse PGN, extract moves, clock times, result
    ↓
Validate game format, check for completeness
```

### **Step 2: Engine Analysis**
```
For each game's moves:
    ↓
Run Stockfish at depth 15 on each position
    ↓
Record: evaluation before move, evaluation after move
    ↓
Calculate: centipawn loss, move quality
    ↓
Classify: blunder type (if applicable)
    ↓
Detect phase: opening/middlegame/endgame
```

### **Step 3: Metrics Computation**
```
Aggregate per-game data:
    ↓
Compute overall CPL (average centipawn loss)
    ↓
Compute CPL per phase
    ↓
Count blunders/mistakes per 100 moves
    ↓
Identify strengths/weaknesses
    ↓
Analyze openings performance
    ↓
Compute time management stats
    ↓
Detect opponent strength patterns
```

### **Step 4: Coaching Report Generation**
```
Deterministic path (free):
    ↓
Generate data-driven coaching (no LLM)
    ↓
Format as readable text report
    
Optional: AI Coach path (premium):
    ↓
Call GPT-4o-mini with game data + coaching prompt
    ↓
Generate narrative insights
    ↓
Track API usage and cost
    ↓
Format as markdown report
```

### **Step 5: Puzzle Generation**
```
For each game:
    ↓
Identify positions with centipawn loss ≥ 100
    ↓
Classify puzzle type (tactical, defensive, etc.)
    ↓
Classify difficulty based on eval loss and game level
    ↓
Generate explanation (pattern-based + Stockfish)
    ↓
Store puzzle with metadata
    ↓
Max 3 puzzles per game (highest loss first)
```

### **Step 6: Output**
```
Generate reports:
    ↓
CSV: games_{username}.csv (raw game data)
    ↓
TXT: {username}_analysis.txt (human-readable report)
    ↓
Store puzzles in Supabase (optional, premium)
    ↓
Web UI displays all analyses interactively
```

---

## Technical Specifications

### **Languages & Dependencies**
- **Python 3.8+**: Core implementation
- **Streamlit**: Web UI framework
- **python-chess**: Chess logic, board representation, move validation
- **Stockfish**: UCI chess engine (local binary or remote VPS)
- **Pandas**: Data manipulation and CSV handling
- **Requests**: Lichess API integration
- **OpenAI**: Optional GPT integration for AI Coach (premium)
- **Paddle**: Payment processing (premium)
- **Supabase**: Cloud database for puzzles (optional)

### **System Requirements**
- **Stockfish**: Installed at `/opt/homebrew/bin/stockfish` (macOS) or configurable path
- **Python Virtual Environment**: `.venv` for dependency isolation
- **RAM**: ~500 MB minimum (can grow with large game batches)
- **Disk**: ~10 MB per user (CSV + analysis outputs)

### **Configuration**
- **Analysis Depth**: Default 15, configurable per session
- **Max Games Fetched**: Default 50, adjustable
- **Stockfish Path**: Environment variable `STOCKFISH_PATH` or auto-detect
- **Remote Engine**: `VPS_ANALYSIS_URL` for cloud fallback
- **API Keys**: 
  - Lichess: Public API (no key required)
  - OpenAI: `OPENAI_API_KEY` (if using AI Coach)
  - Supabase: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (if using puzzle store)
  - Paddle: Payment credentials (if using subscriptions)

---

## Pricing & Monetization

### **Free Tier (€0/month)**
- ✅ Game fetching & analysis
- ✅ Performance metrics (CPL, blunders, phases)
- ✅ Strengths & weaknesses
- ✅ Opening analysis
- ✅ Time management stats
- ✅ Puzzle generation
- ❌ AI Coach reports (0 reviews/month)
- ❌ Advanced features

### **Basic Tier (€9/month)**
- All free features +
- 2 AI Coach reviews/month
- Basic data visualization

### **Plus Tier (€19/month) — BEST VALUE**
- All basic features +
- 5 AI Coach reviews/month
- Advanced playstyle analysis
- Premium puzzle recommendations

### **Pro Tier (€29/month)**
- All plus features +
- Unlimited AI Coach reviews
- Dedicated prioritization
- Early access to new features

---

## Key Insights & Philosophy

### **Why This Software Matters**

1. **Deterministic, Not AI-Driven**: No randomness, no black boxes. All analysis is transparent, rule-based, and reproducible.

2. **Free Core Analysis**: Everyone gets deep performance insights at zero cost. Coaching is optional.

3. **Personalized Training**: Puzzles are generated from *your* mistakes, not generic exercises. Maximum relevance.

4. **Coach-Ready Reports**: Output is written in plain English, formatted for human coaches to review and act on.

5. **Comprehensive Coverage**: From raw move analysis to career-spanning trends. No gaps.

6. **Privacy-First**: All analysis is local (except optional cloud features). No tracking, no behavioral data sales.

### **Performance Optimization**

- **Game Caching**: Avoid re-analyzing the same games
- **CSV Storage**: Efficient raw game data persistence
- **Remote Engine Fallback**: Graceful degradation in cloud environments
- **Pagination**: Handle 50+ games without memory bloat
- **Lazy Loading**: On-demand puzzle generation and explanation

---

## Common Use Cases

### **Coach Using Chess Analyzer**
1. Student's parent enters username
2. Fetch 20 recent games
3. Read coach summary: "Struggling with endgame conversion, missing back-rank tactics"
4. Generate training plan: "Practice endgame positions, 5 back-rank tactic puzzles per week"
5. Track progress over 4 weeks

### **Self-Improving Player**
1. Run analysis on 50 games
2. Discover: "You miss forks 5 times, mostly in blitz"
3. Generate 15 fork-focused puzzles
4. Train for 2 weeks on those specific patterns
5. Re-analyze: Fork-related blunders dropped 60%

### **Tournament Preparation**
1. Analyze games vs. previous tournament opponents
2. Identify opening weaknesses (e.g., always lose with Black after 1.d4)
3. Study specific repertoire improvements (puzzles for those openings)
4. Practice time management in rapid/blitz variants

### **Rating Milestone Achievement**
1. Analyze 100-game career
2. Export peer benchmark: "Your CPL is in the top 30% for your rating"
3. Identify top 3 priorities for improvement
4. Monthly re-analysis to track progress

---

## File Structure (Key Files)

```
chess-analyzer/
├── main.py                          # CLI entry point
├── app.py                           # Streamlit web UI wrapper
├── streamlit_app.py                 # Full Streamlit application
├── requirements.txt                 # Python dependencies
│
├── src/
│   ├── lichess_api.py              # Lichess API integration
│   ├── engine_analysis.py           # Stockfish analysis
│   ├── performance_metrics.py       # CPL, phases, metrics
│   ├── phase2.py                    # Aggregated player analysis
│   ├── ai_coach.py                  # AI Coach reports (GPT)
│   ├── data_driven_coach.py         # Deterministic coaching
│   ├── opening_classifier.py        # 40+ opening patterns
│   ├── time_analysis.py             # Clock time tracking
│   ├── auth.py                      # User authentication
│   ├── game_cache.py                # Game caching
│   ├── mobile_detection.py          # Device detection
│   ├── pricing_ui.py                # Pricing page
│   ├── paddle_integration.py        # Payment integration
│   ├── opponent_strength.py         # Rating-adjusted analysis
│   ├── opponent_mistake.py          # Opponent blunder detection
│   ├── play_vs_engine.py            # Engine play feature
│   ├── game_replayer.py             # Game replay
│   ├── opening_repertoire.py        # Repertoire tracking
│   ├── streak_detection.py          # Win/loss streak detection
│   ├── quick_wins.py                # Quick analysis
│   ├── analytics/                   # Advanced analytics
│   │   ├── aggregator.py            # Coaching report aggregator
│   │   ├── blunder_classifier.py    # Blunder categorization
│   │   ├── endgame_analyzer.py      # Endgame material analysis
│   │   ├── opening_deviation.py     # Opening deviation detection
│   │   ├── opening_style.py         # Opening style detection
│   │   ├── playstyle_analyzer.py    # Playing style profiling
│   │   ├── recurring_patterns.py    # Cross-game patterns
│   │   ├── peer_benchmark.py        # Population benchmarking
│   │   ├── training_planner.py      # Training recommendations
│   │   └── schemas.py               # Data models
│   │
│   ├── Chess_opening_data/          # Opening database
│   └── translations.py              # i18n support
│
├── puzzles/                         # Puzzle generation module
│   ├── puzzle_engine.py             # Main puzzle generator
│   ├── puzzle_types.py              # Puzzle data models
│   ├── difficulty.py                # Difficulty classification
│   ├── explanation_engine.py        # Puzzle explanations
│   ├── tactical_patterns.py         # Advanced pattern detection
│   ├── stockfish_explainer.py       # Stockfish-based explanations
│   ├── puzzle_cache.py              # Puzzle caching
│   ├── puzzle_store.py              # Local puzzle storage
│   ├── global_puzzle_store.py       # Global puzzle index
│   ├── solution_line.py             # Solution continuation lines
│   ├── supabase_client.py           # Supabase integration
│   ├── global_supabase_store.py     # Cloud puzzle store
│   └── puzzle_ui.py                 # Puzzle display UI
│
├── tests/                           # Test suite
├── pages/                           # Streamlit pages (privacy, legal)
├── data/                            # Data files
│   ├── puzzles_global.jsonl         # Global puzzle database
│   └── population_analytics.jsonl   # Population benchmarks
│
├── games_*.csv                      # Per-user game data
└── *_analysis.txt                   # Per-user analysis reports
```

---

## Summary

Chess Analyzer is a **free, comprehensive, deterministic chess analysis platform** that turns Lichess games into actionable coaching insights and personalized training puzzles. It combines:

- **Powerful engine analysis** (Stockfish depth-15)
- **Intelligent metrics** (CPL, phases, patterns)
- **Deterministic coaching** (no AI needed)
- **Optional premium AI insights** (GPT-powered narratives)
- **Personalized training** (puzzles from your mistakes)
- **Privacy-first architecture** (local-first, optional cloud)

Whether you're a coach analyzing students, a player improving your game, or a tournament player preparing for specific opponents, Chess Analyzer provides the data, insights, and training you need—**completely free**.

