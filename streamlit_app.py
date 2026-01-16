from __future__ import annotations

import os
import math
import time
import hashlib
from dataclasses import dataclass
from io import StringIO
from typing import Any, List

import pandas as pd
import requests
import streamlit as st
import chess.pgn


def _hydrate_env_from_streamlit_secrets() -> None:
    """Copy selected Streamlit secrets into env vars.

    Streamlit Community Cloud stores secrets in st.secrets, not necessarily as
    process env vars. Our puzzle bank backend reads env vars so it can be used
    from non-Streamlit modules.
    """
    try:
        secrets = st.secrets
    except Exception:
        return

    for k in ("PUZZLE_BANK_BACKEND", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        try:
            if not os.getenv(k) and secrets.get(k):
                os.environ[k] = str(secrets.get(k))
        except Exception:
            continue


_hydrate_env_from_streamlit_secrets()

from src.lichess_api import fetch_lichess_pgn
from src.analytics import generate_coaching_report, CoachingSummary

# Game cache for avoiding re-analysis
from src.game_cache import (
    get_cached_games_for_user,
    cache_game,
    get_cache_stats,
    clear_cache,
    _extract_game_id,
    _hash_pgn,
)

# Time analysis for clock-based patterns
from src.time_analysis import (
    has_clock_data,
    aggregate_time_analysis,
)

# New feature imports
from src.database import get_db
from src.game_replayer import render_game_replayer
from src.quick_wins import (
    add_export_button,
    add_dark_mode_toggle,
    add_keyboard_shortcuts,
    create_shareable_link,
    detect_time_trouble,
    render_time_trouble_analysis,
)
from src.opening_repertoire import render_opening_repertoire_ui
from src.opponent_strength import render_opponent_strength_analysis
from src.streak_detection import (
    detect_current_streaks,
    render_streak_badges,
    get_streak_milestones,
)

# AI Coach imports
from src.ai_coach_ui import render_ai_coach_tab, render_tier_selector_sidebar

# Auth imports
from src.auth import render_auth_sidebar, get_current_user, is_logged_in, require_auth

# Saved analyses (for logged-in users)
from src.saved_analyses import save_analysis, render_load_analysis_ui

# Translations
from src.translations import t, render_language_selector

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

# Cross-user shared puzzle bank + ratings
from puzzles.global_puzzle_store import load_global_puzzles, save_puzzles_to_global_bank

# Play vs Engine tab
from src.play_vs_engine import render_play_vs_engine_tab

# Pricing page
from src.pricing_ui import render_pricing_page
from src.legal_ui import (
    render_terms_of_service_page,
    render_privacy_policy_page,
    render_refund_policy_page,
)

# Puzzle disk cache
from puzzles.puzzle_cache import load_cached_puzzles, save_cached_puzzles

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
    move_clocks: tuple  # Per-move clock data (tuple for hashability)
    has_clock_data: bool


def _extract_clock_from_comment(comment: str) -> int | None:
    """Extract clock time in seconds from PGN comment like [%clk 0:05:30]."""
    import re
    # Try H:MM:SS format
    match = re.search(r'\[%clk\s+(\d+):(\d+):(\d+)\]', comment)
    if match:
        hours, mins, secs = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return hours * 3600 + mins * 60 + secs
    # Try M:SS format
    match = re.search(r'\[%clk\s+(\d+):(\d+)\]', comment)
    if match:
        mins, secs = int(match.group(1)), int(match.group(2))
        return mins * 60 + secs
    return None


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
        move_clocks: list[dict] = []
        board = game.board()
        
        # Traverse game tree to get moves with comments
        node = game
        ply = 0
        while node.variations:
            next_node = node.variation(0)
            move = next_node.move
            san = board.san(move)
            move_sans.append(san)
            
            # Extract clock from comment
            clock_seconds = _extract_clock_from_comment(next_node.comment or "")
            
            ply += 1
            move_number = (ply + 1) // 2
            mover_color = "white" if board.turn == chess.WHITE else "black"
            
            move_clocks.append({
                'move_number': move_number,
                'ply': ply,
                'color': mover_color,
                'san': san,
                'clock_seconds': clock_seconds,
            })
            
            board.push(move)
            fens_after_ply.append(board.fen())
            node = next_node
        
        has_clock = any(m['clock_seconds'] is not None for m in move_clocks)

        games.append(
            GameInput(
                index=len(games) + 1,
                pgn=str(game),
                headers=headers,
                move_sans=move_sans,
                fens_after_ply=fens_after_ply,
                num_plies=len(move_sans),
                move_clocks=tuple(move_clocks),  # Convert to tuple for hashability
                has_clock_data=has_clock,
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
        
        # Store actual cp_loss for display purposes (before filtering by focus_color)
        actual_cp_loss = cp_loss
        
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
                "actual_cp_loss": actual_cp_loss,  # For display in move list
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


def _post_to_engine(pgn_text: str, max_games: int, *, depth: int = 15, retries: int = 2) -> dict:
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

    # Pass depth as a query parameter (keeps JSON payload contract unchanged).
    try:
        depth_val = int(depth)
    except Exception:
        depth_val = 15
    depth_val = max(10, min(20, depth_val))
    endpoint = f"{endpoint}?depth={depth_val}"
    headers = {"x-api-key": api_key} if api_key else {}
    payload = {"pgn": pgn_text, "max_games": max_games}

    # Defensive payload validation (hard stop)
    if not isinstance(pgn_text, str) or not pgn_text.strip():
        st.error("Invalid PGN input: expected non-empty text")
        st.stop()
    if set(payload.keys()) != {"pgn", "max_games"}:
        st.error(f"Invalid payload keys: {sorted(payload.keys())}. Expected ['max_games', 'pgn']")
        st.stop()

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(endpoint, json=payload, timeout=300, headers=headers)
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise

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
            raise RuntimeError(
                f"Engine endpoint not found: {endpoint}. Check FastAPI route definition."
            )
        if not resp.ok:
            # Retry transient server errors.
            if resp.status_code in {500, 502, 503, 504} and attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            body_preview = (resp.text or "").strip().replace("\n", " ")
            if len(body_preview) > 500:
                body_preview = body_preview[:500] + "…"
            raise RuntimeError(
                f"Engine analysis failed (status {resp.status_code}). "
                + (f"Response: {body_preview}" if body_preview else "")
            )

        return resp.json()

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Engine analysis failed")


def _validate_engine_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise RuntimeError("Invalid engine response: expected JSON object")
    if not data.get("success"):
        detail = (
            data.get("error")
            or data.get("message")
            or data.get("detail")
            or data.get("reason")
            or "(no error detail provided by engine)"
        )
        raise RuntimeError(f"Engine reported failure: {detail}")
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
    focus_player = aggregated.get("focus_player", "").strip()

    # Add export to sidebar
    with st.sidebar:
        if focus_player:
            add_export_button(aggregated, focus_player)
            share_link = create_shareable_link(aggregated, focus_player)
            if share_link:
                st.markdown(f"**Share this analysis:**")
                st.code(share_link, language="text")
        
        # Cache management
        with st.expander("📦 Cache Settings", expanded=False):
            stats = get_cache_stats()
            if "error" not in stats:
                st.caption(f"**Games cached:** {stats.get('total_games', 0)}")
                st.caption(f"**Users:** {stats.get('unique_users', 0)}")
                st.caption(f"**Size:** {stats.get('cache_size_mb', 0)} MB")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🗑️ Clear my cache", help="Clear cached games for current user"):
                        if focus_player:
                            cleared = clear_cache(focus_player)
                            st.success(f"Cleared {cleared} games")
                            st.rerun()
                        else:
                            st.warning("No user to clear")
                with col2:
                    if st.button("🗑️ Clear all", help="Clear entire cache"):
                        cleared = clear_cache()
                        st.success(f"Cleared {cleared} games")
                        st.rerun()
            else:
                st.caption("Cache not available")

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
    
    # Get games from session state for time trouble analysis
    games = []
    if st.session_state.get("analysis_result"):
        games = st.session_state["analysis_result"].get("games", [])
    
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
            for idx, ex in enumerate(blunder.examples[:5]):
                col1, col2 = st.columns([5, 1])
                with col1:
                    # Add color indicator emoji
                    color_indicator = "⬜" if ex.color == "white" else "⬛"
                    st.write(
                        f"{color_indicator} **Game {ex.game_index}, Move {ex.move_number}:** `{ex.san}` "
                        f"({ex.blunder_type.replace('_', ' ')}) - {ex.cp_loss}cp loss [{ex.phase}]"
                    )
                with col2:
                    if st.button("🎮 Show", key=f"show_blunder_{idx}", help="Jump to this move in game replayer"):
                        # Set session state to jump to this game and move
                        st.session_state['main_view'] = f"🎮 {t('tab_replayer')}"
                        st.session_state['replayer_game_select'] = ex.game_index - 1  # game_index is 1-based
                        # Calculate ply from move number and color
                        # Ply = half-moves from starting position (0 = start, 1 = white's first move, 2 = black's first move, etc.)
                        # For white moves: ply = (move_number - 1) * 2 + 1
                        # For black moves: ply = move_number * 2
                        if ex.color == "white":
                            st.session_state['replay_ply'] = (ex.move_number - 1) * 2 + 1
                        else:
                            st.session_state['replay_ply'] = ex.move_number * 2
                        st.rerun()
    
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
                    
                    # Show examples with navigation buttons
                    examples = dev_dict.get('examples', [])
                    if examples:
                        cols = st.columns(len(examples))
                        for idx, example in enumerate(examples):
                            with cols[idx]:
                                color_indicator = "⬜" if example.get('color') == 'white' else "⬛"
                                if st.button(
                                    f"{color_indicator} Show",
                                    key=f"dev_{dev_dict.get('opening')}_{idx}",
                                    help=f"Move {example.get('deviation_move')} ({example.get('eval_loss_cp')}cp loss)"
                                ):
                                    game_idx = example.get('game_index', 1) - 1  # Convert from 1-based to 0-based
                                    deviation_ply = example.get('deviation_ply', 1)
                                    st.session_state['main_view'] = f"🎮 {t('tab_replayer')}"
                                    st.session_state['replayer_game_select'] = game_idx
                                    st.session_state['replay_ply'] = deviation_ply
                                    st.rerun()
    
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
    
    # --- Time Management Analysis (uses Lichess clock data) ---
    st.divider()
    st.subheader("⏱️ Time Management Analysis")
    
    # Check if games have clock data
    if has_clock_data(games):
        time_stats = aggregate_time_analysis(games)
        
        if time_stats.get('has_data'):
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Games Analyzed", time_stats['games_analyzed'])
            with col2:
                st.metric(
                    "Time Trouble Rate", 
                    f"{time_stats['time_trouble_rate']:.0f}%",
                    help="% of games where you entered time trouble"
                )
            with col3:
                st.metric(
                    "Time Management Score",
                    f"{time_stats['avg_time_management_score']}/100",
                    help="Overall time management quality"
                )
            with col4:
                tt_games = time_stats['time_trouble_games']
                st.metric("Games in Time Trouble", tt_games)
            
            # Average time per phase
            st.write("**⏰ Average Time per Move by Phase:**")
            avg_phase = time_stats.get('avg_phase_times', {})
            phase_cols = st.columns(3)
            with phase_cols[0]:
                st.metric("Opening", f"{avg_phase.get('opening', 0):.1f}s")
            with phase_cols[1]:
                st.metric("Middlegame", f"{avg_phase.get('middlegame', 0):.1f}s")
            with phase_cols[2]:
                st.metric("Endgame", f"{avg_phase.get('endgame', 0):.1f}s")
            
            # Patterns detected
            patterns = time_stats.get('patterns', [])
            if patterns:
                st.write("**🔄 Time Management Patterns:**")
                for pattern in patterns:
                    severity = pattern.get('severity', 'medium')
                    if severity == 'high':
                        st.error(f"🔴 **{pattern['description']}** — {pattern['recommendation']}")
                    elif severity == 'positive':
                        st.success(f"✅ **{pattern['description']}** — {pattern['recommendation']}")
                    else:
                        st.warning(f"🟡 **{pattern['description']}** — {pattern['recommendation']}")
                    st.caption(f"   Affected: {pattern['stat']}")
            else:
                st.info("No significant time management patterns detected.")
            
            # Detailed per-game breakdown (collapsible)
            with st.expander("📊 Per-Game Time Analysis", expanded=False):
                per_game = time_stats.get('per_game_analysis', [])
                if per_game:
                    game_rows = []
                    for i, ga in enumerate(per_game):
                        ts = ga.get('time_score', {})
                        tt = ga.get('time_trouble', {})
                        game_rows.append({
                            "#": i + 1,
                            "Date": ga.get('date', ''),
                            "Result": ga.get('result', '').title(),
                            "Time Control": ga.get('time_control', ''),
                            "Time Score": f"{ts.get('score', 0)}/100",
                            "Grade": ts.get('grade', 'N/A'),
                            "Time Trouble Moves": tt.get('time_trouble_moves_count', 0),
                        })
                    st.dataframe(pd.DataFrame(game_rows), width="stretch", hide_index=True)
        else:
            st.info(f"ℹ️ {time_stats.get('message', 'No clock data available.')}")
    else:
        st.error(
            "⏰ **No time data available - Time management analysis disabled**\n\n"
            "This feature analyzes your time usage patterns to identify time trouble and improve time management.\n\n"
            "**If you downloaded games from Chess.com:**\n"
            "Make sure the **\"Timestamps per move\"** option is enabled when exporting games. "
            "Without this option, move timestamps are not included in the PGN file.\n\n"
            "**For Lichess games:**\n"
            "Clock data is automatically included in the PGN export."
        )
        
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


def _render_analysis_input_form() -> None:
    """Render the analysis input form (username/upload) and handle execution."""
    st.subheader(t("inputs"))
    
    # Load previous analysis option (for signed-in users)
    if is_logged_in():
        with st.expander(f"📂 {t('load_previous_analysis')}", expanded=False):
            loaded = render_load_analysis_ui()
            if loaded:
                # Restore the analysis result from saved data
                st.session_state["analysis_result"] = loaded.get("analysis_data")
                st.session_state["analysis_request"] = {
                    "source": loaded.get("source", "lichess"),
                    "max_games": loaded.get("num_games", 0),
                    "loaded_from_save": True,
                    "loaded_username": loaded.get("username", ""),
                }
                st.rerun()
    
    if openings_db is None or openings_db.empty or not _OPENING_INDEX:
        st.warning(
            "Opening database is not loaded (or empty). "
            "Openings cannot be recognized until src/Chess_opening_data is a real non-empty TSV file in the repo."
        )
    else:
        st.caption(f"Opening database loaded: {len(openings_db)} rows")
    source = st.radio(t("source"), [t("lichess_username"), t("chess_com_pgn")], horizontal=True)
    max_games = st.slider(t("max_games"), min_value=1, max_value=200, value=10, step=1)

    analysis_depth = st.slider(
        t("engine_depth"),
        min_value=10,
        max_value=20,
        value=15,
        step=1,
        help="Higher depth is slower but more accurate. Recommended: 15.",
    )

    pgn_text: str = ""  # single canonical analysis input
    focus_player: str | None = None

    if source == t("lichess_username"):
        username = st.text_input(t("lichess_username"))
        focus_player = username.strip() if username else None
        if st.button(t("run_analysis")):
            if not username:
                st.error(t("please_enter_username"))
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
            cache_info = st.empty()

            aggregated_games: list[dict[str, Any]] = []
            aggregated_rows: list[dict[str, Any]] = []

            # Check cache for already-analyzed games
            cached_games = get_cached_games_for_user(username, int(analysis_depth))
            cache_hits = 0
            cache_misses = 0

            for i, gi in enumerate(games_inputs[:games_to_analyze], start=1):
                game_id = _extract_game_id(gi.headers)
                pgn_hash = _hash_pgn(gi.pgn)
                
                # Check if this game is already cached
                if game_id and game_id in cached_games:
                    cached = cached_games[game_id]
                    # Verify it's the same game (PGN hash check would be here)
                    status.info(f"Game {i} of {games_to_analyze}: ✅ Using cached analysis")
                    cache_hits += 1
                    
                    # Reconstruct game data from cache
                    focus_color = _infer_focus_color(gi.headers, focus_player)
                    game_data = {
                        "index": gi.index,
                        "date": cached.get("date") or gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                        "white": cached.get("white") or gi.headers.get("White") or "",
                        "black": cached.get("black") or gi.headers.get("Black") or "",
                        "result": cached.get("result") or gi.headers.get("Result") or "",
                        "eco": cached.get("eco") or gi.headers.get("ECO") or "",
                        "opening": cached.get("opening") or gi.headers.get("Opening") or "",
                        "moves": int((gi.num_plies + 1) // 2),
                        "moves_table": cached.get("moves_table", []),
                        "focus_color": focus_color,
                        "white_rating": cached.get("white_rating"),
                        "black_rating": cached.get("black_rating"),
                        "focus_player_rating": cached.get("focus_player_rating"),
                        "_cached": True,
                        # Clock data from current PGN (not cached, re-extract each time)
                        "time_control": gi.headers.get("TimeControl") or "",
                        "move_clocks": list(gi.move_clocks),
                        "has_clock_data": gi.has_clock_data,
                        "color": focus_color,
                    }
                    aggregated_games.append(game_data)
                    aggregated_rows.extend(cached.get("raw_analysis", []))
                    
                    progress.progress(int((i / games_to_analyze) * 100))
                    cache_info.caption(f"📦 Cache: {cache_hits} hits, {cache_misses} new")
                    continue
                
                # Not in cache - analyze with engine
                cache_misses += 1
                status.info(f"Analyzing {i} of {games_to_analyze} games... (new)")
                try:
                    resp = _post_to_engine(gi.pgn, max_games=1, depth=int(analysis_depth))
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    if "failed_games" not in st.session_state:
                        st.session_state["failed_games"] = []
                    st.session_state["failed_games"].append(
                        {
                            "run_source": "lichess",
                            "i": i,
                            "game_index": gi.index,
                            "white": gi.headers.get("White") or "",
                            "black": gi.headers.get("Black") or "",
                            "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                            "error": str(e),
                        }
                    )
                    status.warning(f"Skipping game {i} due to engine error. Continuing...")
                    progress.progress(int((i / games_to_analyze) * 100))
                    continue

                rows = valid.get("analysis", []) or []
                # Build per-game rows table + phase stats
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(
                    rows,
                    focus_color=focus_color,
                    total_plies=gi.num_plies,
                    fens_after_ply=gi.fens_after_ply,
                )
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "actual_cp_loss", "phase"]].to_dict(
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
                game_data = {
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
                    "time_control": gi.headers.get("TimeControl") or "",
                    "move_clocks": list(gi.move_clocks),  # Per-move clock data
                    "has_clock_data": gi.has_clock_data,
                    "color": focus_color,  # Alias for time analysis compatibility
                }
                aggregated_games.append(game_data)
                
                # Cache this newly analyzed game
                if game_id:
                    cache_game(
                        game_id=game_id,
                        username=username,
                        analysis_depth=int(analysis_depth),
                        pgn_hash=pgn_hash,
                        game_data=game_data,
                        raw_analysis=rows,
                    )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")
                cache_info.caption(f"📦 Cache: {cache_hits} hits, {cache_misses} new")

            # Show final cache stats
            if cache_hits > 0:
                status.success(f"✅ Done! Used {cache_hits} cached games, analyzed {cache_misses} new games.")
            else:
                status.success("Backend status: 200 OK")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            aggregated["focus_player"] = focus_player  # Pass through for analytics
            st.session_state["analysis_result"] = aggregated

            # Auto-save for signed-in users
            if is_logged_in():
                user = get_current_user()
                if user and user.get("id"):
                    success, msg = save_analysis(
                        user_id=user["id"],
                        username=username,
                        source="lichess",
                        num_games=games_to_analyze,
                        analysis_depth=int(analysis_depth),
                        analysis_data=aggregated,
                    )
                    if success:
                        st.toast(msg, icon="💾")
                    else:
                        st.warning(f"⚠️ Could not save analysis: {msg}")

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
                    resp = _post_to_engine(gi.pgn, max_games=1, depth=int(analysis_depth))
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    if "failed_games" not in st.session_state:
                        st.session_state["failed_games"] = []
                    st.session_state["failed_games"].append(
                        {
                            "run_source": "upload",
                            "i": i,
                            "game_index": gi.index,
                            "white": gi.headers.get("White") or "",
                            "black": gi.headers.get("Black") or "",
                            "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                            "error": str(e),
                        }
                    )
                    status.warning(f"Skipping game {i} due to engine error. Continuing...")
                    progress.progress(int((i / games_to_analyze) * 100))
                    continue

                rows = valid.get("analysis", []) or []
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(
                    rows,
                    focus_color=focus_color,
                    total_plies=gi.num_plies,
                    fens_after_ply=gi.fens_after_ply,
                )
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "actual_cp_loss", "phase"]].to_dict(
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
                        "time_control": gi.headers.get("TimeControl") or "",
                        "move_clocks": list(gi.move_clocks),
                        "has_clock_data": gi.has_clock_data,
                        "color": focus_color,
                    }
                )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")

            status.success("Backend status: 200 OK")

            failed = st.session_state.get("failed_games") or []
            if failed:
                st.warning(f"Skipped {len(failed)} game(s) due to engine errors.")
                st.dataframe(failed, width="stretch")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            aggregated["focus_player"] = focus_player  # Pass through for analytics
            st.session_state["analysis_result"] = aggregated

            # Auto-save for signed-in users (Chess.com PGN)
            if is_logged_in() and focus_player:
                user = get_current_user()
                if user and user.get("id"):
                    success, msg = save_analysis(
                        user_id=user["id"],
                        username=focus_player,
                        source="chess.com",
                        num_games=games_to_analyze,
                        analysis_depth=int(analysis_depth),
                        analysis_data=aggregated,
                    )
                    if success:
                        st.toast(msg, icon="💾")
                    else:
                        st.warning(f"⚠️ Could not save analysis: {msg}")

    # Success message after running
    if st.session_state.get("analysis_result"):
        st.success("Analysis complete! View the results in the tabs.")
        st.rerun()


