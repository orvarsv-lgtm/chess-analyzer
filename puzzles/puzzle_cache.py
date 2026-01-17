"""Disk cache for generated puzzles to avoid regenerating for same games."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List

from puzzles.puzzle_types import Puzzle

# Import pattern enrichment from global store
try:
    from puzzles.global_puzzle_store import _enrich_puzzle_with_patterns
    HAS_ENRICH = True
except ImportError:
    HAS_ENRICH = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _cache_dir() -> Path:
    p = _repo_root() / "data" / "puzzle_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key_for_games(games: List[dict]) -> str:
    """Generate a stable cache key from game signatures."""
    h = hashlib.sha256()
    h.update(str(len(games)).encode("utf-8"))
    
    for g in games[:50]:  # Sample first 50 games for key
        if not isinstance(g, dict):
            continue
        for k in ("game_id", "id", "url", "date", "white", "black", "result"):
            v = g.get(k)
            if v:
                h.update(str(v).encode("utf-8"))
                h.update(b"|")
        moves = g.get("moves") or g.get("moves_san") or g.get("pgn_moves")
        if isinstance(moves, list):
            moves = " ".join(str(m) for m in moves[:20])
        if isinstance(moves, str):
            h.update(moves[:200].encode("utf-8"))
            h.update(b"|")
    
    return h.hexdigest()[:24]


def load_cached_puzzles(games: List[dict], max_age_hours: int = 24) -> List[Puzzle] | None:
    """Load cached puzzles if available.

    If max_age_hours <= 0, the cache never expires.
    """
    try:
        cache_key = _cache_key_for_games(games)
        cache_file = _cache_dir() / f"puzzles_{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        # Check age (unless configured to never expire)
        if int(max_age_hours) > 0:
            mtime = cache_file.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            if age_hours > max_age_hours:
                return None
        
        with cache_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict) or "puzzles" not in data:
            return None
        
        puzzles = [Puzzle.from_dict(p) for p in data["puzzles"]]
        
        # Enrich puzzles with tactical patterns if missing (for old cached puzzles)
        if HAS_ENRICH:
            puzzles = [_enrich_puzzle_with_patterns(p) for p in puzzles]
        
        return puzzles
    except Exception:
        return None


def save_cached_puzzles(games: List[dict], puzzles: List[Puzzle]) -> None:
    """Save puzzles to disk cache."""
    try:
        cache_key = _cache_key_for_games(games)
        cache_file = _cache_dir() / f"puzzles_{cache_key}.json"
        
        data = {
            "cache_key": cache_key,
            "timestamp": int(time.time()),
            "num_games": len(games),
            "num_puzzles": len(puzzles),
            "puzzles": [p.to_dict() for p in puzzles],
        }
        
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # Silent fail - caching is optional
