from __future__ import annotations

import os
import math
from dataclasses import dataclass
from io import StringIO
from typing import Any, List

import pandas as pd
import requests
import streamlit as st
import chess.pgn

from src.lichess_api import fetch_lichess_pgn
from src.analytics import generate_coaching_report, CoachingSummary

# Puzzle module imports
from puzzles import (
    Puzzle,
    PuzzleSession,
    generate_puzzles_from_games,
    get_puzzle_stats,
    render_puzzle_page,
    PuzzleUIState,
    Difficulty,
    PuzzleType,
)

# New JS-board puzzle UI (single real board)
from puzzles.puzzle_store import from_legacy_puzzles
from ui.puzzle_ui import render_puzzle_trainer

BASE_DIR = os.path.dirname(__file__)
OPENING_DATA_PATH = os.path.join(BASE_DIR, "src", "Chess_opening_data")


def _get_build_id() -> str:
    """Best-effort build identifier for debugging deployments."""
    for key in (
        "GITHUB_SHA",
        "STREAMLIT_GIT_COMMIT",
        "RENDER_GIT_COMMIT",
        "HEROKU_SLUG_COMMIT",
    ):
        v = (os.getenv(key) or "").strip()
        if v:
            return v[:7]

    # Try reading local .git metadata (available in many deployments)
    try:
        head_path = os.path.join(BASE_DIR, ".git", "HEAD")
        with open(head_path, "r", encoding="utf-8") as f:
            head = (f.read() or "").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_path = os.path.join(BASE_DIR, ".git", ref)
            with open(ref_path, "r", encoding="utf-8") as f:
                sha = (f.read() or "").strip()
            return sha[:7] if sha else "unknown"
        return head[:7] if head else "unknown"
    except Exception:
        return "unknown"


