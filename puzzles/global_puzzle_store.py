from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import chess

from puzzles.puzzle_types import Puzzle


Rating = Literal["dislike", "meh", "like"]


def _repo_root() -> Path:
    # puzzles/ is at <repo>/puzzles
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    p = _repo_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


_GLOBAL_PUZZLES_PATH = _data_dir() / "puzzles_global.jsonl"
_GLOBAL_RATINGS_PATH = _data_dir() / "puzzle_ratings.jsonl"


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


def save_puzzles_to_global_bank(puzzles: list[Puzzle], *, source_user: str | None) -> int:
    """Append puzzles to the global bank (deduped by puzzle_key).

    Returns number of newly added puzzles.
    """
    existing: set[str] = set()
    for obj in _iter_jsonl(_GLOBAL_PUZZLES_PATH):
        key = obj.get("puzzle_key")
        if isinstance(key, str) and key:
            existing.add(key)

    added = 0
    source_user_norm = (source_user or "").strip() or None

    with _GLOBAL_PUZZLES_PATH.open("a", encoding="utf-8") as f:
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
    counts: dict[str, list[int]] = {}  # key -> [dislike, meh, like]
    for obj in _iter_jsonl(_GLOBAL_RATINGS_PATH):
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
    try:
        with _GLOBAL_RATINGS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def load_global_puzzles(*, exclude_source_user: str | None = None) -> list[Puzzle]:
    exclude = (exclude_source_user or "").strip().lower() or None

    puzzles: list[tuple[str, Puzzle]] = []
    seen: set[str] = set()

    for obj in _iter_jsonl(_GLOBAL_PUZZLES_PATH):
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
            puzzles.append((key, Puzzle.from_dict(p)))
            seen.add(key)
        except Exception:
            continue

    # Apply rating priority.
    ratings = load_rating_counts()

    def sort_key(item: tuple[str, Puzzle]) -> tuple:
        key, p = item
        rc = ratings.get(key, RatingCounts())
        # Highest score first, then most likes, then most total votes, then stable key.
        return (-rc.score, -rc.likes, -rc.total, key)

    puzzles_sorted = sorted(puzzles, key=sort_key)
    return [p for _, p in puzzles_sorted]
