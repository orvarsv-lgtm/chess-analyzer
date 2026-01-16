# Show Move Feature & Best Move Display - Testing Guide

## Features Overview

### 1. Show Move Button (Blunder Navigation)
Added a "Show Move" button to blunder examples that navigates to the exact position in the Game Replayer.

### 2. Best Move Display (NEW)
The Game Replayer now shows the engine's recommended best move for each position.

## Changes Made

### 1. Updated BlunderExample Schema (`src/analytics/schemas.py`)
- Added `color` field to track which player (white/black) made the blunder
- This is needed to correctly calculate the ply position

### 2. Updated Blunder Classifier (`src/analytics/blunder_classifier.py`)
- Modified to capture and store the color of each blunder
- Color is determined from move index: even = white, odd = black

### 3. Updated Engine Analysis (`src/engine_analysis.py`)
- Now captures the best move from Stockfish's principal variation (PV)
- Stores both `best_move_san` (human-readable) and `best_move_uci` (machine format)
- Best move is extracted from the engine's analysis before each player's move

### 4. Enhanced Game Replayer UI (`src/game_replayer.py`)
- Displays best move suggestion for every position (💡 **Best Move:** `Nf3`)
- Shows best move in blue info box below the evaluation metrics
- Always visible when a best move is available from engine analysis

### 5. Enhanced Analysis UI (`streamlit_app.py`)
- Added "🎮 Show" button next to each blunder example
- Added color indicator (⬜ for white, ⬛ for black) 
- Button sets session state to:
  - Switch to Game Replayer tab
  - Select the correct game (using game_index)
  - Jump to the exact move position (calculated from move_number and color)

## Ply Calculation Logic

The ply (half-move) is calculated as follows:
- **For white moves**: `ply = (move_number - 1) * 2 + 1`
  - Example: Move 5 by white = ply 9
- **For black moves**: `ply = move_number * 2`
  - Example: Move 5 by black = ply 10

## How to Test

1. Run an analysis with some games:
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Test Best Move Display:**
   - Navigate to "🎮 Game Replayer" tab
   - Select any game
   - Step through moves
   - You should see "💡 **Best Move:** `Nf3`" (or similar) below the metrics
   - Best move appears for every position analyzed

3. **Test Show Move Button:**
   - Navigate to the Analysis tab
   - Scroll to "Blunder Classification" section
   - Expand "📋 Blunder Examples"
   - Click any "🎮 Show" button
   - App switches to Game Replayer
   - Correct game is selected
   - Board jumps to the blunder position
   - Best move is shown for that position

## Example Output

### Best Move in Game Replayer:
```
Eval Before: +25cp
CP Loss: 312cp
Eval After: -287cp
Phase: Middlegame

💡 Best Move: Nf3

⚠️ Blunder: Hanging Piece
```

### Blunder Examples with Show Button:
```
⬜ Game 3, Move 12: Nf3 (hanging piece) - 543cp loss [middlegame] [🎮 Show]
⬛ Game 5, Move 8: Bxe4 (missed tactic) - 412cp loss [opening] [🎮 Show]
```

After clicking "Show":
- Navigates to Game Replayer
- Shows Game 3 at move 12
- Displays: "💡 **Best Move:** Nbd2" (for example)
- Move 12 (Nf3) is highlighted as a blunder

## Example Output

Before clicking:
```
⬜ Game 3, Move 12: Nf3 (hanging piece) - 543cp loss [middlegame] [🎮 Show]
⬛ Game 5, Move 8: Bxe4 (missed tactic) - 412cp loss [opening] [🎮 Show]
```

After clicking the first example:
- Game Replayer shows Game 3 at move 12 (white's move)
- Board displays position after move 11
- Move 12 (Nf3) is highlighted as a blunder
