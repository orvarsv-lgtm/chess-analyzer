"""
Game Analysis Cache

Stores analyzed game data in SQLite to avoid re-analyzing games.
Dramatically speeds up repeated analysis of the same username.
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

# Cache location - in user's home directory for persistence
CACHE_DIR = Path.home() / ".chess_analyzer_cache"
CACHE_DB = CACHE_DIR / "analyzed_games.db"


def _get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.row_factory = sqlite3.Row
    
    # Create tables if they don't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyzed_games (
            game_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            analysis_depth INTEGER NOT NULL,
            pgn_hash TEXT NOT NULL,
            white TEXT,
            black TEXT,
            result TEXT,
            date TEXT,
            opening TEXT,
            eco TEXT,
            moves_table TEXT,
            focus_color TEXT,
            white_rating INTEGER,
            black_rating INTEGER,
            focus_player_rating INTEGER,
            raw_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_username ON analyzed_games(username)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_depth ON analyzed_games(game_id, analysis_depth)
    """)
    
    conn.commit()
    return conn


def _extract_game_id(headers: dict[str, str]) -> Optional[str]:
    """Extract unique game ID from PGN headers.
    
    For Lichess: Uses the Site URL which contains the game ID
    For Chess.com: Uses Link header or constructs from other fields
    Fallback: Creates hash from key game data
    """
    # Lichess: Site header contains "https://lichess.org/GAMEID"
    site = headers.get("Site", "")
    if "lichess.org/" in site:
        # Extract game ID from URL
        parts = site.split("lichess.org/")
        if len(parts) > 1:
            game_id = parts[1].split("/")[0].split("?")[0]
            if game_id:
                return f"lichess_{game_id}"
    
    # Chess.com: Link header
    link = headers.get("Link", "")
    if "chess.com" in link:
        parts = link.split("/")
        if parts:
            game_id = parts[-1].split("?")[0]
            if game_id:
                return f"chesscom_{game_id}"
    
    # Fallback: Create deterministic ID from game data
    white = headers.get("White", "")
    black = headers.get("Black", "")
    date = headers.get("UTCDate", "") or headers.get("Date", "")
    result = headers.get("Result", "")
    utc_time = headers.get("UTCTime", "") or headers.get("Time", "")
    
    # Create hash from unique combination
    unique_str = f"{white}|{black}|{date}|{utc_time}|{result}"
    game_hash = hashlib.md5(unique_str.encode()).hexdigest()[:12]
    return f"hash_{game_hash}"


def _hash_pgn(pgn: str) -> str:
    """Create hash of PGN for change detection."""
    return hashlib.md5(pgn.encode()).hexdigest()


