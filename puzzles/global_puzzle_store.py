from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import requests

import chess

from puzzles.puzzle_types import Puzzle


Rating = Literal["dislike", "meh", "like"]


def _repo_root() -> Path:
    # puzzles/ is at <repo>/puzzles
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    override = (os.getenv("PUZZLE_DATA_DIR") or "").strip()
    if override:
        p = Path(override)
    else:
        p = _repo_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _global_puzzles_path() -> Path:
    return _data_dir() / "puzzles_global.jsonl"


def _global_ratings_path() -> Path:
    return _data_dir() / "puzzle_ratings.jsonl"


def _puzzle_bank_backend() -> str:
    """Return puzzle bank backend.

    - "local": JSONL files under data/ (works locally; NOT persistent on Streamlit Cloud)
    - "supabase": Supabase PostgREST tables (persistent, cross-user)
    """
    return (os.getenv("PUZZLE_BANK_BACKEND") or "local").strip().lower()


def _supabase_config() -> tuple[str, str] | None:
    """Return (url, key) if Supabase is configured."""
    if _puzzle_bank_backend() != "supabase":
        return None

    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()

    if not url or not key:
        return None
    return url, key


def _supabase_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _supabase_fetch_all(
    *,
    table: str,
    select: str,
    filters: list[tuple[str, str, str]] | None = None,
    limit: int = 1000,
    max_rows: int = 20000,
) -> list[dict]:
    """Fetch rows from Supabase using pagination.

    filters is a list of (column, op, value) where op is a PostgREST operator like:
    - "eq", "neq", "is", "ilike"
    """
    cfg = _supabase_config()
    if not cfg:
        return []
    url, key = cfg

    rows: list[dict] = []
    offset = 0

    while len(rows) < max_rows:
        params: dict[str, str | int] = {
            "select": select,
            "limit": limit,
            "offset": offset,
        }
        for col, op, val in (filters or []):
            params[col] = f"{op}.{val}"

        resp = requests.get(
            f"{url}/rest/v1/{table}",
            headers=_supabase_headers(key),
            params=params,
            timeout=10,
        )
        if resp.status_code >= 400:
            return []
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                rows.append(item)
        offset += int(limit)

    return rows


def _supabase_upsert(
    *,
    table: str,
    rows: list[dict],
    on_conflict: str | None = None,
) -> bool:
    cfg = _supabase_config()
    if not cfg:
        return False
    if not rows:
        return True

    url, key = cfg
    params: dict[str, str] = {}
    if on_conflict:
        params["on_conflict"] = on_conflict

    headers = _supabase_headers(key)
    headers["Prefer"] = "resolution=merge-duplicates"

    resp = requests.post(
        f"{url}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=rows,
        timeout=15,
    )
    return resp.status_code < 400


def puzzle_key_from_position(fen: str, first_move_uci: str) -> str:
    """Stable global puzzle key for cross-user dedupe + ratings.

    We intentionally do not rely on Puzzle.puzzle_id because that can collide across
    users (often source_game_index-based).
    """
    base = f"{fen}|{first_move_uci}".encode("utf-8")
    return hashlib.sha1(base).hexdigest()[:16]


def _puzzle_first_move_uci(p: Puzzle) -> str:
    if getattr(p, "best_move_uci", None):
        return str(p.best_move_uci)

    board = chess.Board(p.fen)
    mv = board.parse_san(p.best_move_san)
    return mv.uci()


def puzzle_key_for_puzzle(p: Puzzle) -> str:
    try:
        uci = _puzzle_first_move_uci(p)
    except Exception:
        # Fallback: best_move_san is part of Puzzle, so keep stable-ish.
        uci = str(getattr(p, "best_move_san", ""))
    return puzzle_key_from_position(p.fen, uci)


def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except Exception:
        return []


