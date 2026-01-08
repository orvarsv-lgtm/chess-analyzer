# Chess Analyzer - Complete Technical Guide

**Generated from source code analysis - Zero documentation/assumptions, 100% code-derived**

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [Entry Points](#entry-points)
4. [Core Analysis Engine](#core-analysis-engine)
5. [Analytics Pipeline](#analytics-pipeline)
6. [Puzzle System](#puzzle-system)
7. [Data Persistence](#data-persistence)
8. [API Integrations](#api-integrations)
9. [Performance Optimizations](#performance-optimizations)
10. [Code Organization](#code-organization)

---

## System Overview

**Chess Analyzer** is a chess training platform with two interfaces:

1. **CLI Mode** (`main.py`): Terminal-based analysis tool
2. **Web UI** (`streamlit_app.py`): Interactive Streamlit application (PRIMARY interface)

### Core Capabilities
- Fetch games from Lichess API or import Chess.com PGN files
- Analyze games using Stockfish chess engine (local or remote VPS)
- Compute performance metrics (CPL, blunders, mistakes by phase)
- Generate tactical puzzles from analyzed games
- Provide deterministic coaching insights (NO AI/LLM in core analysis)
- Cross-user puzzle sharing with community ratings

### Key Design Principles
- **Deterministic Analysis**: All metrics computed from Stockfish evaluations
- **Phase-Based Classification**: Opening (≤10 moves OR undeveloped pieces), Endgame (≤13 material points), Middlegame (everything else)
- **CLI/Text Output Only**: No charts/GUIs in CLI mode, all visual elements in Streamlit UI
- **Append-Only Storage**: JSONL files for puzzles, ratings, and population data

---

## Architecture & Data Flow

### High-Level Flow

```
┌─────────────────┐
│  User Input     │
│  (Username/PGN) │
└────────┬────────┘
         │
         v
┌─────────────────────────────┐
│  Game Fetching              │
│  - Lichess API (HTTP)       │
│  - Chess.com PGN Files      │
└────────┬────────────────────┘
         │
         v  (PGN text)
┌─────────────────────────────┐
│  PGN Parsing                │
│  (python-chess library)     │
└────────┬────────────────────┘
         │
         v  (moves list in SAN notation)
┌─────────────────────────────┐
│  Engine Analysis            │
│  - Stockfish (local/VPS)    │
│  - Depth: 15 (default)      │
│  - Max depth: 18 (clamped)  │
└────────┬────────────────────┘
         │
         v  (move evaluations with CP scores)
┌─────────────────────────────┐
│  Performance Metrics        │
│  - CPL aggregation          │
│  - Phase classification     │
│  - Blunder detection        │
└────────┬────────────────────┘
         │
         v
┌─────────────────────────────┐
│  Analytics Pipeline         │
│  (7 analytics modules)      │
└────────┬────────────────────┘
         │
         v
┌─────────────────────────────┐
│  Puzzle Generation          │
│  (parallel processing)      │
└────────┬────────────────────┘
         │
         v
┌─────────────────────────────┐
│  Output                     │
│  - CLI: Text report         │
│  - Web: Interactive UI      │
│  - Files: CSV + JSONL       │
└─────────────────────────────┘
```

---

## Entry Points

### 1. CLI Mode: `main.py` (1001 lines)

**Purpose**: Terminal-based analysis for quick batch processing

**Key Functions**:

```python
def main():
    """
    Main CLI entry point.
    Flow:
    1. Prompt for username OR PGN file path
    2. Fetch/import games
    3. Run Phase 1 (engine analysis)
    4. Run Phase 2 (aggregation & reporting)
    5. Save results to CSV and TXT files
    """
```

**CLI Workflow**:
```python
# 1. Get user input
username = input("Enter Lichess username (or press Enter for PGN file): ")

# 2. Fetch games
if username:
    csv_file, game_count = fetch_user_games(username, max_games=50)
else:
    csv_file, game_count = import_pgn_games()

# 3. Analyze games (Phase 1)
results = run_phase1_for_user(username, csv_file, max_games=15, analysis_depth=15)

# 4. Aggregate & report (Phase 2)
run_phase2_for_user(username, max_games=15, games_data=results['games_data'])
```

**Output Files**:
- `games_{username}.csv`: Raw game data (color, score, opening, moves_pgn, elo, etc.)
- `{username}_analysis.txt`: Text report with metrics and coaching insights

---

### 2. Web UI: `streamlit_app.py` (1923 lines)

**Purpose**: Interactive web interface with puzzle trainer

**Key Functions**:

```python
def main():
    """
    Streamlit app with tabs:
    - Game Analysis (fetch games → remote VPS analysis → display results)
    - Puzzle Trainer (load puzzles → interactive trainer with rating system)
    """
```

**Analysis Tab Flow**:
```python
# 1. User selects source (Lichess username or Chess.com PGN file)
source = st.radio("Source", ["Lichess username", "Chess.com PGN file"])

# 2. Fetch PGN text
if source == "Lichess username":
    pgn_text = fetch_lichess_pgn(username, max_games=max_games)
else:
    pgn_text = uploaded_file.getvalue().decode()

# 3. Post to remote VPS engine (FastAPI endpoint)
response = _post_to_engine(
    pgn_text, 
    max_games=max_games, 
    depth=analysis_depth
)

# 4. Process response into aggregated stats
aggregated = _aggregate_postprocessed_results(response['games'])

# 5. Render enhanced UI with charts and coaching insights
_render_enhanced_ui(aggregated)
```

**Puzzle Tab Flow**:
```python
# 1. Load global puzzles from JSONL file
puzzles = load_global_puzzles(
    min_eval_loss=min_eval_loss,
    max_count=100,
    phase_filter=phase_filter,
    type_filter=type_filter
)

# 2. Render interactive puzzle trainer
render_puzzle_trainer(
    puzzles=puzzles,
    show_explanation=True,
    allow_multi_move=True
)

# 3. User solves puzzle → rating saved to JSONL
record_puzzle_rating(puzzle_key, rating="like")
```

---

## Core Analysis Engine

### Engine Analysis: `src/engine_analysis.py` (754 lines)

**Purpose**: Stockfish integration for move-by-move evaluation

#### Key Constants
```python
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"  # macOS default
ANALYSIS_DEPTH = 15  # Default depth
VPS_ANALYSIS_URL = "http://72.60.185.247:8000/analyze_game"  # Remote fallback
```

#### Move Classification Thresholds
```python
def classify_move(cp_loss):
    """
    Classify move quality based on centipawn loss:
    - Best: ≤10cp
    - Excellent: ≤30cp
    - Good: ≤60cp
    - Inaccuracy: ≤150cp
    - Mistake: ≤300cp
    - Blunder: >300cp
    """
```

#### Blunder Subtype Classification
```python
def classify_blunder(board_before, board_after, move, eval_before, eval_after, phase):
    """
    Deterministic heuristics for blunder categorization:
    
    1. Hanging Piece: Piece left undefended and attacked
    2. Missed Tactic: Capture/fork/pin opportunity missed
    3. King Safety: King moved into danger or weakened
    4. Endgame Technique: Error in simplified position
    
    Returns: str (subtype) or None
    """
```

#### Analysis Function
```python
def analyze_game_detailed(moves_pgn_str: str, *, depth: int = 15) -> list[dict]:
    """
    Analyze a game move-by-move using Stockfish.
    
    Args:
        moves_pgn_str: Space-separated SAN moves (e.g., "e4 e5 Nf3 Nc6")
        depth: Stockfish analysis depth (default 15, max 18)
    
    Returns:
        List of move evaluations with fields:
        - move_num: Move number (1, 2, 3...)
        - color: "white" or "black"
        - san: Move in SAN notation (e.g., "Nf3")
        - cp_loss: Centipawn loss (positive integer)
        - cp_loss_weighted: Context-adjusted loss (forced positions weighted lower)
        - piece: Piece moved ("Pawn", "Knight", "Bishop", etc.)
        - phase: Game phase ("opening", "middlegame", "endgame")
        - blunder_type: "blunder", "mistake", "inaccuracy", or None
        - blunder_subtype: Specific error type (if blunder)
        - move_quality: "Best", "Excellent", "Good", "Inaccuracy", "Mistake", "Blunder"
        - eval_before: Eval before move (centipawns, White POV)
        - eval_after: Eval after move
        - is_mate_before: Boolean (was mate eval before move)
        - is_mate_after: Boolean (was mate eval after move)
        - missed_mate: Boolean (missed forced mate)
        - forced_loss: Boolean (already losing badly)
    """
```

#### Phase Classification
```python
def classify_phase_stable(board: chess.Board, move_number: int) -> str:
    """
    Classify game phase using board state heuristics:
    
    Opening:
    - Move number ≤ 10, OR
    - Undeveloped pieces (knights/bishops on back rank)
    
    Endgame:
    - Material ≤ 13 points (Queen=4, Rook=2, Bishop/Knight=1)
    - No queens AND (≤2 rooks OR ≤4 minor pieces)
    
    Middlegame:
    - Everything else
    
    Returns: "opening", "middlegame", or "endgame"
    """
```

### Performance Metrics: `src/performance_metrics.py` (850 lines)

**Purpose**: Aggregate engine data into coaching metrics

#### CPL Computation
```python
def compute_overall_cpl(games_data: list) -> dict:
    """
    Compute overall centipawn loss statistics.
    
    Returns:
        {
            'overall_cpl': float,           # Average CPL across all moves
            'recent_cpl': float,            # CPL for last 3 games
            'trend': str,                   # "improving", "stable", "declining"
            'trend_reason': str,            # Explanation of trend
            'total_blunders': int,          # Moves with >300cp loss
            'total_mistakes': int,          # Moves with 150-300cp loss
            'blunders_per_100': float,      # Normalized rate
            'avg_blunder_severity': float,  # Average CP loss for blunders
            'max_blunder_severity': int,    # Worst single blunder
            'weakest_phase': str,           # Phase with highest CPL
            'blunder_distribution': dict,   # Blunders by phase
            'best_piece': str,              # Piece with lowest CPL
            'worst_piece': str,             # Piece with highest CPL
            'conversion_difficulty': dict,  # Stats when ahead
            'endgame_advantage': dict,      # Endgame conversion stats
            'mate_missed_count': int,
            'forced_loss_count': int,
        }
    """
```

#### Phase Aggregation
```python
def aggregate_cpl_by_phase(games_data: list) -> dict:
    """
    Aggregate CPL by phase (opening/middlegame/endgame).
    
    Returns:
        {
            'opening': {
                'cpl': float,              # Average CPL
                'blunders': int,           # Count
                'games': int,              # Games that reached this phase
                'total_moves': int,
                'advantage': int,          # Reached +1.0 eval or better
            },
            'middlegame': {...},
            'endgame': {...},
        }
    """
```

#### Strengths/Weaknesses Detection
```python
def compute_strengths_weaknesses(games_data: list) -> dict:
    """
    Derive deterministic insights from engine output.
    
    Logic:
    - Compare phase CPL to overall average
    - Strong phase: CPL ≤ 0.85 × overall
    - Weak phase: CPL ≥ 1.15 × overall
    - Analyze piece performance (CPL per piece type)
    - Detect recurring blunder patterns
    
    Returns:
        {
            'strengths': list[str],      # Human-readable strengths
            'weaknesses': list[str],     # Human-readable weaknesses
            'recommendations': list[str], # Training suggestions
        }
    """
```

---

## Analytics Pipeline

### Aggregator: `src/analytics/aggregator.py` (330 lines)

**Purpose**: Orchestrate all analytics modules into comprehensive coaching report

```python
def generate_coaching_report(
    games: list,
    username: str,
    player_rating: int
) -> CoachingSummary:
    """
    Run full analytics pipeline on analyzed games.
    
    Pipeline modules (all deterministic, no LLMs):
    1. blunder_classifier: Categorize blunders by type and phase
    2. endgame_analyzer: Endgame type performance (pawn, rook, etc.)
    3. opening_deviation: Theory deviation detection
    4. recurring_patterns: Pattern recognition across games
    5. training_planner: Weekly training schedule generator
    6. peer_benchmark: Rating bracket comparison
    7. playstyle_analyzer: Tactical/Positional/Aggressive/Defensive classification
    
    Returns: CoachingSummary dataclass with all insights
    """
```

### Analytics Modules

#### 1. Blunder Classifier: `src/analytics/blunder_classifier.py`
```python
def analyze_blunders(games: list) -> BlunderAnalysis:
    """
    Aggregate blunder statistics:
    - Total blunders/mistakes
    - Blunders per 100 moves (normalized)
    - Breakdown by type (hanging piece, missed tactic, king safety, endgame)
    - Breakdown by phase (opening, middlegame, endgame)
    - Example blunders with game references
    """
```

#### 2. Endgame Analyzer: `src/analytics/endgame_analyzer.py`
```python
def analyze_endgames(games: list) -> EndgameBreakdown:
    """
    Classify endgame types and performance:
    - Pawn endgames
    - Rook endgames
    - Queen endgames
    - Minor piece endgames
    
    For each type:
    - Games count
    - Average CPL
    - Blunder rate %
    - Conversion rate % (winning → won)
    """
```

#### 3. Opening Deviation: `src/analytics/opening_deviation.py`
```python
def analyze_opening_deviations(games: list) -> OpeningDeviations:
    """
    Detect theory deviations:
    - Total games with deviations
    - Average deviation move number
    - Average eval loss on deviation
    - Deviations by opening (ECO code + name)
    - Common deviation moves
    """
```

#### 4. Recurring Patterns: `src/analytics/recurring_patterns.py`
```python
def detect_recurring_patterns(games: list) -> RecurringPatterns:
    """
    Find repeated mistakes:
    - Blunder concentration in specific phases
    - Piece-associated errors (e.g., always blunders with knights)
    - Time-related patterns (if time control data available)
    
    Pattern severity: "critical" (≥50% games), "moderate" (≥30%), "minor" (<30%)
    """
```

#### 5. Training Planner: `src/analytics/training_planner.py`
```python
def generate_training_plan(
    blunders: BlunderAnalysis,
    endgames: EndgameBreakdown,
    openings: OpeningDeviations,
    patterns: RecurringPatterns
) -> TrainingPlan:
    """
    Generate weekly training schedule:
    - Primary focus (biggest weakness)
    - Secondary focus
    - Priority endgame types (3 weakest)
    - Priority tactical themes
    - Daily exercises (7-day schedule)
    - Recommended resources (books, courses, tools)
    """
```

#### 6. Peer Benchmark: `src/analytics/peer_benchmark.py`
```python
def compare_to_peers(
    player_rating: int,
    overall_cpl: float,
    phase_cpls: dict,
    blunder_rate: float
) -> PeerComparison:
    """
    Compare to population data (data/population_analytics.jsonl):
    
    Rating brackets:
    - 0-1000, 1000-1200, 1200-1400, 1400-1600, 1600-1800, 1800-2000, 2000+
    
    Metrics:
    - Overall CPL percentile (0-100, higher = better)
    - Phase CPL percentiles
    - Blunder rate percentile
    - Strongest/weakest phases vs peers
    - Blunder rate vs peers (percentage difference)
    """
```

#### 7. Playstyle Analyzer: `src/analytics/playstyle_analyzer.py`
```python
def analyze_playstyle(games: list) -> PlaystyleAnalysis:
    """
    Classify playing style using deterministic heuristics:
    
    Tactical Score (0-100):
    - Captures per game
    - Checks per game
    - Piece exchanges
    
    Positional Score (0-100):
    - Quiet moves ratio
    - Pawn structure preservation
    - Piece development tempo
    
    Aggressive Score (0-100):
    - Early pawn pushes
    - King-side attacks
    - Sacrifices
    
    Defensive Score (0-100):
    - Defensive moves
    - Piece protection
    - King safety priority
    
    Primary/Secondary Style: Top 2 scores
    Style Confidence: Margin between primary and secondary
    
    Piece Performance:
    - Strongest piece (lowest CPL)
    - Weakest piece (highest CPL)
    - Per-piece stats (moves, avg CPL, blunders, captures, checks)
    """
```

---

## Puzzle System

### Puzzle Engine: `puzzles/puzzle_engine.py` (990 lines)

**Purpose**: Extract tactical puzzles from analyzed games

#### Puzzle Trigger Thresholds
```python
MIN_PUZZLE_EVAL_LOSS = 100       # Minimum CP loss to create puzzle (1 pawn)
BLUNDER_EVAL_LOSS = 300          # Clear blunder threshold
OPENING_MOVE_THRESHOLD = 10      # Opening error detection cutoff
MAX_PUZZLES_PER_GAME = 3         # Prioritize best puzzles
PREFILTER_MIN_LOSS = 80          # Skip positions with small losses
```

#### Puzzle Type Classification
```python
def _classify_puzzle_type(
    board: chess.Board,
    best_move: chess.Move,
    played_move: chess.Move,
    eval_loss_cp: int,
    phase: str,
    move_number: int
) -> PuzzleType:
    """
    Deterministic classification:
    
    1. OPENING_ERROR:
       - Deviation before move 10
       - Phase = "opening"
    
    2. ENDGAME_TECHNIQUE:
       - Phase = "endgame"
       - Total pieces ≤ 12 (simplified position)
       - Eval loss ≥ 100cp
    
    3. MISSED_TACTIC (default):
       - Capture, check, fork, pin, or discovery detected
       - Middlegame tactical errors
    """
```

#### Difficulty Classification
```python
def classify_difficulty(eval_loss_cp: int, puzzle_type: PuzzleType) -> Difficulty:
    """
    Difficulty Rules:
    - EASY: Eval loss ≥ 300cp (obvious blunder)
    - MEDIUM: Eval loss ≥ 200cp (clear mistake)
    - HARD: Eval loss ≥ 100cp (subtle inaccuracy)
    
    Special cases:
    - Endgame puzzles: Bump difficulty up (harder to solve)
    - Opening puzzles: Keep as-is (theory-based)
    """
```

#### Puzzle Generation
```python
def generate_puzzles_from_games(
    games_data: list,
    *,
    source_user: str | None = None,
    depth: int = 6
) -> list[Puzzle]:
    """
    Parallel puzzle generation using ThreadPoolExecutor.
    
    Flow:
    1. Pre-filter: Skip moves with <80cp loss
    2. For each candidate move:
       a. Classify puzzle type
       b. Classify difficulty
       c. Generate explanation (Stockfish-based, depth 6)
       d. Create Puzzle dataclass
    3. Prioritize: Keep top 3 puzzles per game (highest eval loss)
    4. Return all puzzles
    
    Parallelization: 4 workers (ThreadPoolExecutor)
    """
```

#### Explanation Generation
```python
def generate_puzzle_explanation(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int,
    puzzle_type: PuzzleType,
    phase: str
) -> str:
    """
    Stockfish-based tactical analysis (NO LLM):
    
    1. Material wins: Detect winning pieces (net material gain)
    2. Piece protection: Analyze defended/undefended pieces
    3. Mate threats: Check for forced mates
    4. Tactical motifs: Fork/pin/discovery detection
    
    Output: Human-readable explanation (e.g., "Wins the queen with a fork")
    """
```

### Global Puzzle Store: `puzzles/global_puzzle_store.py` (222 lines)

**Purpose**: Cross-user puzzle sharing and rating system

#### Storage Format (JSONL)
```python
# data/puzzles_global.jsonl format:
{
    "puzzle_key": "abc123def456",  # SHA1 hash of FEN + first move UCI
    "source_user": "username",
    "ts": 1234567890,              # Unix timestamp
    "puzzle": {                     # Full Puzzle.to_dict()
        "puzzle_id": "5_12",
        "fen": "...",
        "best_move_san": "Nxf7",
        ...
    }
}
```

#### Deduplication
```python
def puzzle_key_for_puzzle(p: Puzzle) -> str:
    """
    Generate stable global key for deduplication:
    
    Key = SHA1(FEN + best_move_uci)[:16]
    
    Ensures same position + solution = same puzzle across all users
    """
```

#### Loading Puzzles
```python
def load_global_puzzles(
    *,
    min_eval_loss: int = 0,
    max_count: int = 100,
    phase_filter: str | None = None,
    type_filter: str | None = None,
    sort_by: str = "rating"
) -> list[Puzzle]:
    """
    Load puzzles from global bank with filters:
    
    Filters:
    - min_eval_loss: Minimum CP loss (difficulty threshold)
    - phase_filter: "opening", "middlegame", or "endgame"
    - type_filter: "missed_tactic", "endgame_technique", "opening_error"
    
    Sorting:
    - "rating": Sort by community rating (likes - dislikes)
    - "difficulty": Sort by eval_loss_cp (descending)
    - "newest": Sort by timestamp (descending)
    
    Returns: List of up to max_count puzzles
    """
```

#### Rating System
```python
# data/puzzle_ratings.jsonl format:
{
    "puzzle_key": "abc123def456",
    "user": "username",
    "rating": "like",  # "like", "meh", or "dislike"
    "ts": 1234567890
}

def record_puzzle_rating(puzzle_key: str, rating: Rating, *, user: str | None):
    """
    Append rating to JSONL file (append-only, no overwrites)
    """

def load_rating_counts() -> dict[str, RatingCounts]:
    """
    Aggregate all ratings for each puzzle:
    
    RatingCounts:
    - dislikes: int
    - mehs: int
    - likes: int
    - total: int (sum)
    - score: int (likes - dislikes)
    """
```

---

## Data Persistence

### File Formats

#### 1. CSV: Game Data
```csv
color,score,opening,opening_name,moves,date,time_control,moves_pgn,white_elo,black_elo,elo,platform
white,win,Sicilian Defense,sicilian_defense,45,2023-10-15,600+0,"e4 c5 Nf3 ...",1523,1498,1523,lichess
```

**Columns**:
- `color`: User's color ("white" or "black")
- `score`: Result ("win", "loss", "draw")
- `opening`: Opening name from PGN header
- `opening_name`: Classified opening from `src/opening_classifier.py`
- `moves`: Total moves in game
- `date`: Game date (YYYY-MM-DD)
- `time_control`: Time control (e.g., "600+0")
- `moves_pgn`: Space-separated SAN moves (e.g., "e4 e5 Nf3 Nc6")
- `white_elo`, `black_elo`, `elo`: Elo ratings
- `platform`: "lichess" or "chess.com"

#### 2. JSONL: Puzzles
```jsonl
{"puzzle_key": "a1b2c3d4", "source_user": "user1", "ts": 1234567890, "puzzle": {...}}
{"puzzle_key": "e5f6g7h8", "source_user": "user2", "ts": 1234567891, "puzzle": {...}}
```

**Benefits**:
- Append-only (fast writes, no file locking)
- No database required
- Easy to parse line-by-line
- Handles crashes gracefully (no corruption)

#### 3. JSONL: Ratings
```jsonl
{"puzzle_key": "a1b2c3d4", "user": "user1", "rating": "like", "ts": 1234567890}
{"puzzle_key": "a1b2c3d4", "user": "user2", "rating": "dislike", "ts": 1234567891}
```

#### 4. JSONL: Population Analytics
```jsonl
{"rating_bracket": "1400-1600", "overall_cpl": 45.3, "opening_cpl": 38.2, "middlegame_cpl": 42.1, "endgame_cpl": 55.7, "blunder_rate": 2.8, "sample_size": 1523}
```

---

## API Integrations

### Lichess API: `src/lichess_api.py`

```python
def fetch_lichess_pgn(username: str, max_games: int = 50) -> str:
    """
    Fetch PGN games from Lichess API.
    
    Endpoint: https://lichess.org/api/games/user/{username}
    Method: GET
    Headers: Accept: application/x-chess-pgn
    Params: max={max_games}, moves=True
    
    Returns: Raw PGN text (multiple games concatenated)
    
    Error Handling:
    - 404 → ValueError: Username not found
    - Timeout → Exception: Request timed out
    - Other → Exception: API error with status code
    """
```

### Chess.com PGN Import

```python
# Chess.com provides monthly PGN archives, not an API
# Users download PGN files manually and upload to app

def import_pgn_games() -> tuple[str, int]:
    """
    CLI: Prompt user for PGN file path
    Streamlit: File uploader widget
    
    Flow:
    1. Load PGN file
    2. Parse games using python-chess
    3. Extract moves, openings, ratings
    4. Save to CSV
    5. Return CSV filename and game count
    """
```

### Remote VPS Engine: `streamlit_app.py`

```python
VPS_ANALYSIS_URL = "http://72.60.185.247:8000/analyze_game"

def _post_to_engine(pgn_text: str, max_games: int, *, depth: int = 15) -> dict:
    """
    Post PGN to remote FastAPI endpoint for analysis.
    
    Endpoint: {VPS_ANALYSIS_URL}?depth={depth}
    Method: POST
    Headers: x-api-key: {api_key} (if configured)
    Body: {"pgn": pgn_text, "max_games": max_games}
    
    Response:
    {
        "success": true,
        "games_analyzed": 10,
        "total_moves": 523,
        "analysis": [...],  # Move-by-move evals
        "games": [...],     # Per-game summaries
        ...
    }
    
    Retries: 2 (3 total attempts)
    Timeout: 300 seconds (5 minutes)
    
    Error Handling:
    - 403 → Authentication failed
    - 404 → Endpoint not found
    - 422 → Validation error (contract mismatch)
    - 500-504 → Retry transient server errors
    """
```

---

## Performance Optimizations

### 1. Parallel Puzzle Generation

```python
# puzzles/puzzle_engine.py
from concurrent.futures import ThreadPoolExecutor

def generate_puzzles_from_games(games_data: list, ...) -> list[Puzzle]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_generate_single_puzzle, game, move_data)
            for game in games_data
            for move_data in game['move_evals']
            if move_data['cp_loss'] >= PREFILTER_MIN_LOSS
        ]
        puzzles = [f.result() for f in futures if f.result()]
    return puzzles
```

**Speedup**: ~4x for puzzle generation on multi-core systems

### 2. Depth Clamping

```python
# src/engine_analysis.py
def analyze_game_detailed(moves_pgn_str: str, *, depth: int = 15):
    # Clamp depth to prevent excessive analysis time
    depth = max(10, min(18, depth))
    
    # Recent change: Reduced from 20 → 18 max depth
    # Puzzle generation: Reduced from 15 → 6 depth
```

**Rationale**: 
- Depth 15 provides good accuracy (±10-20cp margin)
- Depth 18+ diminishing returns (~1% accuracy improvement, 2x+ time cost)
- Puzzle explanations need shallow analysis (depth 6 sufficient for tactics)

### 3. Pre-filtering

```python
# puzzles/puzzle_engine.py
PREFILTER_MIN_LOSS = 80

# Skip moves with <80cp loss before generating puzzles
candidates = [
    move for move in game['move_evals']
    if move['cp_loss'] >= PREFILTER_MIN_LOSS
]
```

**Speedup**: ~70% reduction in puzzle generation calls

### 4. Lazy Loading

```python
# streamlit_app.py
@st.cache_data
def load_global_puzzles(...):
    # Streamlit cache prevents re-loading on every interaction
    ...

# Only load when puzzle tab is active
if active_tab == "Puzzle Trainer":
    puzzles = load_global_puzzles(...)
```

### 5. Context-Aware CPL Weighting

```python
# src/engine_analysis.py
if forced_loss:
    cpl_weight = 0.25  # Already losing badly → mistakes matter less
elif eval_before_player <= -600:
    cpl_weight = 0.5   # Very bad position → reduce blame
elif eval_before_player < -300:
    cpl_weight = 0.7   # Slightly worse → moderate reduction
elif eval_before_player > 100:
    cpl_weight = 1.3   # Winning → mistakes matter MORE

cp_loss_weighted = cp_loss_capped * cpl_weight
```

**Benefit**: More accurate performance assessment (don't penalize "impossible" positions)

---

## Code Organization

### Directory Structure

```
chess-analyzer/
├── main.py                    # CLI entry point (1001 lines)
├── streamlit_app.py           # Web UI entry point (1923 lines)
├── app.py                     # Alias/symlink to streamlit_app.py
│
├── src/                       # Core analysis modules
│   ├── lichess_api.py         # Lichess API integration (200 lines)
│   ├── engine_analysis.py     # Stockfish wrapper (754 lines)
│   ├── performance_metrics.py # CPL aggregation (850 lines)
│   ├── opening_classifier.py  # Opening name detection
│   ├── parser.py              # PGN parsing helpers
│   ├── streamlit_adapter.py   # Format conversion for UI
│   │
│   └── analytics/             # Analytics pipeline modules
│       ├── aggregator.py      # Orchestrator (330 lines)
│       ├── blunder_classifier.py
│       ├── endgame_analyzer.py
│       ├── opening_deviation.py
│       ├── recurring_patterns.py
│       ├── training_planner.py
│       ├── peer_benchmark.py
│       ├── playstyle_analyzer.py
│       ├── population_store.py  # Population data loader
│       └── schemas.py          # Dataclass definitions
│
├── puzzles/                   # Puzzle generation system
│   ├── puzzle_engine.py       # Main puzzle generator (990 lines)
│   ├── puzzle_types.py        # Dataclass schemas (329 lines)
│   ├── difficulty.py          # Difficulty classifier
│   ├── global_puzzle_store.py # JSONL persistence (222 lines)
│   ├── explanation_engine.py  # Stockfish-based explanations
│   ├── stockfish_explainer.py # Enhanced explainer
│   ├── opponent_mistake.py    # Opponent error analysis
│   └── puzzle_ui.py           # Streamlit puzzle trainer (838 lines)
│
├── ui/                        # UI components
│   ├── chessboard_component.py # Custom React chessboard
│   └── puzzle_ui.py           # Puzzle trainer widget
│
├── tests/                     # Test suite
│   ├── test_puzzles.py
│   └── test_explanation_engine.py
│
├── data/                      # Data files (JSONL)
│   ├── puzzles_global.jsonl   # Global puzzle bank
│   ├── puzzle_ratings.jsonl   # User ratings
│   └── population_analytics.jsonl  # Peer comparison data
│
├── games_*.csv                # Saved game data per user
├── *_analysis.txt             # CLI text reports
│
└── requirements.txt           # Python dependencies
    ├── python-chess          # Chess library
    ├── requests              # HTTP client
    ├── pandas                # Data processing
    ├── streamlit             # Web framework
    └── (see file for full list)
```

### Module Dependencies

```
main.py
├── src.lichess_api
├── src.engine_analysis
├── src.performance_metrics
└── pandas

streamlit_app.py
├── src.lichess_api
├── src.engine_analysis
├── src.performance_metrics
├── src.analytics.aggregator  → All 7 analytics modules
├── puzzles.puzzle_engine
├── puzzles.global_puzzle_store
├── ui.puzzle_ui
└── streamlit

src/analytics/aggregator.py
├── blunder_classifier
├── endgame_analyzer
├── opening_deviation
├── recurring_patterns
├── training_planner
├── peer_benchmark
└── playstyle_analyzer

puzzles/puzzle_engine.py
├── puzzle_types
├── difficulty
├── explanation_engine
├── stockfish_explainer
└── concurrent.futures (ThreadPoolExecutor)
```

---

## Typical Execution Flow

### Example: CLI Analysis

```bash
$ python main.py
```

**Console Output**:
```
===================================
   CHESS ANALYZER - CLI MODE
===================================

Enter Lichess username (or press Enter for PGN file): magnuscarlsen
Max games to fetch [50]: 10
Max games to analyze [15]: 10
Engine analysis depth [15]: 15

✓ Successfully fetched PGN data
✓ Parsed 10 games
✓ Saved to games_magnuscarlsen.csv

======================================================================
🔍 PHASE 1: ENGINE ANALYSIS
======================================================================

──────────────────────────────────────────────────────────────────────
📂 MAGNUSCARLSEN   |  10 total games | analyzing up to 10
──────────────────────────────────────────────────────────────────────
  ✓ Game 1: 42 moves analyzed
  ✓ Game 2: 38 moves analyzed
  ...
  ✓ Game 10: 51 moves analyzed

  ✅ Processed: 10/10 games

  📈 OVERALL PERFORMANCE:
     Avg Centipawn Loss (CPL):       35.2 cp/move
     Recent CPL Trend:          improving (last 3 games: 28.4 cp)
     Blunders:                        2 (0.5 per 100 moves)
     Avg blunder severity:          320 cp
     Worst blunder:                 450 cp
     Mistakes:                        8
     ...

  🎯 BY PHASE (board-state heuristic classification):
     Phase        CPL   Blunders  Games  Reached +1.0
     -------------------------------------------------------
     Opening       28.3         0     10            5
     Middlegame    38.1         1     10            7
     Endgame       42.7         1      8            3
     ...

  💡 PHASE INTERPRETATION
  ───────────────────────────────────────────────────────────────
  • Your opening play is relatively stable (CPL: 28.3 cp/move).
  • The endgame shows the most room for improvement (CPL: 42.7 cp/move).
  • Pattern: severe accuracy drops in the endgame, accounting for 50% of all blunders.

  🧠 COACH SUMMARY
  ==============================================================
  • Primary weakness: Endgame accuracy (CPL: 42.7 cp/move)
    (Average blunder: −320 cp, Worst: −450 cp)
  • Pattern: Blunder concentration in endgame (50%)
  • Strength: Stable openings with low CPL (28.3 cp/move)
  • Training focus:
    - Endgame technique and simplification
    - Converting +1.0 positions into wins
    - Calculation accuracy in final phase

======================================================================
📊 PHASE 2: AGGREGATION & REPORTING
======================================================================
...
```

**Output Files**:
- `games_magnuscarlsen.csv`
- `magnuscarlsen_analysis.txt`

---

### Example: Streamlit Analysis

```bash
$ streamlit run streamlit_app.py
```

**Browser UI**:
1. User enters username "magnuscarlsen"
2. Selects max_games=10, depth=15
3. Clicks "Run analysis"
4. App fetches PGN from Lichess
5. App posts to VPS engine (http://72.60.185.247:8000/analyze_game)
6. VPS returns analyzed games
7. App aggregates into phase stats, openings, trends
8. App calls analytics pipeline for advanced insights
9. App renders:
   - Games table (with per-game expandable details)
   - Phase analysis (CPL, blunders, mistakes by phase)
   - Bar charts (CPL by phase, mistakes by phase, blunders by phase)
   - Line chart (CPL trend over games)
   - Coach summary (strengths, weaknesses, recommendations)
   - Advanced insights:
     - Playstyle (Tactical 75, Positional 60, Aggressive 85, Defensive 40)
     - Piece performance (Strongest: Rook, Weakest: Knight)
     - Blunder classification (by type and phase)
     - Endgame breakdown (pawn/rook/queen endgames)
     - Opening deviations (theory mistakes)
     - Recurring patterns (phase-specific errors)
     - Training plan (daily exercises)
     - Peer comparison (rating bracket percentiles)

---

### Example: Puzzle Generation & Training

**Step 1: Generate Puzzles from Analysis**
```python
# In streamlit_app.py after analysis completes
puzzles = generate_puzzles_from_games(
    games_data=analyzed_games,
    source_user=username,
    depth=6  # Shallow depth for puzzle explanations
)
# Result: ~15 puzzles from 10 games (1.5 per game average)
```

**Step 2: Save to Global Bank**
```python
new_count = save_puzzles_to_global_bank(
    puzzles=puzzles,
    source_user=username
)
# Result: 15 new puzzles added (deduped by position)
```

**Step 3: User Solves Puzzles**
```python
# In Puzzle Trainer tab
puzzles = load_global_puzzles(
    min_eval_loss=150,          # Medium+ difficulty
    phase_filter="endgame",     # Focus on endgames
    type_filter=None,           # All types
    sort_by="rating",           # Community favorites first
    max_count=50
)

# User interacts with puzzle
# - Sees FEN position rendered on chessboard
# - Makes move(s)
# - Gets feedback (correct/incorrect)
# - Sees explanation (Stockfish-based tactical analysis)
# - Rates puzzle (like/meh/dislike)

record_puzzle_rating(
    puzzle_key=puzzle.puzzle_key,
    rating="like",
    user=username
)
```

---

## Key Algorithms & Heuristics

### 1. Phase Classification (Board-State Heuristic)

```python
def classify_phase_stable(board: chess.Board, move_number: int) -> str:
    # Opening: Early moves OR undeveloped pieces
    if move_number <= 10:
        return "opening"
    
    # Check for undeveloped pieces (knights/bishops on back rank)
    undeveloped_count = 0
    for square in [chess.B1, chess.G1, chess.C1, chess.F1]:  # White minors
        piece = board.piece_at(square)
        if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            undeveloped_count += 1
    for square in [chess.B8, chess.G8, chess.C8, chess.F8]:  # Black minors
        piece = board.piece_at(square)
        if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            undeveloped_count += 1
    
    if undeveloped_count >= 4:  # Many undeveloped pieces
        return "opening"
    
    # Endgame: Low material (≤13 points)
    material = 0
    material += len(board.pieces(chess.QUEEN, chess.WHITE)) * 4
    material += len(board.pieces(chess.QUEEN, chess.BLACK)) * 4
    material += len(board.pieces(chess.ROOK, chess.WHITE)) * 2
    material += len(board.pieces(chess.ROOK, chess.BLACK)) * 2
    material += len(board.pieces(chess.BISHOP, chess.WHITE)) * 1
    material += len(board.pieces(chess.BISHOP, chess.BLACK)) * 1
    material += len(board.pieces(chess.KNIGHT, chess.WHITE)) * 1
    material += len(board.pieces(chess.KNIGHT, chess.BLACK)) * 1
    
    if material <= 13:
        return "endgame"
    
    # No queens → endgame
    total_queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if total_queens == 0:
        return "endgame"
    
    # Default: middlegame
    return "middlegame"
```

### 2. Primary Issue Detection (5-Tier Priority)

```python
def _choose_primary_issue(overall: dict, phase_stats: dict) -> str:
    """
    Prioritized issue selection:
    
    Tier 1: Phase with ≥50% of all blunders → "Severe [phase] blunders"
    Tier 2: Conversion failures (high CPL when ahead) → "Converting winning positions"
    Tier 3: Mate misses → "Missing forced mates"
    Tier 4: High blunder rate in equal positions → "[phase] accuracy in equal positions"
    Tier 5: Default to weakest phase CPL → "[weakest_phase] phase accuracy"
    """
    total_blunders = overall['total_blunders']
    blunder_dist = overall.get('blunder_distribution', {})
    
    # Tier 1: Phase blunder concentration
    if total_blunders > 0:
        for phase in ['opening', 'middlegame', 'endgame']:
            phase_blunders = blunder_dist.get(phase, 0)
            if phase_blunders / total_blunders >= 0.5:
                return f"Severe {phase} blunders ({phase_blunders}/{total_blunders})"
    
    # Tier 2: Conversion difficulty
    conv = overall.get('conversion_difficulty', {})
    if conv.get('severe_conversion_errors', 0) > 0:
        return "Converting winning positions into wins"
    
    # Tier 3: Mate misses
    if overall.get('mate_missed_count', 0) > 0:
        return "Missing forced mate opportunities"
    
    # Tier 4: Equal position blunders
    # (not implemented in current code, would require position eval tracking)
    
    # Tier 5: Default to weakest phase
    weakest = overall.get('weakest_phase', 'middlegame')
    return f"{weakest.capitalize()} phase accuracy"
```

### 3. Playstyle Classification (Multi-Score)

```python
def _compute_playstyle_scores(games: list) -> dict:
    tactical_score = 0
    positional_score = 0
    aggressive_score = 0
    defensive_score = 0
    
    for game in games:
        for move in game['move_evals']:
            # Tactical indicators
            if move.get('piece_captured'):
                tactical_score += 10
            if move.get('is_check'):
                tactical_score += 5
            
            # Positional indicators (quiet moves)
            if not move.get('piece_captured') and not move.get('is_check'):
                positional_score += 3
            
            # Aggressive indicators (forward pawn pushes, king-side attacks)
            if move.get('piece') == 'Pawn' and move.get('san')[0] in 'fgh':
                aggressive_score += 5
            
            # Defensive indicators (piece protection, retreat moves)
            if move.get('move_quality') in ['Best', 'Excellent']:
                defensive_score += 2
    
    # Normalize to 0-100 scale
    max_score = max(tactical_score, positional_score, aggressive_score, defensive_score)
    if max_score > 0:
        tactical_score = int((tactical_score / max_score) * 100)
        positional_score = int((positional_score / max_score) * 100)
        aggressive_score = int((aggressive_score / max_score) * 100)
        defensive_score = int((defensive_score / max_score) * 100)
    
    # Primary/secondary style
    scores = [
        ('Tactical', tactical_score),
        ('Positional', positional_score),
        ('Aggressive', aggressive_score),
        ('Defensive', defensive_score),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    
    primary_style = scores[0][0]
    secondary_style = scores[1][0]
    style_confidence = scores[0][1] - scores[1][1]  # Margin
    
    return {
        'primary_style': primary_style,
        'secondary_style': secondary_style,
        'style_confidence': style_confidence,
        'tactical_score': tactical_score,
        'positional_score': positional_score,
        'aggressive_score': aggressive_score,
        'defensive_score': defensive_score,
    }
```

---

## Testing

### Test Suite: `tests/test_puzzles.py`

```bash
$ pytest tests/test_puzzles.py -v
```

**Test Coverage**:
- Puzzle generation from sample games
- Difficulty classification edge cases
- Puzzle type classification (opening/middlegame/endgame)
- Global puzzle store operations (save, load, deduplication)
- Rating system (record, aggregate, sort by score)
- Explanation generation (tactical motifs)

**Current Status**: 42/42 tests passing

---

## Configuration & Environment

### Environment Variables
```bash
# Remote VPS engine (optional, falls back to local Stockfish)
VPS_ANALYSIS_URL="http://72.60.185.247:8000/analyze_game"
VPS_API_KEY="your-api-key-here"  # Optional authentication

# Endgame inflation baseline (for peer comparison, optional)
NORMAL_ENDGAME_INFLATION_PCT="15.0"  # Typical endgame CPL inflation %
```

### Stockfish Binary Path
```python
# src/engine_analysis.py
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"  # macOS Homebrew default

# For other systems:
# Linux: "/usr/bin/stockfish"
# Windows: "C:\\Program Files\\Stockfish\\stockfish.exe"
# Custom: Set STOCKFISH_PATH environment variable
```

### Dependencies
```txt
# requirements.txt
python-chess==1.999
requests==2.31.0
pandas==2.1.4
streamlit==1.29.0
dataclasses-json==0.6.3
```

---

## Summary

The Chess Analyzer is a **deterministic, engine-based chess training platform** with:

1. **Dual Interfaces**: CLI (batch processing) and Web UI (interactive)
2. **Comprehensive Analysis**: CPL by phase, blunder classification, endgame/opening breakdowns
3. **Advanced Insights**: 7-module analytics pipeline (playstyle, peer comparison, training plans)
4. **Puzzle System**: Parallel generation, global sharing, community ratings
5. **Performance Optimized**: Parallel processing, depth clamping, pre-filtering, lazy loading
6. **Data-Driven**: Append-only JSONL storage, CSV game archives
7. **API Integrations**: Lichess API, remote VPS engine, Stockfish UCI
8. **No AI/LLM**: All analysis deterministic (Stockfish + heuristics)

**Target Users**: Chess players (800-2200 Elo) seeking personalized coaching insights

**Technology Stack**: Python 3.13+, Stockfish, Streamlit, python-chess, pandas

**Code Metrics**:
- Total Lines: ~8000+ (core codebase)
- Main Files: main.py (1001), streamlit_app.py (1923), puzzle_engine.py (990)
- Modules: 25+ (src, analytics, puzzles, ui)
- Tests: 42 passing

---

*End of Technical Guide - Generated from source code only, no documentation assumptions*