# Load opening data as DataFrame (tab-separated)
@st.cache_data(show_spinner=False)
def load_opening_db() -> pd.DataFrame:
    # The opening dataset may be TSV or CSV depending on source.
    # Prefer auto-detection; fall back to common separators.
    df: pd.DataFrame
    last_err: Exception | None = None
    for sep in (None, "\t", ","):
        try:
            if sep is None:
                df = pd.read_csv(OPENING_DATA_PATH, sep=None, engine="python", dtype=str)
            else:
                df = pd.read_csv(OPENING_DATA_PATH, sep=sep, engine="python", dtype=str)
            break
        except Exception as e:
            last_err = e
            df = pd.DataFrame()

    # If the file is missing/empty/unreadable, return an empty DB.
    if df is None or df.empty:
        _ = last_err  # keep for debugging if needed
        df = pd.DataFrame(columns=["Moves", "Opening", "ECO"])

    for col in ("Moves", "Opening", "ECO"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df


openings_db = load_opening_db()


def _normalize_move_token(token: str) -> str:
    """Normalize a token to align dataset 'Moves' with SAN from PGN.

    Dataset examples: '1.e4', '2.e5', '3...Nf6' (sometimes)
    PGN SAN examples: 'e4', 'Nf6', 'O-O', 'exd5'
    """
    t = (token or "").strip()
    if not t:
        return ""

    # Strip leading move numbers like '1.', '1...', '1.e4'
    # - '1.e4' -> 'e4'
    # - '1...'  -> ''
    t = t.lstrip()
    # Fast path for '1.e4'
    if "." in t and t.split(".", 1)[0].isdigit():
        t = t.split(".", 1)[1]
        t = t.lstrip(".")

    # Remove trailing check/mate markers for looser matching
    t = t.rstrip("+#")

    # Drop PGN result tokens
    if t in {"*", "1-0", "0-1", "1/2-1/2"}:
        return ""
    return t


@st.cache_data(show_spinner=False)
def _build_opening_index(df: pd.DataFrame) -> tuple[dict[tuple[str, ...], tuple[str, str]], int]:
    """Build a dict mapping move-sequence tuples -> (Opening, ECO)."""
    index: dict[tuple[str, ...], tuple[str, str]] = {}
    max_len = 0
    if df is None or df.empty:
        return index, 0

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

        # If duplicates exist, keep the first; longest-prefix match will pick by length anyway.
        index.setdefault(key, (opening, eco))
        if len(key) > max_len:
            max_len = len(key)

    return index, max_len


_OPENING_INDEX, _OPENING_MAXLEN = _build_opening_index(openings_db)


def recognize_opening(moves: list[str]) -> tuple[str, str]:
    """Return (Opening name, ECO) by longest prefix match on SAN moves."""
    if not moves or not _OPENING_INDEX:
        return ("Unknown", "")

    norm = [_normalize_move_token(m) for m in moves]
    norm = [t for t in norm if t]
    if not norm:
        return ("Unknown", "")

    max_k = min(len(norm), int(_OPENING_MAXLEN or 0))
    for k in range(max_k, 0, -1):
        hit = _OPENING_INDEX.get(tuple(norm[:k]))
        if hit:
            return hit
    return ("Unknown", "")

ANALYZE_ROUTE = "/analyze_game"  # Base URL only; do NOT include this path in secrets/env.

# CPL / phase stats tuning
MATE_CP_THRESHOLD = 10_000  # treat evals beyond this magnitude as mate-like / non-CPL
CPL_CP_LOSS_CAP = 2_000     # cap a single-move cp_loss contribution to avoid outliers


def _ceil_int(x: float | int) -> int:
    try:
        return int(math.ceil(float(x)))
    except Exception:
        return 0


def _pct(numer: float, denom: float) -> int:
    if denom <= 0:
        return 0
    return _ceil_int((numer / denom) * 100.0)


def _parse_rating(value: Any) -> int:
    """Coerce ratings from PGN headers/UI into sanitized ints."""
    try:
        rating = int(float(value))
        return rating if rating > 0 else 0
    except Exception:
        return 0


def _convert_to_analytics_format(
    aggregated_games: list[dict[str, Any]],
    focus_player: str | None = None,
) -> list[dict[str, Any]]:
    """Convert Streamlit aggregated games to analytics pipeline format.
    
    Analytics pipeline expects:
    {
        "game_info": {
            "opening_name": str,
            "eco": str,
            "color": "white"|"black",
            "score": "win"|"draw"|"loss",
            "player_rating": int,
        },
        "move_evals": [
            {
                "san": str,
                "cp_loss": int,
                "phase": str,
                "move_num": int,
                "eval_before": int|None,
                "eval_after": int|None,
                "fen_before": str|None,
            }
        ]
    }
    """
    analytics_games: list[dict[str, Any]] = []
    
    for game in aggregated_games:
        focus_color = game.get("focus_color")
        
        # Determine score from result and focus color
        result = game.get("result", "")
        score = "draw"
        if focus_color == "white":
            score = "win" if result == "1-0" else "loss" if result == "0-1" else "draw"
        elif focus_color == "black":
            score = "win" if result == "0-1" else "loss" if result == "1-0" else "draw"
        
        white_rating = _parse_rating(game.get("white_rating"))
        black_rating = _parse_rating(game.get("black_rating"))
        focus_rating = _parse_rating(game.get("focus_player_rating"))
        if focus_rating == 0:
            if focus_color == "white":
                focus_rating = white_rating
            elif focus_color == "black":
                focus_rating = black_rating

        game_info = {
            "opening_name": game.get("opening") or "Unknown",
            "eco": game.get("eco") or "",
            "color": focus_color or "white",
            "score": score,
            "player_rating": focus_rating,
            "white_rating": white_rating,
            "black_rating": black_rating,
        }
        
        # Convert moves_table to move_evals
        moves_table = game.get("moves_table", []) or []
        move_evals: list[dict[str, Any]] = []
        
        prev_score_cp: int | None = None
        for row in moves_table:
            mover = row.get("mover")
            
            # Only include moves from focus player
            if focus_color and mover != focus_color:
                prev_score_cp = row.get("score_cp")
                continue
            
            ply = int(row.get("ply") or 1)
            move_num = (ply + 1) // 2  # Convert ply to move number
            
            move_eval = {
                "san": row.get("move_san") or "",
                "cp_loss": int(row.get("cp_loss") or 0),
                "phase": row.get("phase") or "middlegame",
                "move_num": move_num,
                "eval_before": prev_score_cp,
                "eval_after": row.get("score_cp"),
            }
            move_evals.append(move_eval)
            prev_score_cp = row.get("score_cp")
        
        analytics_games.append({
            "game_info": game_info,
            "move_evals": move_evals,
        })
    
    return analytics_games


def _get_engine_endpoint() -> tuple[str, str]:
    """Resolve engine URL and API key (Streamlit secrets first, then env)."""
    try:
        url = st.secrets["VPS_ANALYSIS_URL"]
        api_key = st.secrets["VPS_API_KEY"]
        return url, api_key
    except Exception:
        url = os.getenv("VPS_ANALYSIS_URL") or ""
        api_key = os.getenv("VPS_API_KEY") or ""
        return url, api_key


@dataclass(frozen=True)
class GameInput:
    index: int
    pgn: str
    headers: dict[str, str]
    move_sans: list[str]
    fens_after_ply: list[str]
    num_plies: int


def _split_pgn_into_games(pgn_text: str, max_games: int) -> list[GameInput]:
    pgn_io = StringIO(pgn_text or "")
    games: list[GameInput] = []
    while len(games) < int(max_games):
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        headers = {k: str(v) for k, v in dict(game.headers).items() if v is not None}
        move_sans: list[str] = []
        fens_after_ply: list[str] = []
        board = game.board()
        for mv in game.mainline_moves():
            move_sans.append(board.san(mv))
            board.push(mv)
            fens_after_ply.append(board.fen())

        games.append(
            GameInput(
                index=len(games) + 1,
                pgn=str(game),
                headers=headers,
                move_sans=move_sans,
                fens_after_ply=fens_after_ply,
                num_plies=len(move_sans),
            )
        )
    return games


def _infer_focus_color(headers: dict[str, str], focus_player: str | None) -> str | None:
    if not focus_player:
        return None
    fp = focus_player.strip().lower()
    white = (headers.get("White") or "").strip().lower()
    black = (headers.get("Black") or "").strip().lower()
    if fp and white and fp == white:
        return "white"
    if fp and black and fp == black:
        return "black"
    return None


def _result_for_focus(headers: dict[str, str], focus_color: str | None) -> str | None:
    res = (headers.get("Result") or "").strip()
    if not res:
        return None
    if focus_color == "white":
        return "win" if res == "1-0" else "loss" if res == "0-1" else "draw" if res == "1/2-1/2" else None
    if focus_color == "black":
        return "win" if res == "0-1" else "loss" if res == "1-0" else "draw" if res == "1/2-1/2" else None
    return None


def _infer_focus_player_from_games(games: list[GameInput]) -> str | None:
    """Infer a likely focus player from a set of games.

    Used for uploaded PGNs where we don't have a username.
    Picks the most frequent player name across White/Black headers.
    """
    counts: dict[str, int] = {}
    canonical: dict[str, str] = {}
    for gi in games:
        for side in ("White", "Black"):
            name = (gi.headers.get(side) or "").strip()
            if not name:
                continue
            key = name.lower()
            canonical.setdefault(key, name)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    focus_key = max(counts.items(), key=lambda kv: kv[1])[0]
    return canonical.get(focus_key)


def _phase_for_ply(ply_index: int, total_plies: int) -> str:
    """Heuristic phase split by plies (half-moves).

    Opening: first 20 plies (~10 moves)
    Endgame: last 20 plies (~10 moves)
    Middlegame: everything in between
    """
    opening_end = min(20, total_plies)
    endgame_start = max(total_plies - 20, opening_end)
    if ply_index < opening_end:
        return "opening"
    if ply_index >= endgame_start:
        return "endgame"
    return "middlegame"


def _material_phase_ratio(board: chess.Board) -> float:
    """Return a [0,1] phase ratio based on remaining non-pawn material.

    This is a deterministic Stockfish-style idea: as queens/rooks/minors come off,
    the phase moves toward endgame.
    """
    weights = {
        chess.QUEEN: 4,
        chess.ROOK: 2,
        chess.BISHOP: 1,
        chess.KNIGHT: 1,
    }
    max_phase = 24.0  # 2 sides * (Q4 + R2*2 + B1*2 + N1*2) = 24

    phase = 0.0
    for piece_type, w in weights.items():
        phase += w * (
            len(board.pieces(piece_type, chess.WHITE))
            + len(board.pieces(piece_type, chess.BLACK))
        )
    return max(0.0, min(1.0, phase / max_phase))


def _classify_phase(ply_index: int, total_plies: int, board: chess.Board) -> str:
    """Classify phase using early-game guard + material/major-piece heuristics.

    Goals:
    - Opening is always early, regardless of trades.
    - Endgame starts earlier in games with heavy-piece exchanges (especially queen trades).
    - Otherwise, most of the game is middlegame.
    """
    # Guard: first ~8 full moves are opening for essentially all games.
    if ply_index < 16:
        return "opening"

    # If we're at the tail, bias to endgame.
    if total_plies > 0 and ply_index >= max(total_plies - 12, 16):
        return "endgame"

    phase_ratio = _material_phase_ratio(board)
    total_queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    total_rooks = len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.ROOK, chess.BLACK))
    total_minors = (
        len(board.pieces(chess.BISHOP, chess.WHITE))
        + len(board.pieces(chess.BISHOP, chess.BLACK))
        + len(board.pieces(chess.KNIGHT, chess.WHITE))
        + len(board.pieces(chess.KNIGHT, chess.BLACK))
    )

    # Endgame triggers: no queens, or very reduced heavy pieces, or low material phase.
    if total_queens == 0:
        return "endgame"
    if total_queens <= 1 and total_rooks <= 2:
        return "endgame"
    if phase_ratio <= 0.35:
        return "endgame"

    # Opening can extend slightly if basically no material has come off.
    if ply_index < 24 and phase_ratio >= 0.95 and total_minors >= 6:
        return "opening"

    return "middlegame"