def main() -> None:
    st.title(t("app_title"))

    # Render language selector and authentication sidebar
    render_language_selector()
    render_auth_sidebar()
    st.sidebar.caption(f"{t('contact_us')}: orvarsv@icloud.com")
    
    st.sidebar.markdown("---")
    
    # Legal buttons
    if st.sidebar.button("📜 Terms of Service", use_container_width=True):
        st.session_state["main_view"] = "Terms of Service"
        st.rerun()

    col_legal_1, col_legal_2 = st.sidebar.columns(2)
    with col_legal_1:
        if st.button("🔒 Privacy", use_container_width=True):
            st.session_state["main_view"] = "Privacy Policy"
            st.rerun()
    with col_legal_2:
        if st.button("💸 Refund", use_container_width=True):
            st.session_state["main_view"] = "Refund Policy"
            st.rerun()

    if "analysis_result" not in st.session_state:
        st.session_state["analysis_result"] = {} # Initialize empty dict
    if "analysis_request" not in st.session_state:
        st.session_state["analysis_request"] = None

    # Always render the tabbed main view
    # Pass results if available, otherwise empty dict
    _render_tabbed_results(st.session_state["analysis_result"] or {})




def _render_pinned_navigation(view_options: list[str]) -> str:
    """Render pinned navigation as two rows of buttons."""
    
    # Custom CSS for navigation buttons to ensure text fitting
    st.markdown("""
        <style>
        div[data-testid="column"] button {
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding: 0.4rem 0.1rem !important;
            font-size: 0.85rem !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Label mapping for cleaner display
    label_map = {
        "Analysis": "Analysis",
        "AI Coach": "AI Coach",
        "Replayer": "Replayer",
        "Openings": "Openings",
        "Opponent Analysis": "Opponent",
        "Streaks": "Streaks",
        "Puzzles": "Puzzles",
        "Play vs Engine": "Vs Engine",
        "Pricing": "Pricing",
    }

    # Split into two rows (5 items top, 4 items bottom)
    row1 = view_options[:5]
    row2 = view_options[5:]

    # Row 1
    cols1 = st.columns(5, gap="small")
    for i, (col, option) in enumerate(zip(cols1, row1)):
        with col:
            _render_nav_button_logic(option, label_map, i)

    # Row 2
    cols2 = st.columns(4, gap="small")
    for i, (col, option) in enumerate(zip(cols2, row2)):
        with col:
            _render_nav_button_logic(option, label_map, i + 5)
            
    st.markdown("---")
    return st.session_state.get("main_view", view_options[0])


def _render_nav_button_logic(option: str, label_map: dict, key_idx: int) -> None:
    """Helper to render a single navigation button."""
    is_selected = st.session_state.get("main_view") == option
    parts = option.split(" ", 1)
    emoji = parts[0] if parts else "📌"
    original_label = parts[1] if len(parts) > 1 else option
    
    display_label = label_map.get(original_label, original_label)
    
    button_type = "primary" if is_selected else "secondary"
    if st.button(
        f"{emoji} {display_label}",
        key=f"nav_pin_{key_idx}",
        use_container_width=True,
        type=button_type,
    ):
        st.session_state["main_view"] = option
        st.rerun()


def _render_tabbed_results(aggregated: dict[str, Any]) -> None:
    """Render analysis results with pinned navigation bar.

    Navigation is always visible at the top of the content area.
    """
    
    # Build translated view options
    view_options = [
        f"📊 {t('tab_analysis')}",
        f"🤖 {t('tab_ai_coach')}",
        f"🎮 {t('tab_replayer')}",
        f"📚 {t('tab_openings')}",
        f"⚔️ Opponent Analysis",
        f"🏆 Streaks",
        f"♟️ {t('tab_puzzles')}",
        f"🤺 Play vs Engine",
        f"💎 Pricing",
    ]
    
    # Stable view selector (survives reruns)
    if "main_view" not in st.session_state:
        st.session_state["main_view"] = view_options[0]
    
    # Handle language change - reset view if current selection invalid, but allow Legal pages
    legal_pages = {"Terms of Service", "Privacy Policy", "Refund Policy"}
    if st.session_state.get("main_view") not in view_options and st.session_state.get("main_view") not in legal_pages:
        st.session_state["main_view"] = view_options[0]

    # Pinned navigation bar at top
    view = _render_pinned_navigation(view_options)

    # Check if we have analysis data
    has_analysis = bool(aggregated and aggregated.get("games"))
    
    # Render selected view
    if t('tab_puzzles') in view:
        if not has_analysis:
            st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to generate puzzles.")
        else:
            _render_puzzle_tab(aggregated)
    elif t('tab_ai_coach') in view:
        if not has_analysis:
            st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to use the AI Coach.")
        else:
            # Gate AI Coach behind login
            if not is_logged_in():
                st.warning(f"🔒 **{t('sign_in')}** required to access the AI Coach.")
                st.info("Use the sidebar to sign in with your email.")
            else:
                render_ai_coach_tab(aggregated)
    elif t('tab_replayer') in view:
        if not has_analysis:
            st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to use the Replayer.")
        else:
            _render_game_replayer_tab(aggregated)
    elif t('tab_openings') in view:
        if not has_analysis:
            st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to see your Opening Repertoire.")
        else:
            _render_opening_repertoire_tab(aggregated)
    elif "Opponent" in view:
        if not has_analysis:
             st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to see Opponent Analysis.")
        else:
            _render_opponent_analysis_tab(aggregated)
    elif "Streak" in view:
        if not has_analysis:
            st.info(f"ℹ️ Please analyze games in the **{t('tab_analysis')}** tab to see your Streaks.")
        else:
            _render_streaks_tab(aggregated)
    elif "Play vs Engine" in view:
        render_play_vs_engine_tab()
    elif "Pricing" in view:
        render_pricing_page()
    elif view == "Terms of Service":
        render_terms_of_service_page()
    elif view == "Privacy Policy":
        render_privacy_policy_page()
    elif view == "Refund Policy":
        render_refund_policy_page()
    else:
        # Default view (Analysis)
        if not has_analysis:
            _render_analysis_input_form()
        else:
            # Show option to start new analysis
            if st.button("⬅️ New Analysis", type="secondary"):
                st.session_state["analysis_result"] = {}
                st.rerun()
            _render_enhanced_ui(aggregated)


def _render_puzzle_tab(aggregated: dict[str, Any]) -> None:
    """Render the puzzle training tab."""
    st.header("♟️ Chess Puzzles")
    st.caption("Practice tactical patterns from your analyzed games • No AI - purely engine-derived")
    st.caption(f"Build: {_get_build_id()}")
    
    games = aggregated.get("games", [])
    focus_player = (aggregated.get("focus_player") or "").strip()
    # Used by the puzzle trainer UI for rating attribution.
    # Prefer logged-in user ID if available
    user = get_current_user()
    if user and user.get("id"):
        st.session_state["puzzle_rater"] = user.get("id")
    else:
        st.session_state["puzzle_rater"] = focus_player
    
    if not games:
        st.info("No games analyzed yet. Run an analysis to generate puzzles!")
        return

    def _games_signature(gs: list[dict[str, Any]]) -> str:
        """Create a stable-ish signature for the current analyzed game set.

        Used to invalidate cached puzzles when the user analyzes a different
        file/user/session.
        """
        h = hashlib.sha1()
        h.update(str(len(gs)).encode("utf-8"))
        # Sample a prefix to keep it cheap; enough to detect different imports.
        for g in (gs[:25] if isinstance(gs, list) else []):
            if not isinstance(g, dict):
                continue
            for k in ("game_id", "id", "url", "site", "created_at", "date", "white", "black", "result"):
                v = g.get(k)
                if v is None:
                    continue
                h.update(str(v).encode("utf-8"))
                h.update(b"|")
            moves = g.get("moves") or g.get("moves_san") or g.get("pgn_moves")
            if isinstance(moves, list):
                moves = " ".join(str(m) for m in moves[:12])
            if isinstance(moves, str):
                h.update(moves[:120].encode("utf-8"))
                h.update(b"|")
        return h.hexdigest()[:12]

    games_sig = _games_signature(games)
    prev_sig = st.session_state.get("generated_puzzles_sig")
    if prev_sig != games_sig:
        # New analysis input -> regenerate puzzles + reset puzzle UI caches.
        st.session_state["generated_puzzles_sig"] = games_sig
        st.session_state.pop("generated_puzzles", None)
        st.session_state.pop("puzzle_progress_v2", None)
        st.session_state.pop("puzzle_solution_line_cache_v1", None)

    source_mode = st.radio(
        "Puzzle source",
        options=["My games", "Other users"],
        horizontal=True,
        key="puzzle_source_mode",
    )

    # Reset puzzle UI state when switching source to avoid leaking progress/ratings
    prev_mode = st.session_state.get("puzzle_source_mode_prev")
    if prev_mode != source_mode:
        st.session_state.pop("puzzle_progress_v2", None)
        st.session_state.pop("puzzle_solution_line_cache_v2", None)
        st.session_state.pop("puzzle_solution_line_futures_v1", None)
        st.session_state.pop("puzzle_solution_line_executor_v1", None)
        st.session_state.pop("puzzle_rated_keys", None)
        st.session_state.pop("puzzle_last_rating", None)
        st.session_state.pop("puzzle_index", None)
    st.session_state["puzzle_source_mode_prev"] = source_mode
    
    if source_mode == "My games":
        # Generate puzzles from analyzed games
        if "generated_puzzles" not in st.session_state:
            # Try loading from disk cache first
            # Set PUZZLE_CACHE_MAX_AGE_HOURS=0 to make this cache never expire.
            try:
                cache_max_age_hours = int(os.getenv("PUZZLE_CACHE_MAX_AGE_HOURS", "24"))
            except Exception:
                cache_max_age_hours = 24
            cached_puzzles = load_cached_puzzles(games, max_age_hours=cache_max_age_hours)
            
            if cached_puzzles:
                st.session_state["generated_puzzles"] = cached_puzzles
                st.success(f"✓ Loaded {len(cached_puzzles)} puzzles from cache")
            else:
                # Generate fresh puzzles with progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(completed, total):
                    progress = int((completed / total) * 100)
                    progress_bar.progress(progress)
                    status_text.text(f"Analyzing batch {completed}/{total}...")
                
                status_text.text("Generating puzzles from your games...")
                
                puzzles = generate_puzzles_from_games(
                    analyzed_games=games,
                    min_eval_loss=100,
                    max_puzzles=200,
                    engine_depth=12,  # Increased for better puzzle quality validation
                    progress_callback=update_progress,
                )
                
                progress_bar.progress(100)
                status_text.text("✓ Puzzle generation complete!")
                
                # Save to cache for next time
                save_cached_puzzles(games, puzzles)
                
                st.session_state["generated_puzzles"] = puzzles
                
                # Clear progress indicators after a moment
                time.sleep(0.5)
                progress_bar.empty()
                status_text.empty()
        else:
            puzzles = st.session_state["generated_puzzles"]
    else:
        puzzles = load_global_puzzles(exclude_source_user=focus_player)

    if len(games) > 120 and len(puzzles) >= 200:
        st.caption("Note: showing up to 200 puzzles for performance.")
    
    if not puzzles:
        if source_mode == "My games":
            st.warning(
                "No puzzles generated from your games. "
                "Puzzles are created when you make mistakes (≥100cp loss). "
                "Try analyzing more games or games with more tactical complexity."
            )
        else:
            st.info(
                "No shared puzzles yet. Generate puzzles from your games first "
                "(or wait for other users to generate puzzles)."
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

    # Save user's generated puzzles into the global bank (deduped).
    # Avoid repeating the same save on every rerun.
    if source_mode == "My games":
        save_sig_key = "saved_global_puzzles_sig"
        # Determine source_user: prefer logged-in user ID, fallback to focus_player
        user = get_current_user()
        source_user = user.get("id") if user else focus_player
        # Only persist to the shared global bank when we have a known user
        # to attribute the puzzles. Avoid saving anonymous puzzles.
        if source_user and st.session_state.get(save_sig_key) != games_sig:
            try:
                save_puzzles_to_global_bank(puzzles, source_user=source_user, game_players=game_players)
                st.session_state[save_sig_key] = games_sig
            except Exception:
                pass

    # When viewing other users' puzzles, avoid mapping missing origin names
    # to the current user's `game_players` (which causes incorrect attribution).
    gp_for_ui = game_players if source_mode == "My games" else None
    puzzle_defs = from_legacy_puzzles(filtered_puzzles, game_players=gp_for_ui)
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


def _render_game_replayer_tab(aggregated: dict[str, Any]) -> None:
    """Render the interactive game replayer tab."""
    st.header("🎮 Game Replayer")
    st.caption("Step through your games move by move with evaluation analysis")
    
    games = aggregated.get("games", [])
    if not games:
        st.info("No games analyzed yet. Run an analysis first!")
        return
    
    # Game selector
    game_options = [
        f"Game {i+1}: {g.get('white', 'Unknown')} vs {g.get('black', 'Unknown')} ({g.get('date', 'Unknown')})"
        for i, g in enumerate(games)
    ]
    
    selected_game_idx = st.selectbox(
        "Select a game to replay",
        options=range(len(games)),
        format_func=lambda i: game_options[i],
        key="replayer_game_select",
    )
    
    if selected_game_idx is not None:
        game_data = games[selected_game_idx]
        moves_table = game_data.get("moves_table", [])
        
        if not moves_table:
            st.warning("No move data available for this game.")
            return
        
        # Reconstruct moves_pgn from moves_table if not present
        if 'moves_pgn' not in game_data or not game_data['moves_pgn']:
            # Extract SAN moves from moves_table
            san_moves = []
            for move in moves_table:
                move_san = move.get('move_san', '')
                if move_san:
                    san_moves.append(move_san)
            game_data['moves_pgn'] = ' '.join(san_moves)
        
        # Render the interactive replayer
        render_game_replayer(game_data, moves_table)


def _render_opening_repertoire_tab(aggregated: dict[str, Any]) -> None:
    """Render the opening repertoire analysis tab."""
    st.header("📚 Opening Repertoire")
    st.caption("Track your opening performance and identify gaps in your repertoire")
    
    focus_player = aggregated.get("focus_player", "").strip()
    if not focus_player:
        st.warning("No focus player identified. Please analyze games from a specific player.")
        return
    
    games = aggregated.get("games", [])
    if not games:
        st.info("No games analyzed yet. Run an analysis first!")
        return
    
    # Add export button
    add_export_button(aggregated, focus_player)
    
    # Analyze openings from the games we have
    st.subheader("📖 Opening Repertoire")
    st.caption("**Avg Pos** shows your average evaluation after the opening phase (moves 13-17). Positive = better position for you.")
    
    # Color filter
    color_filter = st.radio("Color", ["Both", "White", "Black"], horizontal=True)
    
    # Group games by opening
    opening_stats = {}
    for game in games:
        opening = game.get('opening', 'Unknown')
        eco = game.get('eco', '')
        focus_color = game.get('focus_color', 'white')
        result = game.get('result', '')
        
        # Apply color filter
        if color_filter == "White" and focus_color != "white":
            continue
        if color_filter == "Black" and focus_color != "black":
            continue
        
        # Determine outcome
        if focus_color == 'white':
            outcome = 'win' if result == '1-0' else 'loss' if result == '0-1' else 'draw'
        else:
            outcome = 'win' if result == '0-1' else 'loss' if result == '1-0' else 'draw'
        
        # Initialize stats for this opening
        if opening not in opening_stats:
            opening_stats[opening] = {
                'eco': eco,
                'games': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'opening_exit_evals': [],  # Track eval at end of opening
            }
        
        opening_stats[opening]['games'] += 1
        if outcome == 'win':
            opening_stats[opening]['wins'] += 1
        elif outcome == 'draw':
            opening_stats[opening]['draws'] += 1
        else:
            opening_stats[opening]['losses'] += 1
        
        # Extract evaluation at the end of opening phase (moves 13-17)
        moves_table = game.get('moves_table', [])
        if moves_table:
            for move in moves_table:
                move_num = move.get('move_num') or ((move.get('ply', 0) + 1) // 2)
                phase = move.get('phase', '')
                eval_after = move.get('eval_after') or move.get('score_cp')
                
                # Find the last opening move or first middlegame move
                if 13 <= move_num <= 17 and eval_after is not None:
                    try:
                        eval_val = int(eval_after)
                        # Normalize to player's perspective (positive = good for player)
                        if focus_color == 'black':
                            eval_val = -eval_val
                        opening_stats[opening]['opening_exit_evals'].append(eval_val)
                        break  # Take the first eval in this range
                    except (ValueError, TypeError):
                        pass
    
    if not opening_stats:
        st.info("No opening data yet. Play some games and analyze them to build your repertoire!")
        return
    
    # Display opening statistics
    opening_rows = []
    for opening, stats in opening_stats.items():
        total = stats['games']
        win_rate = (stats['wins'] / total * 100) if total > 0 else 0
        
        # Calculate average position after opening
        exit_evals = stats.get('opening_exit_evals', [])
        avg_exit_eval = sum(exit_evals) / len(exit_evals) if exit_evals else None
        
        row = {
            'Opening': f"{opening} ({stats['eco']})" if stats['eco'] else opening,
            'Games': total,
            'Win Rate': f"{win_rate:.1f}%",
            'W-D-L': f"{stats['wins']}-{stats['draws']}-{stats['losses']}",
        }
        
        # Add position quality column if we have data
        if avg_exit_eval is not None:
            row['Avg Pos'] = f"{avg_exit_eval:+.0f}cp"
        else:
            row['Avg Pos'] = "N/A"
        
        opening_rows.append(row)
    
    # Sort by games played
    opening_rows = sorted(opening_rows, key=lambda x: x['Games'], reverse=True)
    
    st.dataframe(opening_rows, use_container_width=True, hide_index=True)
    
    # Recommendations
    st.subheader("💡 Recommendations")
    weak_openings = [r for r in opening_rows if float(r['Win Rate'].rstrip('%')) < 40 and r['Games'] >= 3]
    if weak_openings:
        st.warning(f"**Weak openings to study:** {', '.join([r['Opening'].split(' (')[0] for r in weak_openings[:3]])}")
    
    rare_openings = [r for r in opening_rows if r['Games'] < 3]
    if rare_openings:
        st.info(f"**Build more experience in:** {len(rare_openings)} openings played fewer than 3 times")


def _render_opponent_analysis_tab(aggregated: dict[str, Any]) -> None:
    """Render the opponent strength analysis tab."""
    st.header("⚔️ Opponent Strength Analysis")
    st.caption("See how you perform against different rating levels")
    
    games = aggregated.get("games", [])
    if not games:
        st.info("No games analyzed yet. Run an analysis first!")
        return
    
    focus_player = aggregated.get("focus_player", "").strip()
    
    # Extract rating data from games
    games_with_ratings = []
    total_player_rating = 0
    rating_count = 0
    
    for game in games:
        focus_color = game.get('focus_color', 'white')
        white_rating = game.get('white_elo', 0) or game.get('white_rating', 0)
        black_rating = game.get('black_elo', 0) or game.get('black_rating', 0)
        
        if white_rating > 0 and black_rating > 0:
            player_rating = white_rating if focus_color == 'white' else black_rating
            opponent_rating = black_rating if focus_color == 'white' else white_rating
            
            total_player_rating += player_rating
            rating_count += 1
            
            # Determine score from result
            if focus_color == 'white':
                score = 'win' if game.get('result') == '1-0' else 'loss' if game.get('result') == '0-1' else 'draw'
            else:
                score = 'win' if game.get('result') == '0-1' else 'loss' if game.get('result') == '1-0' else 'draw'
            
            # Extract move evaluations for CPL calculation
            move_evals = []
            moves_table = game.get('moves_table', [])
            for move in moves_table:
                if move.get('mover') == focus_color:  # Only include focus player's moves
                    move_evals.append({
                        'cp_loss': move.get('cp_loss', 0),
                        'phase': move.get('phase', 'middlegame'),
                        'san': move.get('move_san', ''),
                    })
            
            games_with_ratings.append({
                'white_rating': white_rating,
                'black_rating': black_rating,
                'focus_color': focus_color,
                'focus_player_rating': player_rating,
                'opponent_rating': opponent_rating,
                'result': game.get('result', ''),
                'game_info': {
                    'score': score,
                    'opponent_elo': opponent_rating,
                    'opponent_rating': opponent_rating,
                    'opening_name': game.get('opening', 'Unknown'),
                    'eco': game.get('eco', ''),
                    'date': game.get('date', ''),
                    'color': focus_color,
                },
                'move_evals': move_evals,
            })
    
    if not games_with_ratings:
        st.warning("No rating data available in analyzed games. Opponent strength analysis requires games with player ratings.")
        st.info("💡 Tip: Lichess games usually include ratings. Try analyzing games from Lichess to see opponent strength analysis.")
        return
    
    avg_player_rating = total_player_rating // rating_count if rating_count > 0 else 0
    
    st.metric("Your Average Rating", avg_player_rating)
    st.caption(f"Based on {len(games_with_ratings)} games with rating data")
    
    # Render opponent strength analysis
    render_opponent_strength_analysis(games_with_ratings, avg_player_rating)


def _render_streaks_tab(aggregated: dict[str, Any]) -> None:
    """Render the streaks and achievements tab."""
    st.header("🏆 Streaks & Achievements")
    st.caption("Track your winning streaks and unlock achievements")
    
    games = aggregated.get("games", [])
    focus_player = aggregated.get("focus_player", "").strip()
    
    if not games:
        st.info("No games analyzed yet. Run an analysis first!")
        return
    
    if not focus_player:
        st.warning("No focus player identified. Please analyze games from a specific player.")
        return
    
    # Convert games to the format expected by detect_current_streaks
    games_for_streaks = []
    for game in games:
        # Determine score from result and focus color
        focus_color = game.get('focus_color', 'white')
        result = game.get('result', '')
        
        if focus_color == 'white':
            score = 'win' if result == '1-0' else 'loss' if result == '0-1' else 'draw'
        else:
            score = 'win' if result == '0-1' else 'loss' if result == '1-0' else 'draw'
        
        # Check for blunders in moves_table
        moves_table = game.get('moves_table', [])
        move_evals = []
        for move in moves_table:
            cp_loss = move.get('cp_loss', 0)
            # Mark as blunder if CP loss >= 300
            blunder_type = 'blunder' if cp_loss >= 300 else None
            move_evals.append({
                'cp_loss': cp_loss,
                'blunder_type': blunder_type,
            })
        
        games_for_streaks.append({
            'game_info': {
                'date': game.get('date', ''),
                'score': score,
            },
            'move_evals': move_evals,
            'opening': game.get('opening', 'Unknown'),
        })
    
    # Detect current streaks
    streaks = detect_current_streaks(games_for_streaks, focus_player)
    
    # Render streak badges and achievements
    render_streak_badges(streaks)
    
    # Show achievement milestones
    st.divider()
    st.subheader("🎯 Achievement Milestones")
    
    # Hardcode milestones with proper formatting
    milestones = [
        ("🥉 Bronze Streak", 3),
        ("🥈 Silver Streak", 5),
        ("🥇 Gold Streak", 7),
        ("💎 Diamond Streak", 10),
        ("👑 Master Streak", 15),
        ("🏆 Grandmaster Streak", 20),
    ]
    
    milestone_cols = st.columns(3)
    for i, (name, count) in enumerate(milestones):
        col = milestone_cols[i % 3]
        with col:
            st.metric(name, f"{count} games")


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

