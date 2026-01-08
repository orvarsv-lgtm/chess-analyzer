# Chess Analyzer - Current State Summary
**Generated:** January 7, 2026

## 🎯 Core Application

### **Active Entry Points**
1. **main.py** (1001 lines) - CLI analysis tool
   - Fetches games from Lichess API
   - Runs Stockfish analysis (depth 10-18, default 15)
   - Generates coach-style reports
   - Outputs to CSV + TXT files

2. **streamlit_app.py** (1923 lines) - Web UI (PRIMARY)
   - Remote engine analysis via VPS
   - Interactive puzzle trainer
   - Advanced coaching insights
   - Multi-tab interface (Analysis, Puzzles)
   
3. **app.py** (11 lines) - Streamlit entrypoint wrapper

### **Core Modules (src/)**

#### Analysis Pipeline
- **engine_analysis.py** (754 lines) - Stockfish integration
  - Local & remote (VPS) analysis
  - CPL calculation & phase classification
  - Blunder detection & classification
  - Max depth: 18 (reduced from 20)

- **performance_metrics.py** - CPL aggregation by phase
- **lichess_api.py** - Lichess game fetching
- **opening_classifier.py** - ECO code recognition
- **phase2.py** - Strategic analysis & reporting

#### Analytics Intelligence (src/analytics/)
- **aggregator.py** - Multi-game analysis orchestration
- **playstyle_analyzer.py** - Tactical/positional style detection
- **blunder_classifier.py** - Blunder type categorization
- **endgame_analyzer.py** - Endgame performance tracking
- **opening_deviation.py** - Theory deviation detection
- **peer_benchmark.py** - Rating-based percentile comparison
- **recurring_patterns.py** - Pattern detection across games
- **training_planner.py** - Weekly training plan generation
- **population_store.py** - Anonymous aggregate data storage

### **Puzzle System (puzzles/)**

#### Core Puzzle Engine
- **puzzle_engine.py** (990 lines) - Main puzzle generator
  - Parallel processing (4 workers)
  - Pre-filtering (80cp loss threshold)
  - Max 3 puzzles/game, prioritized by eval loss
  - Engine depth: 6 (reduced from 8)

- **puzzle_types.py** (329 lines) - Data schemas
- **puzzle_store.py** (130 lines) - Format conversion (lazy explanations)
- **difficulty.py** - Difficulty classification
- **explanation_engine.py** - Deterministic explanations
- **solution_line.py** - Stockfish continuation computation

#### Global Features
- **global_puzzle_store.py** (211 lines) - Cross-user puzzle sharing
  - JSONL storage: data/puzzles_global.jsonl
  - Rating system (Like/Meh/Dislike)
  - Rating-based prioritization

- **puzzle_cache.py** (75 lines) - Disk caching (24h TTL)
- **stockfish_explainer.py** - Enhanced explanations

#### UI Components (ui/)
- **puzzle_ui.py** (838 lines) - Interactive trainer
  - Multi-move puzzle support
  - Rating buttons (fixed text wrapping)
  - Reveal answer functionality
  - Async solution line computation

- **chessboard_component.py** - Custom React chessboard

### **Tests (tests/)**
- **test_puzzles.py** - Puzzle generation tests (42 passing)
- **test_explanation_engine.py** - Explanation tests (2 known failures)

## �� Data Files

### **Active Data**
- **data/puzzles_global.jsonl** - Global puzzle bank
- **data/puzzle_ratings.jsonl** - User ratings
- **data/population_analytics.jsonl** - Anonymous aggregate stats

### **User Game Data** (16 CSV files)
- games_ari.csv, games_arrow.csv, games_atli.csv, etc.
- Generated analysis: *_analysis.txt (8 files)

### **Reference Data**
- src/Chess_opening_data - Opening ECO database (TSV)

## ⚙️ Configuration

### **Current Settings**
- Analysis depth: 10-18 (default 15, max 18)
- Puzzle engine depth: 6
- Puzzle cache TTL: 24 hours
- Max puzzles per game: 3
- Pre-filter threshold: 80cp loss
- Parallel workers: 4

### **Dependencies** (requirements.txt)
- python-chess - Chess library
- requests - HTTP client
- pandas - Data analysis
- streamlit - Web framework
- dataclasses, hashlib, etc. (stdlib)

## 🔄 Workflow

### **CLI Flow (main.py)**
1. Enter Lichess username
2. Fetch games (max configurable)
3. Analyze with Stockfish (local)
4. Generate report → {username}_analysis.txt
5. Save games → games_{username}.csv

### **Web Flow (streamlit_app.py)**
1. Enter username OR upload PGN
2. Submit to remote VPS engine
3. Display analysis (tabs: Games, Phase Stats, Coach Summary, Puzzles)
4. Interactive puzzle trainer with global bank

## 📈 Performance Optimizations

### **Recent Improvements**
1. **Lazy explanation generation** - Instant puzzle loading (<1ms for 50 puzzles)
2. **Disk caching** - 100x faster on cache hit
3. **Parallel processing** - 3-4x speedup with 4 workers
4. **Pre-filtering** - Skip positions <80cp loss (15% faster)
5. **Reduced engine depth** - 6 instead of 8/10 (20-30% faster)
6. **Corrupt puzzle filtering** - Graceful error handling

## 🎓 Features

### **Analysis**
- ✅ Centipawn loss (CPL) by phase
- ✅ Blunder/mistake detection
- ✅ Opening recognition
- ✅ Playstyle classification
- ✅ Peer benchmarking
- ✅ Training plan generation
- ✅ Endgame analysis
- ✅ Opening deviation tracking

### **Puzzles**
- ✅ Auto-generation from games
- ✅ Global puzzle bank (cross-user)
- ✅ Rating system (Like/Meh/Dislike)
- ✅ Source selection (My games / Other users)
- ✅ Difficulty/type/phase filters
- ✅ Multi-move sequences
- ✅ Disk caching

### **Missing/Future**
- ⏳ Time trouble detection
- ⏳ Opening repertoire builder
- ⏳ Spaced repetition
- ⏳ Game replayer with evaluation graph
- ⏳ Database migration (currently CSV/JSONL)
- ⏳ Mobile optimization
- ⏳ User accounts

## 🏗️ Architecture

### **Design Principles**
- **Deterministic analysis** - No LLMs in core analytics
- **Phase-based organization** - Opening/Middlegame/Endgame
- **Lazy loading** - Compute on-demand, cache aggressively
- **Error resilience** - Graceful degradation, skip corrupt data

### **Technology Stack**
- **Backend:** Python 3.13/3.14
- **Frontend:** Streamlit + Custom React components
- **Engine:** Stockfish (local: /opt/homebrew/bin/stockfish)
- **Storage:** CSV (games), JSONL (puzzles), flat files (reports)
- **Deployment:** Streamlit Cloud (web), local CLI

## 📝 Code Quality

### **Strengths**
- Well-documented with docstrings
- Type hints throughout
- Comprehensive test coverage for puzzles
- Clear separation of concerns
- Defensive error handling

### **Technical Debt**
- CSV storage (should migrate to SQLite)
- Multiple duplicate markdown docs
- Old test files (test_phase1.py, analyze.py)
- Unused utility scripts
- Hardcoded file paths

## 🔢 Statistics

- **Total Python files:** 46
- **Lines of code (main modules):** ~10,000+
- **Documentation files:** 10 markdown files (2103 total lines)
- **Test coverage:** 42/45 tests passing
- **Active users:** Multiple (ari, arrow, atli, john, etc.)

