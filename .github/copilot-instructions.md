# Copilot Instructions for AI Agents

## Project Overview
- **Chess Analyzer** is a CLI tool for analyzing Lichess games using Stockfish, producing coach-ready reports with detailed performance metrics.
- The codebase is organized in **phases**: Phase 1 (core analytics), Phase 2 (strategic aggregation/reporting), Phase 3 (intelligence/recommendations).
- All analysis is deterministic—no randomness or LLMs. Output is always CLI/text, never charts or GUIs.

## Key Components & Data Flow
- **src/lichess_api.py**: Fetches and parses Lichess PGN data.
- **src/engine_analysis.py**: Runs Stockfish analysis, returns structured move data (move number, SAN, evals, phase, etc.).
- **src/performance_metrics.py**: Computes CPL (centipawn loss), aggregates by phase, calculates trends, blunder/mistake rates.
- **src/main.py**: Main entry; orchestrates fetching, analysis, and report output. Calls all major modules.
- **CSV files**: `games_{username}.csv` store raw game data; `{username}_analysis.txt` stores report output.

## Developer Workflows
- **Run analysis**: `python main.py` (or `.venv/bin/python main.py`)
- **Typical flow**: Enter username → fetch games → analyze → output saved to CSV and TXT files.
- **Testing**: Use real user CSVs (e.g., `games_ari.csv`) and compare output to expected metrics in `IMPROVEMENTS_COMPLETE.md`.
- **No build step**: Pure Python, no compilation.

## Project-Specific Conventions
- **Phases**: Opening (1–15), Middlegame (16–40), Endgame (41+), as defined in `performance_metrics.py`.
- **Blunder/mistake detection**: Engine-based, phase-tagged, normalized per 100 moves.
- **Trend reporting**: Only shown if enough games (≥6) and real comparison is possible.
- **Coach summary**: Always 6 elements, fully structured, see `main.py` and `IMPROVEMENTS_COMPLETE.md`.
- **No new dependencies**: Only `python-chess`, `requests`, `pandas`, and Stockfish binary (see below).

## Integration & Dependencies
- **Stockfish**: Expects binary at `/opt/homebrew/bin/stockfish` (macOS default). Update path if needed.
- **No external APIs except Lichess**: All data is local or from Lichess API.

## Examples & References
- See `IMPROVEMENTS_COMPLETE.md` and `REPORT_IMPROVEMENTS_SUMMARY.md` for sample outputs and verification cases.
- For implementation details, see `IMPLEMENTATION_SUMMARY.md` and `NEXT_STEPS.md`.

## Quick Start
1. Ensure Stockfish is installed and available at the expected path.
2. Run `python main.py` and follow prompts.
3. Output files will be created in the project root.

---
For any new features, follow the phase-based structure and deterministic, CLI-only output conventions. Reference existing report formats for consistency.
