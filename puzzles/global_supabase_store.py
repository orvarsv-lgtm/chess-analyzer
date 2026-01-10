from typing import Dict, Any, Optional
from puzzles.supabase_client import supabase

# --- Puzzles Global Table ---

def insert_puzzle_global(puzzle_key: str, source_user: str, ts: int, puzzle: dict) -> Any:
    data = {
        "puzzle_key": puzzle_key,
        "source_user": source_user,
        "ts": ts,
        "puzzle": puzzle,
    }
    return supabase.table("puzzles_global").insert(data).execute()

def get_puzzle_global(puzzle_key: str) -> Optional[dict]:
    res = supabase.table("puzzles_global").select("*").eq("puzzle_key", puzzle_key).single().execute()
    return res.data if res.data else None

# --- Puzzle Ratings Table ---

def insert_puzzle_rating(puzzle_key: str, rating: str, rater: str, ts: int) -> Any:
    data = {
        "puzzle_key": puzzle_key,
        "rating": rating,
        "rater": rater,
        "ts": ts,
    }
    return supabase.table("puzzle_ratings").insert(data).execute()

def get_puzzle_ratings(puzzle_key: str) -> list:
    res = supabase.table("puzzle_ratings").select("*").eq("puzzle_key", puzzle_key).execute()
    return res.data if res.data else []