def _compute_cp_loss_rows(
    analysis_rows: list[dict[str, Any]],
    focus_color: str | None,
    total_plies: int,
    fens_after_ply: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute per-ply cp_loss from successive score_cp values.

    score_cp is assumed to be White POV evaluation after the move.
    cp_loss is assigned to the side that just moved.
    """
    # score_cp is assumed to be White POV eval after the move.
    # Some engines encode mates as huge centipawn numbers. Exclude those from CPL.
    scores: list[int | None] = []
    for r in analysis_rows:
        try:
            v = int(r.get("score_cp") or 0)
            if abs(v) >= MATE_CP_THRESHOLD:
                scores.append(None)
            else:
                scores.append(v)
        except Exception:
            scores.append(None)

    out: list[dict[str, Any]] = []
    prev_score: int | None = None
    for i, r in enumerate(analysis_rows):
        curr = scores[i] if i < len(scores) else None
        mover = "white" if (i % 2 == 0) else "black"

        cp_loss = 0
        cpl_included = True

        # If either side of the delta is mate-like/unknown, exclude from CPL.
        if curr is None:
            cpl_included = False
        if prev_score is None:
            # First ply (or after excluded ply) has no delta.
            cp_loss = 0
        else:
            if not cpl_included:
                cp_loss = 0
            else:
                if mover == "white":
                    cp_loss = max(0, prev_score - curr)
                else:
                    cp_loss = max(0, curr - prev_score)
                # Cap extreme swings (including imminent mates) so averages stay meaningful.
                cp_loss = min(int(cp_loss), int(CPL_CP_LOSS_CAP))

        prev_score = curr
        if focus_color and mover != focus_color:
            cp_loss = 0
            cpl_included = False

        if fens_after_ply and i < len(fens_after_ply):
            try:
                board = chess.Board(fens_after_ply[i])
                phase = _classify_phase(i, total_plies, board)
            except Exception:
                phase = _phase_for_ply(i, total_plies)
        else:
            phase = _phase_for_ply(i, total_plies)
        out.append(
            {
                "ply": i + 1,
                "mover": mover,
                "move_san": r.get("move_san"),
                "score_cp": int(curr) if curr is not None else None,
                "cp_loss": cp_loss,
                "phase": phase,
                "cpl_included": bool(cpl_included),
            }
        )
    return out


def _aggregate_postprocessed_results(games: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-game move tables into phase stats, opening performance, trends, and coach summary."""
    all_move_rows: list[dict[str, Any]] = []
    focus_player_ratings: list[int] = []
    for g in games:
        focus_rating = _parse_rating(g.get("focus_player_rating"))
        if focus_rating > 0:
            focus_player_ratings.append(focus_rating)
        all_move_rows.extend(g.get("moves_table") or [])

    # Phase stats
    phase_stats: dict[str, dict[str, Any]] = {}
    for phase in ("opening", "middlegame", "endgame"):
        phase_rows = [r for r in all_move_rows if r.get("phase") == phase]
        cpl_vals = [
            int(r.get("cp_loss") or 0)
            for r in phase_rows
            if bool(r.get("cpl_included", True)) and int(r.get("cp_loss") or 0) > 0
        ]
        avg_cpl = (sum(cpl_vals) / len(cpl_vals)) if cpl_vals else 0.0
        mistakes = sum(1 for v in cpl_vals if v >= 100)
        blunders = sum(1 for v in cpl_vals if v >= 300)
        phase_stats[phase] = {
            "avg_cpl": float(avg_cpl),
            "moves": int(len(phase_rows)),
            "mistakes": int(mistakes),
            "blunders": int(blunders),
        }

    # Endgame CPL inflation vs non-endgame (opening+middlegame)
    end_avg = float(phase_stats.get("endgame", {}).get("avg_cpl", 0.0) or 0.0)
    non_rows = [r for r in all_move_rows if r.get("phase") in {"opening", "middlegame"}]
    non_vals = [
        int(r.get("cp_loss") or 0)
        for r in non_rows
        if bool(r.get("cpl_included", True)) and int(r.get("cp_loss") or 0) > 0
    ]
    non_avg = (sum(non_vals) / len(non_vals)) if non_vals else 0.0
    endgame_inflation_pct = 0.0
    if non_avg and end_avg:
        endgame_inflation_pct = max(0.0, ((end_avg / non_avg) - 1.0) * 100.0)

    # Optional comparison to a "normal" endgame inflation baseline (percent).
    # If not provided, UI will show N/A.
    try:
        normal_inflation_pct = float(os.getenv("NORMAL_ENDGAME_INFLATION_PCT") or 0.0)
    except Exception:
        normal_inflation_pct = 0.0
    endgame_vs_normal_pct = None
    if normal_inflation_pct > 0.0:
        endgame_vs_normal_pct = (endgame_inflation_pct / normal_inflation_pct) * 100.0

    # Weakest/strongest phases
    phase_by_cpl = sorted(((p, s.get("avg_cpl", 0.0)) for p, s in phase_stats.items()), key=lambda x: x[1], reverse=True)
    weakest_phase = phase_by_cpl[0][0] if phase_by_cpl else "opening"
    strongest_phase = phase_by_cpl[-1][0] if phase_by_cpl else "opening"

    # Win/draw/loss by opening (for focus player when possible)
    opening_counts: dict[str, dict[str, int]] = {}
    for g in games:
        opening = (g.get("opening") or g.get("eco") or "Unknown").strip() or "Unknown"
        opening_counts.setdefault(opening, {"win": 0, "draw": 0, "loss": 0, "games": 0})
        opening_counts[opening]["games"] += 1

        focus_color = g.get("focus_color")
        headers = {
            "White": g.get("white") or "",
            "Black": g.get("black") or "",
            "Result": g.get("result") or "",
        }
        outcome = _result_for_focus(headers, focus_color)
        if outcome in {"win", "draw", "loss"}:
            opening_counts[opening][outcome] += 1

    # Keep top openings by sample size
    opening_rates: list[dict[str, Any]] = []
    for opening, rec in sorted(opening_counts.items(), key=lambda kv: kv[1].get("games", 0), reverse=True)[:12]:
        opening_rates.append(
            {
                "opening": opening,
                "win": rec["win"],
                "draw": rec["draw"],
                "loss": rec["loss"],
            }
        )

    # CPL trend over games (avg cp_loss per game for focus player)
    cpl_trend: list[dict[str, Any]] = []
    for g in games:
        rows = g.get("moves_table") or []
        cpl_vals = [int(r.get("cp_loss") or 0) for r in rows if int(r.get("cp_loss") or 0) > 0]
        avg = (sum(cpl_vals) / len(cpl_vals)) if cpl_vals else 0.0
        cpl_trend.append({"game": f"Game {g.get('index')}", "avg_cpl": float(avg)})

    # Endgame success (games that reached endgame where outcome is win)
    endgame_games = 0
    endgame_wins = 0
    for g in games:
        rows = g.get("moves_table") or []
        if any(r.get("phase") == "endgame" for r in rows):
            endgame_games += 1
            headers = {
                "White": g.get("white") or "",
                "Black": g.get("black") or "",
                "Result": g.get("result") or "",
            }
            outcome = _result_for_focus(headers, g.get("focus_color"))
            if outcome == "win":
                endgame_wins += 1

    endgame_success = {
        "endgame_games": int(endgame_games),
        "endgame_wins": int(endgame_wins),
        "endgame_win_rate": (float(endgame_wins) / float(endgame_games)) if endgame_games else 0.0,
    }

    # Coach summary (deterministic, minimal)
    strengths: list[str] = []
    recommended: list[str] = []

    strengths.append(f"Strongest phase: {strongest_phase.title()}")
    recommended.append(f"Focus: {weakest_phase.title()} phase accuracy")

    if phase_stats.get(weakest_phase, {}).get("blunders", 0) > 0:
        recommended.append("Tactical review: reduce blunders (>=300cp swings)")
    if phase_stats.get(weakest_phase, {}).get("mistakes", 0) > 0:
        recommended.append("Conversion practice: reduce medium mistakes (>=100cp swings)")

    if endgame_success["endgame_games"] > 0:
        strengths.append(
            f"Endgames reached: {endgame_success['endgame_games']} (win rate {round(endgame_success['endgame_win_rate'] * 100, 1)}%)"
        )
    else:
        recommended.append("Endgame fundamentals: reach simplified positions confidently")

    coach_summary = {
        "primary_weakness": f"Weakest phase: {weakest_phase.title()}",
        "strengths": strengths[:4],
        "recommended_focus": recommended[:4],
    }

    avg_focus_rating = (
        _ceil_int(sum(focus_player_ratings) / len(focus_player_ratings)) if focus_player_ratings else 0
    )

    return {
        "success": True,
        "games_analyzed": len(games),
        "total_moves": int(len(all_move_rows)),
        "analysis": [],
        "games": games,
        "phase_stats": phase_stats,
        "endgame_inflation_pct": float(endgame_inflation_pct),
        "endgame_vs_normal_pct": (float(endgame_vs_normal_pct) if endgame_vs_normal_pct is not None else None),
        "opening_rates": opening_rates,
        "cpl_trend": cpl_trend,
        "endgame_success": endgame_success,
        "coach_summary": coach_summary,
        "focus_player_rating": avg_focus_rating,
    }


def _post_to_engine(pgn_text: str, max_games: int) -> dict:
    url, api_key = _get_engine_endpoint()
    if not url:
        raise RuntimeError("Engine endpoint not configured")

    # Normalize base URL: strip trailing slash and reject accidental paths.
    base = url.rstrip("/")
    # Prevent double /analyze_game in misconfigured secrets/env.
    if "/analyze_game" in base:
        base = base.split("/analyze_game")[0]
    endpoint = f"{base}{ANALYZE_ROUTE}"
    if endpoint.count("/analyze_game") != 1:
        raise RuntimeError(f"Invalid engine endpoint: {endpoint}")
    headers = {"x-api-key": api_key} if api_key else {}
    payload = {"pgn": pgn_text, "max_games": max_games}

    # Defensive payload validation (hard stop)
    if not isinstance(pgn_text, str) or not pgn_text.strip():
        st.error("Invalid PGN input: expected non-empty text")
        st.stop()
    if set(payload.keys()) != {"pgn", "max_games"}:
        st.error(f"Invalid payload keys: {sorted(payload.keys())}. Expected ['max_games', 'pgn']")
        st.stop()

    resp = requests.post(endpoint, json=payload, timeout=300, headers=headers)

    if resp.status_code == 403:
        raise RuntimeError("VPS Authentication Failed")
    if resp.status_code == 422:
        st.error("Engine rejected request (422 Validation Error)")
        st.info(
            "Backend contract mismatch: the server at this URL is not accepting JSON bodies. "
            "It is requiring multipart/form-data with a required 'file' field (confirmed by /openapi.json and by a direct JSON POST).\n\n"
            "To satisfy the project rule (PGN text only; keys ['pgn','max_games']), you must either:\n"
            "1) Point VPS_ANALYSIS_URL at the correct JSON-accepting backend, or\n"
            "2) Update the FastAPI backend /analyze_game endpoint to accept application/json with a body containing 'pgn' and 'max_games'."
        )
        try:
            st.json(resp.json())
        except Exception:
            st.write(resp.text)
        st.stop()
    if resp.status_code == 404:
        raise RuntimeError(f"Engine endpoint not found: {endpoint}. Check FastAPI route definition.")
    if not resp.ok:
        raise RuntimeError(f"Engine analysis failed (status {resp.status_code})")

    return resp.json()


def _validate_engine_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise RuntimeError("Invalid engine response: expected JSON object")
    if not data.get("success"):
        raise RuntimeError("Engine reported failure")
    analysis = data.get("analysis")
    if not analysis:
        raise RuntimeError("Engine returned no analysis")
    for entry in analysis:
        if "move_san" not in entry or "score_cp" not in entry:
            raise RuntimeError("Engine response missing move_san or score_cp")
    return data


def _render_results(data: dict) -> None:
    analysis = data.get("analysis", [])
    st.subheader("Analysis Result")
    st.metric("Total moves analyzed", len(analysis))
    table_rows = [{"move_san": row.get("move_san"), "score_cp": row.get("score_cp")}
                  for row in analysis]
    st.dataframe(table_rows)
    st.success("Analysis completed")


def _render_enhanced_ui(aggregated: dict[str, Any]) -> None:
    games: list[dict[str, Any]] = aggregated.get("games", []) or []
    all_rows: list[dict[str, Any]] = aggregated.get("analysis", []) or []

    st.subheader("Analysis")
    st.metric("Games analyzed", int(aggregated.get("games_analyzed") or len(games) or 0))
    st.metric("Total moves analyzed", int(aggregated.get("total_moves") or len(all_rows) or 0))

    # --- Per-game summary table ---
    if games:
        summary_df = pd.DataFrame(
            [
                {
                    "#": g.get("index"),
                    "Date": g.get("date"),
                    "White": g.get("white"),
                    "Black": g.get("black"),
                    "Result": g.get("result"),
                    "ECO": g.get("eco"),
                    "Opening": g.get("opening"),
                    "Moves": g.get("moves"),
                }
                for g in games
            ]
        )
        st.subheader("Games")
        st.dataframe(summary_df, width="stretch")

        for g in games:
            title = f"Game {g.get('index')}: {g.get('white')} vs {g.get('black')} ({g.get('result')})"
            with st.expander(title, expanded=False):
                st.write(
                    f"Opening: {g.get('opening') or 'Unknown'} "
                    f"{('(' + str(g.get('eco')) + ')') if g.get('eco') else ''}"
                )
                moves_df = pd.DataFrame(g.get("moves_table") or [])
                if not moves_df.empty:
                    st.dataframe(moves_df, width="stretch")
                    
                    # Add evaluation chart (line chart showing score_cp over ply)
                    if "score_cp" in moves_df.columns and "ply" in moves_df.columns:
                        st.write("**Evaluation over moves:**")
                        eval_df = moves_df[["ply", "score_cp"]].dropna()
                        if not eval_df.empty:
                            # Streamlit line_chart needs index as x-axis
                            eval_chart = eval_df.set_index("ply")[["score_cp"]]
                            st.line_chart(eval_chart)
                            st.caption("Positive = White advantage | Negative = Black advantage (centipawns)")
                else:
                    st.warning("No move rows to display for this game.")

    # --- Phase analysis ---
    phase_stats = aggregated.get("phase_stats") or {}
    if phase_stats:
        st.subheader("Phase Analysis")
        # Ensure consistent phase order
        phase_order = ["opening", "middlegame", "endgame"]
        phase_df = pd.DataFrame(
            [
                {
                    "Phase": p.title(),
                    "Avg CPL": _ceil_int(float(phase_stats.get(p, {}).get("avg_cpl") or 0.0)),
                    "Moves": int(phase_stats.get(p, {}).get("moves") or 0),
                    "Mistakes (>=100)": int(phase_stats.get(p, {}).get("mistakes") or 0),
                    "Blunders (>=300)": int(phase_stats.get(p, {}).get("blunders") or 0),
                }
                for p in phase_order if p in phase_stats
            ]
        )
        st.dataframe(phase_df, width="stretch")

        # Create separate bar charts for each metric (3 charts side by side)
        st.write("**Phase Performance Charts**")
        col1, col2, col3 = st.columns(3)
        
        chart_data = phase_df.set_index("Phase")
        
        with col1:
            st.write("📊 Avg CPL by Phase")
            cpl_chart = chart_data[["Avg CPL"]]
            st.bar_chart(cpl_chart)
        
        with col2:
            st.write("⚠️ Mistakes by Phase")
            mistakes_chart = chart_data[["Mistakes (>=100)"]]
            st.bar_chart(mistakes_chart)
        
        with col3:
            st.write("💥 Blunders by Phase")
            blunders_chart = chart_data[["Blunders (>=300)"]]
            st.bar_chart(blunders_chart)

        # Endgame bias metrics (percent)
        infl = float(aggregated.get("endgame_inflation_pct") or 0.0)
        vs_normal = aggregated.get("endgame_vs_normal_pct")
        st.caption(
            f"Endgame CPL inflation vs non-endgame baseline: {_ceil_int(infl)}%"
            + (f" | vs normal: {_ceil_int(float(vs_normal))}%" if vs_normal is not None else "")
        )

    # --- Win rates / opening performance ---
    opening_rates = aggregated.get("opening_rates") or []
    if opening_rates:
        st.subheader("Win/Draw/Loss by Opening")
        odf = pd.DataFrame(opening_rates)
        if not odf.empty:
            odf = odf.set_index("opening")[["win", "draw", "loss"]]
            st.bar_chart(odf)

    # --- CPL trend ---
    trend = aggregated.get("cpl_trend") or []
    if trend:
        st.subheader("CPL Trend")
        tdf = pd.DataFrame(trend)
        if not tdf.empty:
            # Round up for display
            tdf["avg_cpl"] = tdf["avg_cpl"].apply(_ceil_int)
            tdf = tdf.set_index("game")[["avg_cpl"]]
            st.line_chart(tdf)

    # --- Coach summary ---
    coach = aggregated.get("coach_summary") or {}
    if coach:
        st.subheader("Coach Summary")
        st.write(f"Primary weakness: {coach.get('primary_weakness')}")
        strengths = coach.get("strengths") or []
        focus = coach.get("recommended_focus") or []
        if strengths:
            st.write("Strengths:")
            for s in strengths:
                st.write(f"- {s}")
        if focus:
            st.write("Recommended training focus:")
            for f in focus:
                st.write(f"- {f}")

    # --- Advanced Coaching Insights (from analytics pipeline) ---
    if games:
        st.divider()
        try:
            # Convert to analytics format and generate coaching report
            focus_player = aggregated.get("focus_player") or ""
            analytics_games = _convert_to_analytics_format(games, focus_player)
            
            if analytics_games:
                focus_player_rating = _parse_rating(aggregated.get("focus_player_rating"))
                coaching_report = generate_coaching_report(
                    analytics_games,
                    username=focus_player,
                    player_rating=focus_player_rating,
                )
                _render_coaching_insights(coaching_report)
        except Exception as e:
            st.warning(f"Advanced coaching insights unavailable: {e}")


def _render_coaching_insights(coaching_report: CoachingSummary) -> None:
    """Render the advanced coaching insights section from analytics pipeline."""
    st.header("🎯 Advanced Coaching Insights")
    st.caption("Powered by deterministic analytics engine - no AI/LLM in analysis")
    
    # --- Playstyle Analysis (NEW) ---
    playstyle = coaching_report.playstyle
    if playstyle.primary_style:
        st.subheader("🎭 Your Playstyle")
        
        # Primary style with emoji
        style_emojis = {
            "Tactical": "⚔️",
            "Positional": "🏰",
            "Aggressive": "🔥",
            "Defensive": "🛡️",
        }
        primary_emoji = style_emojis.get(playstyle.primary_style, "♟️")
        secondary_emoji = style_emojis.get(playstyle.secondary_style, "♟️")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Primary Style",
                f"{primary_emoji} {playstyle.primary_style}",
                help=f"Confidence: {playstyle.style_confidence}%"
            )
        with col2:
            st.metric("Secondary Style", f"{secondary_emoji} {playstyle.secondary_style}")
        with col3:
            st.metric("Style Confidence", f"{playstyle.style_confidence}%")
        
        # Style scores as progress bars
        st.write("**Style Breakdown:**")
        style_cols = st.columns(4)
        with style_cols[0]:
            st.write(f"⚔️ Tactical: **{playstyle.tactical_score}**")
            st.progress(playstyle.tactical_score / 100)
        with style_cols[1]:
            st.write(f"🏰 Positional: **{playstyle.positional_score}**")
            st.progress(playstyle.positional_score / 100)
        with style_cols[2]:
            st.write(f"🔥 Aggressive: **{playstyle.aggressive_score}**")
            st.progress(playstyle.aggressive_score / 100)
        with style_cols[3]:
            st.write(f"🛡️ Defensive: **{playstyle.defensive_score}**")
            st.progress(playstyle.defensive_score / 100)
        
        # Style indicators
        if playstyle.style_indicators:
            st.write("**Key Indicators:**")
            for indicator in playstyle.style_indicators[:4]:
                st.caption(f"  • {indicator}")
    
    # --- Piece Performance (NEW) ---
    if playstyle.strongest_piece or playstyle.weakest_piece:
        st.subheader("♟️ Piece Performance")
        
        piece_emojis = {
            "Pawn": "♙",
            "Knight": "♘",
            "Bishop": "♗",
            "Rook": "♖",
            "Queen": "♕",
            "King": "♔",
        }
        
        col1, col2 = st.columns(2)
        with col1:
            if playstyle.strongest_piece:
                emoji = piece_emojis.get(playstyle.strongest_piece, "♟️")
                st.success(f"**💪 Strongest Piece: {emoji} {playstyle.strongest_piece}**")
                if playstyle.strongest_piece_reason:
                    st.caption(f"  {playstyle.strongest_piece_reason}")
        with col2:
            if playstyle.weakest_piece:
                emoji = piece_emojis.get(playstyle.weakest_piece, "♟️")
                st.warning(f"**📈 Needs Work: {emoji} {playstyle.weakest_piece}**")
                if playstyle.weakest_piece_reason:
                    st.caption(f"  {playstyle.weakest_piece_reason}")
        
        # Piece stats table
        piece_stats = playstyle.piece_stats
        if piece_stats:
            with st.expander("📊 Detailed Piece Statistics", expanded=False):
                piece_rows = []
                for name, ps in piece_stats.items():
                    if ps.moves > 0:
                        piece_rows.append({
                            "Piece": f"{piece_emojis.get(name, '')} {name}",
                            "Moves": ps.moves,
                            "Avg CPL": round(ps.avg_cpl, 1),
                            "Blunders": ps.blunders,
                            "Mistakes": ps.mistakes,
                            "Excellent": ps.excellent_moves,
                            "Captures": ps.captures,
                            "Checks": ps.checks,
                        })
                if piece_rows:
                    st.dataframe(pd.DataFrame(piece_rows), width="stretch", hide_index=True)
    
    st.divider()
    
    # --- Critical Issues & Strengths ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⚠️ Critical Issues")
        if coaching_report.critical_issues:
            for issue in coaching_report.critical_issues:
                st.error(f"• {issue}")
        else:
            st.success("No critical issues detected!")
    
    with col2:
        st.subheader("💪 Strengths")
        if coaching_report.strengths:
            for strength in coaching_report.strengths:
                st.success(f"• {strength}")
        else:
            st.info("Keep playing to identify your strengths!")
    
    # --- Blunder Classification ---
    st.subheader("🔍 Blunder Classification")
    blunder = coaching_report.blunder_analysis
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Blunders", blunder.total_blunders)
    with col2:
        st.metric("Total Mistakes", blunder.total_mistakes)
    with col3:
        st.metric("Blunders per 100 moves", f"{blunder.blunder_rate_per_100_moves:.1f}")
    
    # Blunder type breakdown
    by_type = blunder.by_type.to_dict()
    if by_type:
        st.write("**Blunder Types:**")
        type_df = pd.DataFrame([
            {"Type": k.replace("_", " ").title(), "Count": v}
            for k, v in by_type.items()
        ]).sort_values("Count", ascending=False)
        st.dataframe(type_df, width="stretch", hide_index=True)
        
        # Chart
        if len(type_df) > 1:
            chart_df = type_df.set_index("Type")
            st.bar_chart(chart_df)
    
    # Blunder by phase
    by_phase = blunder.by_phase
    if by_phase and sum(by_phase.values()) > 0:
        st.write("**Blunders by Phase:**")
        phase_df = pd.DataFrame([
            {"Phase": p.title(), "Blunders": c}
            for p, c in by_phase.items()
        ])
        st.dataframe(phase_df, width="stretch", hide_index=True)
    
    # Blunder examples
    if blunder.examples:
        with st.expander(f"📋 Blunder Examples ({len(blunder.examples)} shown)", expanded=False):
            for ex in blunder.examples[:5]:
                st.write(
                    f"**Game {ex.game_index}, Move {ex.move_number}:** `{ex.san}` "
                    f"({ex.blunder_type.replace('_', ' ')}) - {ex.cp_loss}cp loss [{ex.phase}]"
                )
    
    # --- Endgame Breakdown ---
    endgame = coaching_report.endgame_breakdown
    endgame_types = endgame.to_dict().get("endgame_types", {})
    if endgame_types:
        st.subheader("♟️ Endgame Analysis")
        
        col1, col2 = st.columns(2)
        with col1:
            if endgame.weakest_endgame_type:
                st.warning(f"Weakest: {endgame.weakest_endgame_type.replace('_', ' ').title()}")
        with col2:
            if endgame.strongest_endgame_type:
                st.success(f"Strongest: {endgame.strongest_endgame_type.replace('_', ' ').title()}")
        
        endgame_rows = []
        for etype, stats in endgame_types.items():
            if isinstance(stats, dict) and stats.get("games", 0) > 0:
                endgame_rows.append({
                    "Type": etype.replace("_", " ").title(),
                    "Games": stats.get("games", 0),
                    "Avg CPL": stats.get("avg_cpl", 0),
                    "Blunder Rate %": stats.get("blunder_rate_pct", 0),
                    "Conversion %": stats.get("conversion_rate_pct", 0),
                })
        if endgame_rows:
            st.dataframe(pd.DataFrame(endgame_rows), width="stretch", hide_index=True)
    
    # --- Opening Deviations ---
    opening_dev = coaching_report.opening_deviations
    if opening_dev.total_games_with_deviation > 0:
        st.subheader("📖 Opening Theory Deviations")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Games with Deviation", opening_dev.total_games_with_deviation)
        with col2:
            st.metric("Avg Deviation Move", f"{opening_dev.avg_deviation_move:.1f}")
        with col3:
            st.metric("Avg Eval Loss", f"{opening_dev.avg_eval_loss_on_deviation}cp")
        
        if opening_dev.deviations_by_opening:
            with st.expander("Opening Deviation Details", expanded=False):
                for dev in opening_dev.deviations_by_opening[:5]:
                    dev_dict = dev if isinstance(dev, dict) else dev.to_dict()
                    st.write(
                        f"**{dev_dict.get('opening', 'Unknown')}** ({dev_dict.get('eco', '')}): "
                        f"Deviation at move {dev_dict.get('deviation_move_number', '?')} "
                        f"({dev_dict.get('common_deviation_move', '?')}) - "
                        f"Avg loss: {dev_dict.get('avg_eval_loss_cp', 0)}cp"
                    )
    
    # --- Recurring Patterns ---
    patterns = coaching_report.recurring_patterns
    if patterns.patterns:
        st.subheader("🔄 Recurring Patterns")
        
        for pattern in patterns.patterns[:5]:
            severity_color = {
                "critical": "🔴",
                "moderate": "🟡",
                "minor": "🟢",
            }.get(pattern.severity, "⚪")
            st.write(f"{severity_color} **{pattern.pattern_type.replace('_', ' ').title()}**: {pattern.description}")
            st.caption(f"   Occurrences: {pattern.occurrences} | Games affected: {pattern.games_affected}")
    
    # --- Training Plan ---
    plan = coaching_report.training_plan
    if plan.primary_focus:
        st.subheader("📚 Weekly Training Plan")
        
        # Primary/Secondary focus with rationale
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**🎯 Primary Focus:** {plan.primary_focus}")
        with col2:
            if plan.secondary_focus:
                st.info(f"**📌 Secondary Focus:** {plan.secondary_focus}")
        
        if plan.rationale:
            st.caption(f"💡 *{plan.rationale}*")
        
        # Priority areas
        priority_col1, priority_col2 = st.columns(2)
        with priority_col1:
            if plan.priority_endgame_types:
                st.write("**♟️ Priority Endgame Types:**")
                for eg in plan.priority_endgame_types[:3]:
                    st.write(f"  • {eg}")
        with priority_col2:
            if plan.priority_tactical_themes:
                st.write("**⚔️ Priority Tactical Themes:**")
                for theme in plan.priority_tactical_themes[:3]:
                    st.write(f"  • {theme}")
        
        # Daily schedule
        if plan.daily_exercises:
            with st.expander("📅 Daily Exercise Schedule", expanded=True):
                for day in plan.daily_exercises:
                    day_dict = day if isinstance(day, dict) else day.to_dict()
                    day_name = day_dict.get('day', 'Day')
                    theme = day_dict.get('theme', 'Practice')
                    focus = day_dict.get('focus_area', '')
                    duration = day_dict.get('duration_minutes', 30)
                    
                    st.markdown(f"**{day_name}:** {theme} ({duration} min)")
                    exercises = day_dict.get("exercises", []) or day_dict.get("suggested_exercises", [])
                    if exercises:
                        for ex in exercises[:4]:
                            st.caption(f"   ✓ {ex}")
        
        # Recommended resources
        if plan.recommended_resources:
            with st.expander("📖 Recommended Resources", expanded=False):
                for resource in plan.recommended_resources[:8]:
                    st.write(f"• {resource}")
    
    # --- Peer Benchmark ---
    peer = coaching_report.peer_comparison
    if peer.rating_bracket:
        st.subheader("📊 Peer Comparison")
        
        # Show rating bracket prominently
        st.markdown(f"### 🏆 Rating Bracket: **{peer.rating_bracket}**")
        if peer.sample_size > 0:
            st.caption(f"Based on {peer.sample_size:,} players in this rating range")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            pct = peer.overall_cpl_percentile
            rank_str = f"Top {100 - pct}%" if pct > 0 else "N/A"
            st.metric("Overall CPL", rank_str, help="Your centipawn loss percentile vs peers")
        with col2:
            if peer.strongest_vs_peers:
                st.metric("💪 Strongest Phase", peer.strongest_vs_peers.title())
        with col3:
            if peer.weakest_vs_peers:
                st.metric("📈 Needs Work", peer.weakest_vs_peers.title())
        
        # Blunder rate comparison
        if peer.blunder_rate_percentile > 0 or peer.blunder_rate_vs_peers_pct != 0:
            st.write("**Blunder Rate vs Peers:**")
            br_pct = peer.blunder_rate_vs_peers_pct
            if br_pct > 0:
                st.warning(f"Your blunder rate is {br_pct}% higher than average for your rating bracket")
            elif br_pct < 0:
                st.success(f"Your blunder rate is {abs(br_pct)}% lower than average for your rating bracket!")
            else:
                st.info("Your blunder rate is average for your rating bracket")
        
        # Phase percentiles table
        phase_percentiles = []
        for phase in ["opening", "middlegame", "endgame"]:
            pct = getattr(peer, f"{phase}_cpl_percentile", 0)
            if pct > 0:
                rank = 100 - pct
                phase_percentiles.append({
                    "Phase": phase.title(),
                    "Percentile": pct,
                    "Rank vs Peers": f"Top {rank}%" if rank <= 50 else f"Bottom {100 - rank}%",
                    "Status": "✅ Strong" if rank <= 25 else "⚠️ Average" if rank <= 50 else "❌ Needs work",
                })
        if phase_percentiles:
            st.write("**Phase-by-Phase Performance:**")
            st.dataframe(pd.DataFrame(phase_percentiles), width="stretch", hide_index=True)
    
    # --- LLM-Ready JSON Export ---
    with st.expander("🤖 Export for AI Coach (JSON)", expanded=False):
        st.caption("This JSON can be fed to an LLM for personalized coaching explanations")
        st.code(coaching_report.to_json()[:5000] + "..." if len(coaching_report.to_json()) > 5000 else coaching_report.to_json(), language="json")


