"""
Opening Explorer – Combines Lichess master/player databases with personal stats.

Endpoints:
- GET /openings/explore — Query master + player databases via Lichess API
- GET /openings/personal — User's personal opening repertoire with stats
- GET /openings/tree — Build an opening tree from the user's games
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import chess
import chess.engine
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import get_settings
from app.db.models import Game, MoveEvaluation, OpeningRepertoire, User
from app.db.session import get_db

router = APIRouter()

# ═══════════════════════════════════════════════════════════
# In-memory cache for explorer responses (TTL-based)
# ═══════════════════════════════════════════════════════════

_explorer_cache: dict[str, tuple[float, "ExplorerResponse"]] = {}
_CACHE_TTL = 600  # 10 minutes
_CACHE_MAX = 500  # max entries


def _cache_get(key: str) -> "ExplorerResponse | None":
    entry = _explorer_cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    if entry:
        del _explorer_cache[key]
    return None


def _cache_set(key: str, value: "ExplorerResponse") -> None:
    if len(_explorer_cache) >= _CACHE_MAX:
        oldest_key = min(_explorer_cache, key=lambda k: _explorer_cache[k][0])
        del _explorer_cache[oldest_key]
    _explorer_cache[key] = (time.time(), value)


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
    average_cpl: Optional[float] = None
    best_move_san: Optional[str] = None
    eval_cp: Optional[int] = None
    win_rate: Optional[float] = None
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
    Shows the user's most-played lines with win rates and engine eval data.
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

    # Fetch engine evaluations for these games (indexed by fen_before)
    game_ids = [g.id for g in games]
    evals_q = await db.execute(
        select(MoveEvaluation).where(
            MoveEvaluation.game_id.in_(game_ids),
        )
    )
    all_evals = evals_q.scalars().all()

    # Build lookup: fen_before -> best_move_san, eval_before (take first non-null)
    eval_by_fen: dict[str, dict] = {}
    for ev in all_evals:
        if ev.fen_before and ev.fen_before not in eval_by_fen:
            eval_by_fen[ev.fen_before] = {
                "best_move_san": ev.best_move_san,
                "eval_before": ev.eval_before,
            }

    # Build per-move CPL lookup: (fen_before, san) -> list of cp_loss values
    cpl_by_move: dict[tuple[str, str], list[int]] = {}
    for ev in all_evals:
        if ev.fen_before and ev.san and ev.cp_loss is not None:
            key = (ev.fen_before, ev.san)
            cpl_by_move.setdefault(key, []).append(ev.cp_loss)

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

                fen_before = board.fen()
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
                        "fen_before": fen_before,
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

            # Cross-reference engine eval data
            fen = child_data.get("fen_before")
            ev_data = eval_by_fen.get(fen, {}) if fen else {}

            # Compute average CPL for this specific move
            cpl_key = (fen, child_data["san"]) if fen else None
            cpl_values = cpl_by_move.get(cpl_key, []) if cpl_key else []
            avg_cpl = round(sum(cpl_values) / len(cpl_values), 1) if cpl_values else None

            result.append({
                "san": child_data["san"],
                "uci": child_data.get("uci"),
                "games": total,
                "wins": child_data["wins"],
                "draws": child_data["draws"],
                "losses": child_data["losses"],
                "win_rate": wr,
                "best_move_san": ev_data.get("best_move_san"),
                "eval_cp": ev_data.get("eval_before"),
                "average_cpl": avg_cpl,
                "children": to_tree_nodes(child_data, min_games),
            })
        return result

    tree = to_tree_nodes(root)

    return {"tree": tree, "total_games": len(games), "color": color}


# ═══════════════════════════════════════════════════════════
# Lichess API helpers
# ═══════════════════════════════════════════════════════════


async def _lichess_get(url: str, params: dict, retries: int = 3) -> dict:
    """GET from Lichess with retry on 429 rate-limit."""
    for attempt in range(retries):
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            wait = 1.5 * (attempt + 1)
            await asyncio.sleep(wait)
            continue
        raise HTTPException(502, f"Lichess explorer API error (HTTP {resp.status_code})")
    raise HTTPException(502, "Lichess explorer API rate limited – try again shortly")


async def _fetch_lichess_masters(fen: str) -> ExplorerResponse:
    """Fetch from Lichess masters database (cached)."""
    cache_key = f"masters:{fen}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    data = await _lichess_get("https://explorer.lichess.ovh/masters", {"fen": fen})
    result = _parse_explorer_response(data, fen, "masters")
    _cache_set(cache_key, result)
    return result


async def _fetch_lichess_database(
    fen: str, ratings: Optional[str], speeds: Optional[str]
) -> ExplorerResponse:
    """Fetch from Lichess database (cached)."""
    cache_key = f"lichess:{fen}:{ratings}:{speeds}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    params: dict = {"fen": fen}
    if ratings:
        params["ratings"] = ratings
    if speeds:
        params["speeds"] = speeds
    data = await _lichess_get("https://explorer.lichess.ovh/lichess", params)
    result = _parse_explorer_response(data, fen, "lichess")
    _cache_set(cache_key, result)
    return result


async def _fetch_lichess_player(
    fen: str, player: str, color: Optional[str], speeds: Optional[str]
) -> ExplorerResponse:
    """Fetch from Lichess player database (cached)."""
    cache_key = f"player:{player}:{color}:{fen}:{speeds}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    params: dict = {"fen": fen, "player": player}
    if color:
        params["color"] = color
    if speeds:
        params["speeds"] = speeds
    data = await _lichess_get("https://explorer.lichess.ovh/player", params)
    result = _parse_explorer_response(data, fen, "player")
    _cache_set(cache_key, result)
    return result


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


# ═══════════════════════════════════════════════════════════
# Move validation via Stockfish
# ═══════════════════════════════════════════════════════════

CPL_THRESHOLD = 50  # moves losing ≤50 cp are considered viable
VALIDATE_DEPTH = 14


class ValidateMoveRequest(BaseModel):
    fen: str
    san: str


class ValidateMoveResponse(BaseModel):
    viable: bool
    cp_loss: int
    best_move_san: str
    eval_before: int  # centipawns from side-to-move perspective
    eval_after: int


def _pov_to_cp(pov_score: chess.engine.PovScore, pov_color: chess.Color) -> int:
    """Convert PovScore to centipawns from the given color's perspective."""
    score = pov_score.pov(pov_color)
    if score.is_mate():
        m = score.mate() or 0
        return 10_000 if m > 0 else -10_000
    return score.score() or 0


