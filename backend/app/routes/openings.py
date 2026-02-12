"""
Opening Explorer – Combines Lichess master/player databases with personal stats.

Endpoints:
- GET /openings/explore — Query master + player databases via Lichess API
- GET /openings/personal — User's personal opening repertoire with stats
- GET /openings/tree — Build an opening tree from the user's games
"""

from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import Game, GameAnalysis, MoveEvaluation, OpeningRepertoire, User
from app.db.session import get_db

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class ExplorerMove(BaseModel):
    san: str
    uci: str
    white: int  # games won by white
    draws: int
    black: int  # games won by black
    total: int
    win_rate: float  # from the side-to-move perspective
    average_rating: Optional[int] = None


class ExplorerResponse(BaseModel):
    fen: str
    source: str  # "masters" | "lichess" | "player"
    total_games: int
    white_wins: int
    draws: int
    black_wins: int
    moves: list[ExplorerMove]
    opening: Optional[str] = None
    eco: Optional[str] = None
    top_games: list[dict] = []


class PersonalOpening(BaseModel):
    opening_name: str
    eco_code: Optional[str]
    color: str
    games_played: int
    games_won: int
    games_drawn: int
    games_lost: int
    win_rate: float
    average_cpl: Optional[float]


class PersonalRepertoireResponse(BaseModel):
    openings: list[PersonalOpening]
    total_openings: int
    most_played: Optional[str]
    best_opening: Optional[str]
    worst_opening: Optional[str]


class OpeningTreeNode(BaseModel):
    san: str
    uci: Optional[str] = None
    games: int
    wins: int
    draws: int
    losses: int
    average_cpl: Optional[float]
    children: list["OpeningTreeNode"] = []


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.get("/explore", response_model=ExplorerResponse)
async def explore_opening(
    fen: str = Query(
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        description="FEN position to explore",
    ),
    source: str = Query(default="masters", description="Database: masters, lichess, player"),
    ratings: Optional[str] = Query(default=None, description="Rating range for lichess DB, e.g. '1600,1800,2000'"),
    speeds: Optional[str] = Query(default=None, description="Speed filters: bullet,blitz,rapid,classical"),
    player: Optional[str] = Query(default=None, description="Lichess username for player DB"),
    color: Optional[str] = Query(default=None, description="Color for player DB: white/black"),
):
    """
    Query the Lichess opening explorer API.
    Supports masters database, lichess player database, and specific player database.
    """
    if source == "masters":
        data = await _fetch_lichess_masters(fen)
    elif source == "lichess":
        data = await _fetch_lichess_database(fen, ratings, speeds)
    elif source == "player":
        if not player:
            raise HTTPException(400, "Player username required for player database")
        data = await _fetch_lichess_player(fen, player, color, speeds)
    else:
        raise HTTPException(400, f"Unknown source: {source}")

    return data