def main() -> None:
    st.title("Chess Analyzer (Remote Engine)")

    if "analysis_result" not in st.session_state:
        st.session_state["analysis_result"] = None
    if "analysis_request" not in st.session_state:
        st.session_state["analysis_request"] = None

    st.subheader("Inputs")
    if openings_db is None or openings_db.empty or not _OPENING_INDEX:
        st.warning(
            "Opening database is not loaded (or empty). "
            "Openings cannot be recognized until src/Chess_opening_data is a real non-empty TSV file in the repo."
        )
    else:
        st.caption(f"Opening database loaded: {len(openings_db)} rows")
    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"], horizontal=True)
    max_games = st.slider("Max games", min_value=1, max_value=200, value=10, step=1)

    pgn_text: str = ""  # single canonical analysis input
    focus_player: str | None = None

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        focus_player = username.strip() if username else None
        if st.button("Run analysis"):
            if not username:
                st.error("Please enter a username")
                return
            try:
                pgn_text = fetch_lichess_pgn(username, max_games=max_games)
            except Exception as e:
                st.error(str(e))
                st.stop()

            games_inputs = _split_pgn_into_games(pgn_text, max_games=max_games)
            num_games_in_pgn = max(pgn_text.count("[Event "), len(games_inputs))
            games_to_analyze = min(len(games_inputs), int(max_games))
            st.session_state["analysis_request"] = {
                "source": "lichess",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            progress = st.progress(0)
            status = st.empty()
            moves_counter = st.empty()

            aggregated_games: list[dict[str, Any]] = []
            aggregated_rows: list[dict[str, Any]] = []

            for i, gi in enumerate(games_inputs[:games_to_analyze], start=1):
                status.info(f"Analyzing {i} of {games_to_analyze} games...")
                try:
                    resp = _post_to_engine(gi.pgn, max_games=1)
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                rows = valid.get("analysis", []) or []
                # Build per-game rows table + phase stats
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(
                    rows,
                    focus_color=focus_color,
                    total_plies=gi.num_plies,
                    fens_after_ply=gi.fens_after_ply,
                )
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "phase"]].to_dict(
                    orient="records"
                )
                aggregated_rows.extend(rows)

                # Recognize opening by moves if not in PGN headers
                opening_name, eco_code = recognize_opening(gi.move_sans)
                white_rating = _parse_rating(gi.headers.get("WhiteElo"))
                black_rating = _parse_rating(gi.headers.get("BlackElo"))
                focus_player_rating = (
                    white_rating if focus_color == "white" else black_rating if focus_color == "black" else 0
                )
                aggregated_games.append(
                    {
                        "index": gi.index,
                        "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                        "white": gi.headers.get("White") or "",
                        "black": gi.headers.get("Black") or "",
                        "result": gi.headers.get("Result") or "",
                        "eco": gi.headers.get("ECO") or eco_code or "",
                        "opening": gi.headers.get("Opening") or opening_name or "",
                        "moves": int((gi.num_plies + 1) // 2),
                        "moves_table": moves_table,
                        "focus_color": focus_color,
                        "white_rating": white_rating,
                        "black_rating": black_rating,
                        "focus_player_rating": focus_player_rating,
                    }
                )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")

            status.success("Backend status: 200 OK")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            aggregated["focus_player"] = focus_player  # Pass through for analytics
            st.session_state["analysis_result"] = aggregated

    else:
        st.caption(f"Build: {_get_build_id()}")
        uploaded_files = st.file_uploader(
            "Upload PGN file(s)",
            type=["pgn"],
            accept_multiple_files=True,
            key="upload_pgn_files_v2",
            help="Select multiple files with Shift/Cmd-click in the file picker, or drag-and-drop several files at once.",
        )
        if uploaded_files:
            st.caption(
                "Selected: " + ", ".join(getattr(f, "name", "(unnamed)") for f in uploaded_files)
            )
        if st.button("Run analysis"):
            if not uploaded_files:
                st.error("Please upload at least one PGN file.")
                return

            combined_games: list[Any] = []
            total_events = 0

            for uploaded in uploaded_files:
                try:
                    pgn_text = uploaded.read().decode("utf-8", errors="ignore")
                except Exception as e:
                    st.error(f"Failed to read {uploaded.name}: {e}")
                    st.stop()

                total_events += pgn_text.count("[Event ")
                combined_games.extend(_split_pgn_into_games(pgn_text, max_games=max_games))

            if not combined_games:
                st.error("No games found in uploaded files.")
                return

            games_inputs = combined_games
            num_games_in_pgn = max(total_events, len(games_inputs))
            games_to_analyze = min(len(games_inputs), int(max_games))
            st.session_state["analysis_request"] = {
                "source": "upload",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            progress = st.progress(0)
            status = st.empty()
            moves_counter = st.empty()

            aggregated_games: list[dict[str, Any]] = []
            aggregated_rows: list[dict[str, Any]] = []

            # For uploads, infer the most likely focus player across games.
            focus_player = _infer_focus_player_from_games(games_inputs)

            for i, gi in enumerate(games_inputs[:games_to_analyze], start=1):
                status.info(f"Analyzing {i} of {games_to_analyze} games...")
                try:
                    resp = _post_to_engine(gi.pgn, max_games=1)
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                rows = valid.get("analysis", []) or []
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(
                    rows,
                    focus_color=focus_color,
                    total_plies=gi.num_plies,
                    fens_after_ply=gi.fens_after_ply,
                )
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "phase"]].to_dict(
                    orient="records"
                )
                aggregated_rows.extend(rows)

                # Recognize opening by moves if not in PGN headers
                opening_name, eco_code = recognize_opening(gi.move_sans)
                white_rating = _parse_rating(gi.headers.get("WhiteElo"))
                black_rating = _parse_rating(gi.headers.get("BlackElo"))
                focus_player_rating = (
                    white_rating if focus_color == "white" else black_rating if focus_color == "black" else 0
                )
                aggregated_games.append(
                    {
                        "index": gi.index,
                        "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                        "white": gi.headers.get("White") or "",
                        "black": gi.headers.get("Black") or "",
                        "result": gi.headers.get("Result") or "",
                        "eco": gi.headers.get("ECO") or eco_code or "",
                        "opening": gi.headers.get("Opening") or opening_name or "",
                        "moves": int((gi.num_plies + 1) // 2),
                        "moves_table": moves_table,
                        "focus_color": focus_color,
                        "white_rating": white_rating,
                        "black_rating": black_rating,
                        "focus_player_rating": focus_player_rating,
                    }
                )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")

            status.success("Backend status: 200 OK")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            aggregated["focus_player"] = focus_player  # Pass through for analytics
            st.session_state["analysis_result"] = aggregated

    req = st.session_state.get("analysis_request")
    if req:
        if req.get("num_games_in_pgn", 0) > 0:
            st.info(
                f"Analyzing {req.get('games_to_analyze')} of {req.get('num_games_in_pgn')} games "
                f"(limited by max_games={req.get('max_games')})."
            )
        else:
            st.warning(
                "Could not count games in PGN (no '[Event ' headers found). "
                "This usually means the PGN is a single game or is missing headers."
            )

    # Show results with tabs if we have analysis
    if st.session_state.get("analysis_result"):
        _render_tabbed_results(st.session_state["analysis_result"])


def _render_tabbed_results(aggregated: dict[str, Any]) -> None:
    """Render analysis results with a stable selector including Puzzles.

    Streamlit tabs reset to the first tab on rerun. Since puzzle moves cause reruns,
    we keep the user's selection stable via session_state.
    """
    
    # CSS to make the puzzle tab larger and more prominent
    st.markdown("""
    <style>
    /* Make tabs larger and more visible */
    div[data-baseweb="tab-list"] {
        gap: 8px;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"] {
        font-size: 1.2rem;
        padding: 12px 24px;
        font-weight: 600;
    }
    /* Highlight the puzzle tab specifically */
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(2) {
        background-color: rgba(127, 166, 80, 0.15);
        border-radius: 8px 8px 0 0;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(2):hover {
        background-color: rgba(127, 166, 80, 0.25);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Stable view selector (survives reruns)
    if "main_view" not in st.session_state:
        st.session_state["main_view"] = "📊 Analysis"

    view = st.radio(
        "Main view",
        options=["📊 Analysis", "♟️ Puzzles"],
        horizontal=True,
        key="main_view",
        label_visibility="collapsed",
    )

    if view == "♟️ Puzzles":
        _render_puzzle_tab(aggregated)
    else:
        _render_enhanced_ui(aggregated)


def _render_puzzle_tab(aggregated: dict[str, Any]) -> None:
    """Render the puzzle training tab."""
    st.header("♟️ Chess Puzzles")
    st.caption("Practice tactical patterns from your analyzed games • No AI - purely engine-derived")
    st.caption(f"Build: {_get_build_id()}")
    
    games = aggregated.get("games", [])
    
    if not games:
        st.info("No games analyzed yet. Run an analysis to generate puzzles!")
        return
    
    # Generate puzzles from analyzed games
    if "generated_puzzles" not in st.session_state:
        with st.spinner("Generating puzzles from your games..."):
            puzzles = generate_puzzles_from_games(
                analyzed_games=games,
                min_eval_loss=100,  # Minimum 100cp loss to be a puzzle
            )
            st.session_state["generated_puzzles"] = puzzles
    else:
        puzzles = st.session_state["generated_puzzles"]
    
    if not puzzles:
        st.warning(
            "No puzzles generated from your games. "
            "Puzzles are created when you make mistakes (≥100cp loss). "
            "Try analyzing more games or games with more tactical complexity."
        )
        return
    
    # Puzzle stats overview
    stats = get_puzzle_stats(puzzles)
    
    st.subheader("📈 Puzzle Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Puzzles", stats["total"])
    with col2:
        by_diff = stats.get("by_difficulty", {})
        easy = by_diff.get("easy", 0)
        st.metric("🟢 Easy", easy)
    with col3:
        medium = by_diff.get("medium", 0)
        st.metric("🟡 Medium", medium)
    with col4:
        hard = by_diff.get("hard", 0)
        st.metric("🔴 Hard", hard)
    
    # Puzzle type breakdown
    st.write("**Puzzle Types:**")
    by_type = stats.get("by_type", {})
    type_cols = st.columns(3)
    with type_cols[0]:
        st.write(f"⚔️ Missed Tactics: **{by_type.get('missed_tactic', 0)}**")
    with type_cols[1]:
        st.write(f"♟️ Endgame Technique: **{by_type.get('endgame_technique', 0)}**")
    with type_cols[2]:
        st.write(f"📖 Opening Errors: **{by_type.get('opening_error', 0)}**")
    
    st.divider()
    
    # Filtering options
    st.subheader("🎯 Filter Puzzles")
    
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    
    with filter_col1:
        difficulty_filter = st.selectbox(
            "Difficulty",
            options=["All", "Easy", "Medium", "Hard"],
            key="puzzle_difficulty_filter",
        )
    
    with filter_col2:
        type_filter = st.selectbox(
            "Type",
            options=["All", "Missed Tactic", "Endgame Technique", "Opening Error"],
            key="puzzle_type_filter",
        )
    
    with filter_col3:
        phase_filter = st.selectbox(
            "Phase",
            options=["All", "Opening", "Middlegame", "Endgame"],
            key="puzzle_phase_filter",
        )
    
    # Apply filters
    filtered_puzzles = _filter_puzzles(
        puzzles,
        difficulty_filter,
        type_filter,
        phase_filter,
    )
    
    if not filtered_puzzles:
        st.warning("No puzzles match your filters. Try different options.")
        return
    
    st.caption(f"Showing {len(filtered_puzzles)} of {len(puzzles)} puzzles")
    
    st.divider()
    
    # Premium status (for demo, always False - implement real check)
    IS_PREMIUM = False
    
    # Render puzzle interface (single JS board with drag/click)
    game_players = {
        int(g.get("index") or 0): (str(g.get("white") or ""), str(g.get("black") or ""))
        for g in games
        if int(g.get("index") or 0) > 0
    }
    puzzle_defs = from_legacy_puzzles(filtered_puzzles, game_players=game_players)
    render_puzzle_trainer(puzzle_defs)


def _filter_puzzles(
    puzzles: List[Puzzle],
    difficulty: str,
    puzzle_type: str,
    phase: str,
) -> List[Puzzle]:
    """Apply filters to puzzle list."""
    result = puzzles
    
    # Difficulty filter
    if difficulty != "All":
        diff_map = {
            "Easy": Difficulty.EASY,
            "Medium": Difficulty.MEDIUM,
            "Hard": Difficulty.HARD,
        }
        target_diff = diff_map.get(difficulty)
        if target_diff:
            result = [p for p in result if p.difficulty == target_diff]
    
    # Type filter
    if puzzle_type != "All":
        type_map = {
            "Missed Tactic": PuzzleType.MISSED_TACTIC,
            "Endgame Technique": PuzzleType.ENDGAME_TECHNIQUE,
            "Opening Error": PuzzleType.OPENING_ERROR,
        }
        target_type = type_map.get(puzzle_type)
        if target_type:
            result = [p for p in result if p.puzzle_type == target_type]
    
    # Phase filter
    if phase != "All":
        target_phase = phase.lower()
        result = [p for p in result if p.phase == target_phase]
    
    return result


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