@router.post("/validate-move", response_model=ValidateMoveResponse)
async def validate_move(
    body: ValidateMoveRequest,
    user: User = Depends(require_user),
):
    """
    Check whether a move is viable (≤50 cp loss) using Stockfish.
    Used by the opening drill to accept any reasonable move.
    """
    settings = get_settings()

    try:
        board = chess.Board(body.fen)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid FEN")

    try:
        move = board.parse_san(body.san)
    except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
        raise HTTPException(400, f"Invalid or illegal move: {body.san}")

    turn = board.turn

    try:
        transport, engine = await chess.engine.popen_uci(settings.stockfish_path)
    except Exception:
        raise HTTPException(503, "Stockfish engine unavailable")

    try:
        # Evaluate position before the move (from side-to-move perspective)
        info_before = await engine.analyse(
            board,
            chess.engine.Limit(depth=VALIDATE_DEPTH),
            info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
        )
        eval_before = _pov_to_cp(info_before["score"], turn)
        best_pv = info_before.get("pv", [])
        best_move_san = board.san(best_pv[0]) if best_pv else body.san

        # Evaluate position after the move (from original side-to-move perspective)
        board.push(move)
        info_after = await engine.analyse(
            board,
            chess.engine.Limit(depth=VALIDATE_DEPTH),
            info=chess.engine.INFO_SCORE,
        )
        eval_after = _pov_to_cp(info_after["score"], turn)
    finally:
        await engine.quit()

    cp_loss = max(0, eval_before - eval_after)
    viable = cp_loss <= CPL_THRESHOLD

    return ValidateMoveResponse(
        viable=viable,
        cp_loss=cp_loss,
        best_move_san=best_move_san,
        eval_before=eval_before,
        eval_after=eval_after,
    )


class BestMoveRequest(BaseModel):
    fen: str


class BestMoveResponse(BaseModel):
    best_move_san: str


@router.post("/best-move", response_model=BestMoveResponse)
async def best_move(
    body: BestMoveRequest,
    user: User = Depends(require_user),
):
    """Return the engine's best move for a given FEN (used for opponent replies in drill)."""
    settings = get_settings()

    try:
        board = chess.Board(body.fen)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid FEN")

    try:
        transport, engine = await chess.engine.popen_uci(settings.stockfish_path)
    except Exception:
        raise HTTPException(503, "Stockfish engine unavailable")

    try:
        info = await engine.analyse(
            board,
            chess.engine.Limit(depth=VALIDATE_DEPTH),
            info=chess.engine.INFO_PV,
        )
        pv = info.get("pv", [])
        if not pv:
            raise HTTPException(500, "Engine returned no move")
        san = board.san(pv[0])
    finally:
        await engine.quit()

    return BestMoveResponse(best_move_san=san)