@router.get("/personal", response_model=PersonalRepertoireResponse)
async def personal_repertoire(
    color: Optional[str] = Query(default=None, description="Filter by color: white/black"),
    min_games: int = Query(default=1, description="Minimum games for an opening to appear"),
    sort_by: str = Query(default="games", description="Sort by: games, winrate, cpl"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the user's personal opening repertoire with win rates and CPL.
    """
    query = select(OpeningRepertoire).where(
        OpeningRepertoire.user_id == user.id,
        OpeningRepertoire.games_played >= min_games,
    )

    if color:
        query = query.where(OpeningRepertoire.color == color)

    result = await db.execute(query)
    rows = result.scalars().all()

    openings = []
    for r in rows:
        wr = round((r.games_won / r.games_played) * 100, 1) if r.games_played > 0 else 0
        openings.append(PersonalOpening(
            opening_name=r.opening_name,
            eco_code=r.eco_code,
            color=r.color,
            games_played=r.games_played,
            games_won=r.games_won,
            games_drawn=r.games_drawn,
            games_lost=r.games_lost,
            win_rate=wr,
            average_cpl=r.average_cpl,
        ))

    # Sort
    if sort_by == "winrate":
        openings.sort(key=lambda o: o.win_rate, reverse=True)
    elif sort_by == "cpl":
        openings.sort(key=lambda o: o.average_cpl or 999)
    else:
        openings.sort(key=lambda o: o.games_played, reverse=True)

    # Find best/worst
    most_played = openings[0].opening_name if openings else None
    best_opening = None
    worst_opening = None
    if openings:
        qualifying = [o for o in openings if o.games_played >= 3]
        if qualifying:
            best_opening = max(qualifying, key=lambda o: o.win_rate).opening_name
            worst_opening = min(qualifying, key=lambda o: o.win_rate).opening_name

    return PersonalRepertoireResponse(
        openings=openings,
        total_openings=len(openings),
        most_played=most_played,
        best_opening=best_opening,
        worst_opening=worst_opening,
    )


@router.get("/tree")
async def opening_tree(
    color: str = Query(default="white", description="Color: white/black"),
    max_depth: int = Query(default=10, description="Maximum ply depth"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Build an opening tree from the user's actual games.
    Shows the user's most-played lines with win rates.
    """
    # Fetch all user games of the specified color with analysis
    games_q = await db.execute(
        select(Game).where(
            Game.user_id == user.id,
            Game.color == color,
        ).order_by(Game.date.desc()).limit(200)
    )
    games = games_q.scalars().all()

    if not games:
        return {"tree": [], "total_games": 0}

    # Build a trie of moves from all PGNs
    import chess.pgn
    from io import StringIO

    root: dict = {"children": {}, "games": 0, "wins": 0, "draws": 0, "losses": 0}

    for game in games:
        if not game.moves_pgn:
            continue

        try:
            pgn_io = StringIO(game.moves_pgn)
            pgn_game = chess.pgn.read_game(pgn_io)
            if not pgn_game:
                continue

            board = pgn_game.board()
            node = root
            ply = 0

            for move in pgn_game.mainline_moves():
                if ply >= max_depth:
                    break

                san = board.san(move)
                uci = move.uci()
                board.push(move)
                ply += 1

                if san not in node["children"]:
                    node["children"][san] = {
                        "san": san,
                        "uci": uci,
                        "children": {},
                        "games": 0,
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                    }

                child = node["children"][san]
                child["games"] += 1
                if game.result == "win":
                    child["wins"] += 1
                elif game.result == "draw":
                    child["draws"] += 1
                else:
                    child["losses"] += 1

                node = child

        except Exception:
            continue

    # Convert trie to response format (prune branches with < 2 games)
    def to_tree_nodes(node: dict, min_games: int = 2) -> list[dict]:
        result = []
        for child_data in sorted(
            node["children"].values(),
            key=lambda c: c["games"],
            reverse=True,
        ):
            if child_data["games"] < min_games:
                continue

            total = child_data["games"]
            wr = round((child_data["wins"] / total) * 100, 1) if total > 0 else 0

            result.append({
                "san": child_data["san"],
                "uci": child_data.get("uci"),
                "games": total,
                "wins": child_data["wins"],
                "draws": child_data["draws"],
                "losses": child_data["losses"],
                "win_rate": wr,
                "children": to_tree_nodes(child_data, min_games),
            })
        return result

    tree = to_tree_nodes(root)

    return {"tree": tree, "total_games": len(games), "color": color}


# ═══════════════════════════════════════════════════════════
# Lichess API helpers
# ═══════════════════════════════════════════════════════════


async def _fetch_lichess_masters(fen: str) -> ExplorerResponse:
    """Fetch from Lichess masters database."""
    url = "https://explorer.lichess.ovh/masters"
    params = {"fen": fen}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(502, "Lichess explorer API error")

    data = resp.json()
    return _parse_explorer_response(data, fen, "masters")


async def _fetch_lichess_database(
    fen: str, ratings: Optional[str], speeds: Optional[str]
) -> ExplorerResponse:
    """Fetch from Lichess player database."""
    url = "https://explorer.lichess.ovh/lichess"
    params: dict = {"fen": fen}
    if ratings:
        params["ratings"] = ratings
    if speeds:
        params["speeds"] = speeds

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(502, "Lichess explorer API error")

    data = resp.json()
    return _parse_explorer_response(data, fen, "lichess")


async def _fetch_lichess_player(
    fen: str, player: str, color: Optional[str], speeds: Optional[str]
) -> ExplorerResponse:
    """Fetch from Lichess specific player database."""
    url = "https://explorer.lichess.ovh/player"
    params: dict = {"fen": fen, "player": player}
    if color:
        params["color"] = color
    if speeds:
        params["speeds"] = speeds

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(502, "Lichess explorer API error")

    data = resp.json()
    return _parse_explorer_response(data, fen, "player")


def _parse_explorer_response(data: dict, fen: str, source: str) -> ExplorerResponse:
    """Parse Lichess explorer API response into our schema."""
    white_wins = data.get("white", 0)
    draws = data.get("draws", 0)
    black_wins = data.get("black", 0)
    total = white_wins + draws + black_wins

    moves = []
    for m in data.get("moves", []):
        mw = m.get("white", 0)
        md = m.get("draws", 0)
        mb = m.get("black", 0)
        mt = mw + md + mb

        # Calculate win rate from side-to-move perspective
        # In FEN, " w " means white to move
        is_white_turn = " w " in fen
        if is_white_turn:
            wr = round((mw / mt) * 100, 1) if mt > 0 else 50.0
        else:
            wr = round((mb / mt) * 100, 1) if mt > 0 else 50.0

        moves.append(ExplorerMove(
            san=m.get("san", ""),
            uci=m.get("uci", ""),
            white=mw,
            draws=md,
            black=mb,
            total=mt,
            win_rate=wr,
            average_rating=m.get("averageRating"),
        ))

    opening_name = None
    eco = None
    if "opening" in data and data["opening"]:
        opening_name = data["opening"].get("name")
        eco = data["opening"].get("eco")

    # Top games
    top_games = []
    for g in data.get("topGames", data.get("recentGames", []))[:5]:
        top_games.append({
            "id": g.get("id"),
            "white": g.get("white", {}).get("name", "?"),
            "white_rating": g.get("white", {}).get("rating"),
            "black": g.get("black", {}).get("name", "?"),
            "black_rating": g.get("black", {}).get("rating"),
            "winner": g.get("winner"),
            "year": g.get("year"),
            "month": g.get("month"),
        })

    return ExplorerResponse(
        fen=fen,
        source=source,
        total_games=total,
        white_wins=white_wins,
        draws=draws,
        black_wins=black_wins,
        moves=moves,
        opening=opening_name,
        eco=eco,
        top_games=top_games,
    )
