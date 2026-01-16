# src/analytics/opening_deviation.py
"""Module 3: Opening Deviation + Evaluation Loss.

Detect where the player leaves known theory and quantify the cost.

Requirements:
- Use opening database (ECO or custom)
- Detect first deviation move
- Compute eval loss on deviation
- Aggregate by opening

The module does NOT call an LLM - all theory comparison is against
a pre-loaded opening database.
"""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

import pandas as pd

from .schemas import OpeningDeviationReport, OpeningDeviation

if TYPE_CHECKING:
    from typing import Any

# Load opening database
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
OPENING_DATA_PATH = os.path.join(BASE_DIR, "Chess_opening_data")

_OPENING_DB: pd.DataFrame | None = None
_OPENING_INDEX: dict[tuple[str, ...], tuple[str, str, str]] | None = None  # moves -> (opening, eco, full_line)


def _normalize_move_token(token: str) -> str:
    """Normalize move token to align dataset with SAN."""
    t = (token or "").strip()
    if not t:
        return ""
    if "." in t and t.split(".", 1)[0].isdigit():
        t = t.split(".", 1)[1].lstrip(".")
    t = t.rstrip("+#")
    if t in {"*", "1-0", "0-1", "1/2-1/2"}:
        return ""
    return t


def _load_opening_db() -> tuple[pd.DataFrame | None, dict[tuple[str, ...], tuple[str, str, str]]]:
    """Load opening database and build index."""
    global _OPENING_DB, _OPENING_INDEX

    if _OPENING_INDEX is not None:
        return _OPENING_DB, _OPENING_INDEX

    try:
        for sep in (None, "\t", ","):
            try:
                if sep is None:
                    df = pd.read_csv(OPENING_DATA_PATH, sep=None, engine="python", dtype=str)
                else:
                    df = pd.read_csv(OPENING_DATA_PATH, sep=sep, engine="python", dtype=str)
                break
            except Exception:
                df = pd.DataFrame()

        if df is None or df.empty:
            _OPENING_DB = None
            _OPENING_INDEX = {}
            return _OPENING_DB, _OPENING_INDEX

        _OPENING_DB = df
        _OPENING_INDEX = {}

        for _, row in df.iterrows():
            moves_str = str(row.get("Moves", "") or "").strip()
            if not moves_str:
                continue
            tokens = [_normalize_move_token(tok) for tok in moves_str.split()]
            tokens = [t for t in tokens if t]
            if not tokens:
                continue

            key = tuple(tokens)
            opening = str(row.get("Opening", "Unknown") or "Unknown")
            eco = str(row.get("ECO", "") or "")
            _OPENING_INDEX.setdefault(key, (opening, eco, moves_str))

        return _OPENING_DB, _OPENING_INDEX

    except Exception:
        _OPENING_DB = None
        _OPENING_INDEX = {}
        return _OPENING_DB, _OPENING_INDEX


def _find_longest_book_match(moves: list[str]) -> tuple[int, str, str, str]:
    """Find the longest prefix of moves that matches book theory.

    Returns:
        (book_depth, opening_name, eco, book_line)
    """
    _, idx = _load_opening_db()
    if not idx or not moves:
        return 0, "", "", ""

    norm = [_normalize_move_token(m) for m in moves]
    norm = [t for t in norm if t]
    if not norm:
        return 0, "", "", ""

    # Find longest match
    best_depth = 0
    best_match = ("", "", "")

    max_len = max((len(k) for k in idx.keys()), default=0)
    for k in range(min(len(norm), max_len), 0, -1):
        key = tuple(norm[:k])
        if key in idx:
            if k > best_depth:
                best_depth = k
                best_match = idx[key]
            break  # found longest match

    return best_depth, best_match[0], best_match[1], best_match[2]


def _ceil_int(x: float) -> int:
    return int(math.ceil(x))


