from typing import Dict, Any, Optional, List
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


# --- Solution Line Cache Table ---

def get_cached_solution_line(puzzle_key: str) -> Optional[List[str]]:
    """Fetch pre-computed solution line from Supabase."""
    try:
        res = supabase.table("puzzle_solutions").select("solution_line").eq("puzzle_key", puzzle_key).single().execute()
        if res.data and res.data.get("solution_line"):
            return res.data["solution_line"]
    except Exception:
        pass
    return None


def save_solution_line(puzzle_key: str, solution_line: List[str]) -> bool:
    """Save computed solution line to Supabase for future fast lookup."""
    try:
        data = {
            "puzzle_key": puzzle_key,
            "solution_line": solution_line,
        }
        # Upsert to handle duplicates
        supabase.table("puzzle_solutions").upsert(data, on_conflict="puzzle_key").execute()
        return True
    except Exception:
        return False


def batch_get_solution_lines(puzzle_keys: List[str]) -> Dict[str, List[str]]:
    """Batch fetch solution lines for multiple puzzles."""
    if not puzzle_keys:
        return {}
    try:
        res = supabase.table("puzzle_solutions").select("puzzle_key,solution_line").in_("puzzle_key", puzzle_keys).execute()
        if res.data:
            return {row["puzzle_key"]: row["solution_line"] for row in res.data if row.get("solution_line")}
    except Exception:
        pass
    return {}
