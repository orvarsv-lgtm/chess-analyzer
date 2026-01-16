# Show Move Feature - Testing Guide

## Feature Overview
Added a "Show Move" button to blunder examples that navigates to the exact position in the Game Replayer.

## Changes Made

### 1. Updated BlunderExample Schema (`src/analytics/schemas.py`)
- Added `color` field to track which player (white/black) made the blunder
- This is needed to correctly calculate the ply position

### 2. Updated Blunder Classifier (`src/analytics/blunder_classifier.py`)
- Modified to capture and store the color of each blunder
- Color is determined from move index: even = white, odd = black

### 3. Enhanced UI (`streamlit_app.py`)
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

2. Navigate to the Analysis tab and scroll to "Blunder Classification" section

3. Expand "📋 Blunder Examples"

4. Click any "🎮 Show" button

5. Expected behavior:
   - App switches to "🎮 Game Replayer" tab
   - Correct game is selected in the dropdown
   - Board position jumps to the exact move where the blunder occurred
   - You can see the blunder highlighted in the move list

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