def analyze_opening_deviations(games_data: list[dict[str, Any]]) -> OpeningDeviationReport:
    """Analyze opening deviations across games.

    Args:
        games_data: List of game dicts with move_evals and game_info.

    Returns:
        OpeningDeviationReport with deviation analysis.
    """
    result = OpeningDeviationReport()

    # Accumulators by opening
    opening_stats: dict[str, dict[str, Any]] = {}
    all_deviation_moves: list[int] = []
    all_deviation_losses: list[int] = []

    for game_idx, game in enumerate(games_data):
        move_evals = game.get("move_evals", []) or []
        game_info = game.get("game_info", {}) or {}
        player_color = (game_info.get("color") or "").lower()
        game_result = game_info.get("score")  # "win", "loss", "draw"

        # Collect SAN moves
        san_moves: list[str] = []
        eval_at_ply: dict[int, int] = {}  # ply -> eval

        for m in move_evals:
            san = m.get("san") or m.get("move_san") or ""
            if san:
                san_moves.append(san)
            # Store eval (White POV)
            ply = len(san_moves)
            ev = m.get("eval_after") or m.get("score_cp")
            if ev is not None:
                try:
                    eval_at_ply[ply] = int(ev)
                except Exception:
                    pass

        if not san_moves:
            continue

        # Find book depth
        book_depth, opening_name, eco, book_line = _find_longest_book_match(san_moves)

        if book_depth == 0:
            # No book match at all - skip or use header opening
            opening_name = game_info.get("opening_name") or "Unknown"
            eco = game_info.get("eco") or ""

        # Deviation is at book_depth + 1 (first move out of book)
        if book_depth < len(san_moves):
            deviation_ply = book_depth + 1
            deviation_move_num = (deviation_ply + 1) // 2  # fullmove number
            deviation_san = san_moves[book_depth] if book_depth < len(san_moves) else ""

            # Compute eval loss at deviation
            eval_before = eval_at_ply.get(book_depth, 0)
            eval_after = eval_at_ply.get(deviation_ply, 0)

            # Adjust for player color
            if player_color == "black":
                eval_before = -eval_before
                eval_after = -eval_after

            eval_loss = max(0, eval_before - eval_after)

            all_deviation_moves.append(deviation_move_num)
            all_deviation_losses.append(eval_loss)
            result.total_games_with_deviation += 1

            # Aggregate by opening
            key = opening_name or "Unknown"
            if key not in opening_stats:
                opening_stats[key] = {
                    "eco": eco,
                    "games": 0,
                    "deviation_moves": [],
                    "eval_losses": [],
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                    "common_deviations": {},
                    "examples": [],
                }

            opening_stats[key]["games"] += 1
            opening_stats[key]["deviation_moves"].append(deviation_move_num)
            opening_stats[key]["eval_losses"].append(eval_loss)
            
            # Store example (limit to first 3 per opening)
            if len(opening_stats[key]["examples"]) < 3:
                from .schemas import DeviationExample
                opening_stats[key]["examples"].append(DeviationExample(
                    game_index=game_idx + 1,  # 1-based indexing to match BlunderExample
                    deviation_ply=deviation_ply,
                    deviation_move=deviation_san,
                    eval_loss_cp=eval_loss,
                    color=player_color if player_color in ("white", "black") else "white",
                ))

            # Track common deviation moves
            if deviation_san:
                opening_stats[key]["common_deviations"][deviation_san] = \
                    opening_stats[key]["common_deviations"].get(deviation_san, 0) + 1

            # Results
            if game_result == "win":
                opening_stats[key]["wins"] += 1
            elif game_result == "draw":
                opening_stats[key]["draws"] += 1
            elif game_result == "loss":
                opening_stats[key]["losses"] += 1

    # Compute aggregates
    if all_deviation_moves:
        result.avg_deviation_move = sum(all_deviation_moves) / len(all_deviation_moves)
    if all_deviation_losses:
        result.avg_eval_loss_on_deviation = _ceil_int(sum(all_deviation_losses) / len(all_deviation_losses))

    # Build per-opening deviations
    deviations: list[OpeningDeviation] = []
    for opening, stats in opening_stats.items():
        games = stats["games"]
        if games == 0:
            continue

        avg_move = sum(stats["deviation_moves"]) / len(stats["deviation_moves"]) if stats["deviation_moves"] else 0
        avg_loss = _ceil_int(sum(stats["eval_losses"]) / len(stats["eval_losses"])) if stats["eval_losses"] else 0

        wins = stats["wins"]
        draws = stats["draws"]
        losses = stats["losses"]
        total = wins + draws + losses

        win_rate = _ceil_int((wins / total) * 100) if total > 0 else 0
        draw_rate = _ceil_int((draws / total) * 100) if total > 0 else 0
        loss_rate = _ceil_int((losses / total) * 100) if total > 0 else 0

        # Find most common deviation move
        common_dev = ""
        if stats["common_deviations"]:
            common_dev = max(stats["common_deviations"].items(), key=lambda x: x[1])[0]

        deviations.append(OpeningDeviation(
            opening=opening,
            eco=stats["eco"],
            games=games,
            common_deviation_move=common_dev,
            deviation_move_number=round(avg_move, 1),
            avg_eval_loss_cp=avg_loss,
            win_rate_pct=win_rate,
            draw_rate_pct=draw_rate,
            loss_rate_pct=loss_rate,
            examples=stats.get("examples", [])[:3],
        ))

    # Sort by games descending
    deviations.sort(key=lambda x: x.games, reverse=True)
    result.deviations_by_opening = deviations

    # Find most costly / most accurate opening
    if deviations:
        by_loss = sorted(deviations, key=lambda x: x.avg_eval_loss_cp, reverse=True)
        result.most_costly_opening = by_loss[0].opening
        result.most_accurate_opening = by_loss[-1].opening

    return result