def save_puzzles_to_global_bank(
    puzzles: list[Puzzle], *, source_user: str | None, game_players: dict[int, tuple[str, str]] | None = None
) -> int:
    """Append puzzles to the global bank (deduped by puzzle_key).

    Returns number of newly added puzzles.
    """
    # Prefer Supabase when configured (Streamlit Cloud-safe persistence)
    if _supabase_config():
        source_user_norm = (source_user or "").strip() or None
        now = int(time.time())

        # Fetch existing keys for fast client-side dedupe.
        existing_keys = {
            r.get("puzzle_key")
            for r in _supabase_fetch_all(table="puzzles_global", select="puzzle_key")
            if isinstance(r.get("puzzle_key"), str)
        }

        to_insert: list[dict] = []
        added = 0

        for p in puzzles:
            try:
                key = puzzle_key_for_puzzle(p)
            except Exception:
                continue
            if key in existing_keys:
                continue
            # Attach origin player names when available so UI can display correct source
            puzzle_dict = p.to_dict()
            try:
                idx = int(getattr(p, "source_game_index", 0) or 0)
            except Exception:
                idx = 0
            if game_players and idx and idx in game_players:
                white_name, black_name = game_players.get(idx, ("", ""))
                puzzle_dict["origin_white"] = white_name
                puzzle_dict["origin_black"] = black_name

            to_insert.append(
                {
                    "puzzle_key": key,
                    "source_user": source_user_norm,
                    "ts": now,
                    "puzzle": puzzle_dict,
                }
            )
            existing_keys.add(key)
            added += 1

        # Upsert to handle concurrent writers safely.
        ok = _supabase_upsert(table="puzzles_global", rows=to_insert, on_conflict="puzzle_key")
        return added if ok else 0

    # Local JSONL fallback (works locally; not durable on Streamlit Cloud)
    existing: set[str] = set()
    puzzles_path = _global_puzzles_path()
    for obj in _iter_jsonl(puzzles_path):
        key = obj.get("puzzle_key")
        if isinstance(key, str) and key:
            existing.add(key)

    added = 0
    source_user_norm = (source_user or "").strip() or None

    with puzzles_path.open("a", encoding="utf-8") as f:
        for p in puzzles:
            try:
                key = puzzle_key_for_puzzle(p)
            except Exception:
                continue
            if key in existing:
                continue

            record = {
                "puzzle_key": key,
                "source_user": source_user_norm,
                "ts": int(time.time()),
                "puzzle": p.to_dict(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing.add(key)
            added += 1

    return added


@dataclass(frozen=True)
class RatingCounts:
    dislikes: int = 0
    mehs: int = 0
    likes: int = 0

    @property
    def total(self) -> int:
        return int(self.dislikes + self.mehs + self.likes)

    @property
    def score(self) -> int:
        # Simple, transparent ranking: likes - dislikes
        return int(self.likes - self.dislikes)


def load_rating_counts() -> dict[str, RatingCounts]:
    # Prefer Supabase when configured
    if _supabase_config():
        counts: dict[str, list[int]] = {}
        rows = _supabase_fetch_all(table="puzzle_ratings", select="puzzle_key,rating")
        for obj in rows:
            key = obj.get("puzzle_key")
            rating = obj.get("rating")
            if not isinstance(key, str) or not key:
                continue
            if rating not in {"dislike", "meh", "like"}:
                continue
            counts.setdefault(key, [0, 0, 0])
            if rating == "dislike":
                counts[key][0] += 1
            elif rating == "meh":
                counts[key][1] += 1
            else:
                counts[key][2] += 1
        return {k: RatingCounts(v[0], v[1], v[2]) for k, v in counts.items()}

    counts: dict[str, list[int]] = {}  # key -> [dislike, meh, like]
    ratings_path = _global_ratings_path()
    for obj in _iter_jsonl(ratings_path):
        key = obj.get("puzzle_key")
        rating = obj.get("rating")
        if not isinstance(key, str) or not key:
            continue
        if rating not in {"dislike", "meh", "like"}:
            continue
        if key not in counts:
            counts[key] = [0, 0, 0]
        if rating == "dislike":
            counts[key][0] += 1
        elif rating == "meh":
            counts[key][1] += 1
        else:
            counts[key][2] += 1

    return {k: RatingCounts(v[0], v[1], v[2]) for k, v in counts.items()}


def record_puzzle_rating(*, puzzle_key: str, rating: Rating, rater: str | None = None) -> None:
    key = (puzzle_key or "").strip()
    if not key:
        return
    rater_norm = (rater or "").strip() or None

    payload = {
        "puzzle_key": key,
        "rating": rating,
        "rater": rater_norm,
        "ts": int(time.time()),
    }

    # Prefer Supabase when configured
    if _supabase_config():
        _ = _supabase_upsert(table="puzzle_ratings", rows=[payload], on_conflict=None)
        return

    try:
        with _global_ratings_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def get_user_rated_keys(rater: str | None) -> set[str]:
    """Return set of puzzle_key strings that the given rater has rated.

    Works with Supabase when configured, otherwise scans local JSONL ratings file.
    """
    r = (rater or "").strip()
    if not r:
        return set()

    keys = set()
    if _supabase_config():
        rows = _supabase_fetch_all(table="puzzle_ratings", select="puzzle_key,rater", filters=[("rater", "eq", r)])
        for obj in rows:
            k = obj.get("puzzle_key")
            if isinstance(k, str) and k:
                keys.add(k)
        return keys

    for obj in _iter_jsonl(_global_ratings_path()):
        if obj.get("rater") == r:
            k = obj.get("puzzle_key")
            if isinstance(k, str) and k:
                keys.add(k)
    return keys


def load_global_puzzles(*, exclude_source_user: str | None = None) -> list[Puzzle]:
    exclude = (exclude_source_user or "").strip().lower() or None

    puzzles: list[tuple[str, Puzzle]] = []
    seen: set[str] = set()

    # Prefer Supabase when configured
    if _supabase_config():
        filters: list[tuple[str, str, str]] = []
        if exclude:
            filters.append(("source_user", "neq", exclude))

        rows = _supabase_fetch_all(
            table="puzzles_global",
            select="puzzle_key,source_user,puzzle",
            filters=filters,
        )
        for obj in rows:
            key = obj.get("puzzle_key")
            if not isinstance(key, str) or not key:
                continue
            if key in seen:
                continue
            p = obj.get("puzzle")
            if not isinstance(p, dict):
                continue

            try:
                puzzle = Puzzle.from_dict(p)
                # Preserve origin player names if stored in the record
                origin_white = p.get("origin_white") if isinstance(p, dict) else None
                origin_black = p.get("origin_black") if isinstance(p, dict) else None
                if origin_white:
                    setattr(puzzle, "origin_white", origin_white)
                if origin_black:
                    setattr(puzzle, "origin_black", origin_black)
                try:
                    board = chess.Board(puzzle.fen)
                    if not puzzle.best_move_uci:
                        board.parse_san(puzzle.best_move_san)
                except Exception:
                    continue
                puzzles.append((key, puzzle))
                seen.add(key)
            except Exception:
                continue
    else:
        for obj in _iter_jsonl(_global_puzzles_path()):
            key = obj.get("puzzle_key")
            if not isinstance(key, str) or not key:
                continue
            if key in seen:
                continue

            src_user = obj.get("source_user")
            if exclude and isinstance(src_user, str) and src_user.strip().lower() == exclude:
                continue

            p = obj.get("puzzle")
            if not isinstance(p, dict):
                continue

            try:
                puzzle = Puzzle.from_dict(p)
                # Preserve origin player names if stored in the record
                origin_white = p.get("origin_white") if isinstance(p, dict) else None
                origin_black = p.get("origin_black") if isinstance(p, dict) else None
                if origin_white:
                    setattr(puzzle, "origin_white", origin_white)
                if origin_black:
                    setattr(puzzle, "origin_black", origin_black)
                # Validate that the puzzle is valid before adding it
                # This catches issues like invalid FEN or SAN that would cause crashes later
                try:
                    board = chess.Board(puzzle.fen)
                    # Verify best_move_san is legal in this position
                    if not puzzle.best_move_uci:
                        board.parse_san(puzzle.best_move_san)
                except Exception:
                    # Skip invalid puzzles silently
                    continue
                puzzles.append((key, puzzle))
                seen.add(key)
            except Exception:
                continue

    # Return unsorted puzzles - sorting by rating will happen AFTER filtering
    # This ensures user filters take priority over rating quality
    return [p for _, p in puzzles]