def get_cached_game(
    game_id: str,
    analysis_depth: int,
    pgn_hash: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """
    Retrieve a cached analyzed game.
    
    Args:
        game_id: Unique game identifier
        analysis_depth: Required minimum depth
        pgn_hash: If provided, verifies PGN hasn't changed
    
    Returns:
        Cached game data dict, or None if not found/outdated
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM analyzed_games 
            WHERE game_id = ? AND analysis_depth >= ?
            ORDER BY analysis_depth DESC
            LIMIT 1
            """,
            (game_id, analysis_depth)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Verify PGN hash if provided
        if pgn_hash and row["pgn_hash"] != pgn_hash:
            return None  # PGN changed, need re-analysis
        
        # Reconstruct game data
        return {
            "game_id": row["game_id"],
            "date": row["date"],
            "white": row["white"],
            "black": row["black"],
            "result": row["result"],
            "eco": row["eco"],
            "opening": row["opening"],
            "moves_table": json.loads(row["moves_table"]) if row["moves_table"] else [],
            "focus_color": row["focus_color"],
            "white_rating": row["white_rating"],
            "black_rating": row["black_rating"],
            "focus_player_rating": row["focus_player_rating"],
            "raw_analysis": json.loads(row["raw_analysis"]) if row["raw_analysis"] else [],
            "_cached": True,
            "_cache_depth": row["analysis_depth"],
        }
    except Exception as e:
        print(f"Cache read error: {e}")
        return None


def cache_game(
    game_id: str,
    username: str,
    analysis_depth: int,
    pgn_hash: str,
    game_data: dict[str, Any],
    raw_analysis: list[dict[str, Any]]
) -> bool:
    """
    Store analyzed game in cache.
    
    Args:
        game_id: Unique game identifier
        username: Player username (for filtering)
        analysis_depth: Depth used for analysis
        pgn_hash: Hash of PGN for change detection
        game_data: Full game data dict
        raw_analysis: Raw engine analysis rows
    
    Returns:
        True if cached successfully
    """
    try:
        conn = _get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO analyzed_games (
                game_id, username, analysis_depth, pgn_hash,
                white, black, result, date, opening, eco,
                moves_table, focus_color, white_rating, black_rating,
                focus_player_rating, raw_analysis, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                username.lower(),
                analysis_depth,
                pgn_hash,
                game_data.get("white"),
                game_data.get("black"),
                game_data.get("result"),
                game_data.get("date"),
                game_data.get("opening"),
                game_data.get("eco"),
                json.dumps(game_data.get("moves_table", [])),
                game_data.get("focus_color"),
                game_data.get("white_rating"),
                game_data.get("black_rating"),
                game_data.get("focus_player_rating"),
                json.dumps(raw_analysis),
                datetime.now().isoformat(),
            )
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Cache write error: {e}")
        return False


def get_cached_games_for_user(
    username: str,
    analysis_depth: int
) -> dict[str, dict[str, Any]]:
    """
    Get all cached games for a username.
    
    Args:
        username: Player username
        analysis_depth: Required minimum depth
    
    Returns:
        Dict mapping game_id -> game_data
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM analyzed_games 
            WHERE username = ? AND analysis_depth >= ?
            """,
            (username.lower(), analysis_depth)
        )
        rows = cursor.fetchall()
        conn.close()
        
        result = {}
        for row in rows:
            result[row["game_id"]] = {
                "game_id": row["game_id"],
                "date": row["date"],
                "white": row["white"],
                "black": row["black"],
                "result": row["result"],
                "eco": row["eco"],
                "opening": row["opening"],
                "moves_table": json.loads(row["moves_table"]) if row["moves_table"] else [],
                "focus_color": row["focus_color"],
                "white_rating": row["white_rating"],
                "black_rating": row["black_rating"],
                "focus_player_rating": row["focus_player_rating"],
                "raw_analysis": json.loads(row["raw_analysis"]) if row["raw_analysis"] else [],
                "_cached": True,
                "_cache_depth": row["analysis_depth"],
            }
        return result
    except Exception as e:
        print(f"Cache read error: {e}")
        return {}


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    try:
        conn = _get_connection()
        
        total = conn.execute("SELECT COUNT(*) FROM analyzed_games").fetchone()[0]
        users = conn.execute("SELECT COUNT(DISTINCT username) FROM analyzed_games").fetchone()[0]
        
        # Size of cache file
        cache_size = CACHE_DB.stat().st_size if CACHE_DB.exists() else 0
        
        conn.close()
        
        return {
            "total_games": total,
            "unique_users": users,
            "cache_size_mb": round(cache_size / (1024 * 1024), 2),
            "cache_path": str(CACHE_DB),
        }
    except Exception as e:
        return {"error": str(e)}


def clear_cache(username: Optional[str] = None) -> int:
    """
    Clear cache, optionally for a specific user only.
    
    Args:
        username: If provided, only clear this user's cache
    
    Returns:
        Number of games cleared
    """
    try:
        conn = _get_connection()
        
        if username:
            cursor = conn.execute(
                "DELETE FROM analyzed_games WHERE username = ?",
                (username.lower(),)
            )
        else:
            cursor = conn.execute("DELETE FROM analyzed_games")
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        print(f"Cache clear error: {e}")
        return 0


def clear_old_cache(days: int = 30) -> int:
    """Clear cache entries older than specified days."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            """
            DELETE FROM analyzed_games 
            WHERE updated_at < datetime('now', ?)
            """,
            (f"-{days} days",)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        print(f"Cache clear error: {e}")
        return 0
