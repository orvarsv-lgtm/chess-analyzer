# Chess Analyzer - Engine Analysis Implementation

## Summary of Changes

All three files have been updated to support proper engine analysis with full move lists stored.

---

## 1. parser.py (UPDATED)

**Changes:**
- Now extracts full move list in SAN (Standard Algebraic Notation) format
- Stores moves as a space-separated string in `moves_pgn` field
- This string is saved to CSV for later engine analysis

**Key additions:**
```python
# Extract moves as space-separated SAN notation
moves_list = []
board = game.board()
for move in game.mainline_moves():
    moves_list.append(board.san(move))
    board.push(move)
moves_pgn = " ".join(moves_list)

# Added to game_info dict:
"moves_pgn": moves_pgn,
```

**Output:** Each game now has columns:
- `white`, `black`, `result`, `opening`, `moves` (count), `moves_pgn` (full move string)

---

## 2. engine_analysis.py (REWRITTEN)

**Changes:**
- Replaced `stockfish` library with `chess.engine.SimpleEngine` (standard python-chess)
- Function renamed: `analyze_game()` → `analyze_game_from_moves()`
- Takes a space-separated move string as input (from CSV)
- Analyzes moves and prints:
  - **Blunders** (≥150 cp loss)
  - **Mistakes** (≥50 cp loss)
  - Average centipawn loss
  - Maximum centipawn loss

**Key function signature:**
```python
def analyze_game_from_moves(moves_pgn_str):
    """
    Analyze a game given a space-separated move string.
    Returns blunders, mistakes, and average centipawn loss.
    """
```

**Output example:**
```
==================================================
ENGINE ANALYSIS - 40 moves
==================================================

🔴 BLUNDERS (2):
  Move 15: Nd4 (-152 cp)
  Move 28: Bg5 (-175 cp)

🟡 MISTAKES (3):
  Move 8: Bb5 (-85 cp)
  Move 22: h4 (-62 cp)
  Move 35: Nxe5 (-51 cp)

📊 Average Centipawn Loss: 28.5 cp
   Max Loss: 175 cp
```

---

## 3. main.py (MINIMAL CHANGES)

**Changes:**
- Import `analyze_game_from_moves` instead of `analyze_game`
- At the end of statistics output, call engine analysis on most recent game
- Engine analysis is optional (only runs if `moves_pgn` exists)

**Added code:**
```python
# Engine analysis for most recent game
if len(df) > 0 and "moves_pgn" in df.columns:
    most_recent_game = df.iloc[0]
    moves_pgn = most_recent_game.get("moves_pgn", "")
    
    if moves_pgn:
        print("\n" + "=" * 50)
        print("ENGINE ANALYSIS (Most Recent Game)")
        print("=" * 50)
        analyze_game_from_moves(moves_pgn)
```

**Constraints met:**
- ✅ Existing statistics not broken
- ✅ Games not re-downloaded unnecessarily (cached in CSV)
- ✅ Engine analysis optional and fast
- ✅ Runs `analyze_game_from_moves()` after statistics

---

## File Locations

- `src/parser.py` - Extracts full move lists
- `src/engine_analysis.py` - Analyzes moves with Stockfish
- `src/main.py` - Main flow, calls engine analysis on most recent game

## Usage

```bash
python src/main.py
# Enter Lichess username when prompted
# Program loads/fetches games, shows statistics
# Engine analyzes most recent game with blunders/mistakes
```

## Dependencies

- `python-chess` (for chess.engine.SimpleEngine)
- `requests` (for API)
- `pandas` (for data)
- `stockfish` binary at `/opt/homebrew/bin/stockfish`
