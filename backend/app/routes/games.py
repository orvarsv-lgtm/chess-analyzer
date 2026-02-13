"""
Games routes – Fetch from Lichess, import Chess.com PGN, list user games.
"""

from __future__ import annotations

from io import StringIO
from typing import Optional

import chess.pgn
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_user
from app.db.models import Game, User
from app.db.session import get_db
from app.analysis_core import extract_opening_name

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class FetchLichessRequest(BaseModel):
    username: str
    max_games: int = 50


class FetchChesscomRequest(BaseModel):
    username: str
    max_games: int = 50


class ImportPGNRequest(BaseModel):
    pgn_text: str
    platform: str = "chess.com"  # or 'lichess', 'other'


class GameOut(BaseModel):
    id: int
    platform: str
    platform_game_id: Optional[str]
    date: str
    color: str
    result: str
    white_player: Optional[str] = None
    black_player: Optional[str] = None
    opening_name: Optional[str]
    eco_code: Optional[str]
    time_control: Optional[str]
    player_elo: Optional[int]
    opponent_elo: Optional[int]
    moves_count: Optional[int]
    has_analysis: bool = False

    class Config:
        from_attributes = True


class GamesListResponse(BaseModel):
    games: list[GameOut]
    total: int
    page: int
    per_page: int


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════


@router.get("", response_model=GamesListResponse)
async def list_games(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    result: Optional[str] = None,
    opening: Optional[str] = None,
    platform: Optional[str] = None,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's games with pagination and filters."""
    query = select(Game).where(Game.user_id == user.id)

    if result:
        query = query.where(Game.result == result)
    if opening:
        query = query.where(Game.opening_name.ilike(f"%{opening}%"))
    if platform:
        query = query.where(Game.platform == platform)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate — eagerly load analysis relationship to avoid lazy-load in async
    query = (
        query.options(selectinload(Game.analysis))
        .order_by(Game.date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(query)).scalars().all()

    games_out = []
    for g in rows:
        # Extract player names from PGN if not stored in DB
        wp = g.white_player
        bp = g.black_player
        if (not wp or not bp) and g.moves_pgn:
            try:
                import chess.pgn as cpgn
                from io import StringIO as SIO
                _pg = cpgn.read_game(SIO(g.moves_pgn))
                if _pg:
                    wp = wp or _pg.headers.get("White")
                    bp = bp or _pg.headers.get("Black")
            except Exception:
                pass
        games_out.append(
            GameOut(
                id=g.id,
                platform=g.platform,
                platform_game_id=g.platform_game_id,
                date=g.date.isoformat() if g.date else "",
                color=g.color,
                result=g.result,
                white_player=wp,
                black_player=bp,
                opening_name=g.opening_name,
                eco_code=g.eco_code,
                time_control=g.time_control,
                player_elo=g.player_elo,
                opponent_elo=g.opponent_elo,
                moves_count=g.moves_count,
                has_analysis=g.analysis is not None,
            )
        )

    return GamesListResponse(games=games_out, total=total, page=page, per_page=per_page)


@router.post("/fetch-lichess")
async def fetch_lichess_games(
    body: FetchLichessRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch recent games from Lichess API and store them.
    """
    url = f"https://lichess.org/api/games/user/{body.username}"
    params = {
        "max": min(body.max_games, 100),
        "pgnInBody": "true",
        "clocks": "true",
        "evals": "false",
        "opening": "true",
    }
    headers = {"Accept": "application/x-chess-pgn"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Lichess user '{body.username}' not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Lichess API error")

    pgn_text = resp.text
    imported = await _import_pgn_games(db, user, pgn_text, "lichess")

    # Save the lichess username on the user profile
    # Re-fetch user to avoid expired attribute issues after commit in _import_pgn_games
    await db.refresh(user)
    if not user.lichess_username:
        user.lichess_username = body.username
        db.add(user)
        await db.commit()

    return {"imported": imported, "username": body.username}


@router.post("/fetch-chesscom")
async def fetch_chesscom_games(
    body: FetchChesscomRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch recent games from Chess.com public API and store them.
    Uses the Published Data API (no API key required).
    """
    base_url = f"https://api.chess.com/pub/player/{body.username.lower()}"
    req_headers = {
        "User-Agent": "ChessAnalyzer/2.0 (chess analysis platform)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Verify the player exists
        profile_resp = await client.get(base_url, headers=req_headers)
        if profile_resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Chess.com user '{body.username}' not found",
            )
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Chess.com API error")

        # 2. Get the monthly archives list
        archives_resp = await client.get(
            f"{base_url}/games/archives", headers=req_headers
        )
        if archives_resp.status_code != 200:
            raise HTTPException(
                status_code=502, detail="Failed to fetch Chess.com game archives"
            )

        archives: list[str] = archives_resp.json().get("archives", [])
        if not archives:
            return {"imported": 0, "username": body.username}

        # 3. Fetch the most recent months (work backwards) until we have enough games
        all_pgn_parts: list[str] = []
        total_fetched = 0
        # Process archives from most recent to oldest
        for archive_url in reversed(archives):
            if total_fetched >= body.max_games:
                break
            month_resp = await client.get(archive_url, headers=req_headers)
            if month_resp.status_code != 200:
                continue  # skip months that fail
            month_data = month_resp.json()
            month_games = month_data.get("games", [])
            for g in reversed(month_games):  # newest first within month
                if total_fetched >= body.max_games:
                    break
                pgn = g.get("pgn", "")
                if pgn:
                    all_pgn_parts.append(pgn)
                    total_fetched += 1

    if not all_pgn_parts:
        return {"imported": 0, "username": body.username}

    combined_pgn = "\n\n".join(all_pgn_parts)
    imported = await _import_pgn_games(db, user, combined_pgn, "chess.com")

    # Save the chess.com username on the user profile
    # Re-fetch user to avoid expired attribute issues after commit in _import_pgn_games
    await db.refresh(user)
    if not user.chesscom_username:
        user.chesscom_username = body.username
        db.add(user)
        await db.commit()

    return {"imported": imported, "username": body.username}


@router.post("/import-pgn")
async def import_pgn(
    body: ImportPGNRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import games from raw PGN text (Chess.com export, etc.).
    First-class Chess.com support.
    """
    if not body.pgn_text.strip():
        raise HTTPException(status_code=400, detail="PGN text is empty")

    imported = await _import_pgn_games(db, user, body.pgn_text, body.platform)
    return {"imported": imported, "platform": body.platform}


@router.post("/import-pgn-file")
async def import_pgn_file(
    file: UploadFile = File(...),
    platform: str = Query("chess.com"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a .pgn file to import games."""
    if not file.filename or not file.filename.endswith(".pgn"):
        raise HTTPException(status_code=400, detail="File must be a .pgn file")

    content = await file.read()
    pgn_text = content.decode("utf-8", errors="replace")
    imported = await _import_pgn_games(db, user, pgn_text, platform)
    return {"imported": imported, "platform": platform, "filename": file.filename}


@router.get("/{game_id}")
async def get_game(
    game_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single game with its PGN and analysis (if available)."""
    result = await db.execute(
        select(Game)
        .options(selectinload(Game.analysis))
        .where(Game.id == game_id, Game.user_id == user.id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Extract player names from PGN if not stored in DB
    wp = game.white_player
    bp = game.black_player
    if (not wp or not bp) and game.moves_pgn:
        try:
            import chess.pgn as cpgn
            from io import StringIO as SIO
            _pg = cpgn.read_game(SIO(game.moves_pgn))
            if _pg:
                wp = wp or _pg.headers.get("White")
                bp = bp or _pg.headers.get("Black")
        except Exception:
            pass

    resp = {
        "id": game.id,
        "platform": game.platform,
        "date": game.date.isoformat() if game.date else None,
        "color": game.color,
        "result": game.result,
        "white_player": wp,
        "black_player": bp,
        "opening_name": game.opening_name,
        "eco_code": game.eco_code,
        "time_control": game.time_control,
        "player_elo": game.player_elo,
        "opponent_elo": game.opponent_elo,
        "moves_pgn": game.moves_pgn,
        "moves_count": game.moves_count,
    }

    if game.analysis:
        resp["analysis"] = {
            "overall_cpl": game.analysis.overall_cpl,
            "phase_opening_cpl": game.analysis.phase_opening_cpl,
            "phase_middlegame_cpl": game.analysis.phase_middlegame_cpl,
            "phase_endgame_cpl": game.analysis.phase_endgame_cpl,
            "blunders": game.analysis.blunders_count,
            "mistakes": game.analysis.mistakes_count,
            "inaccuracies": game.analysis.inaccuracies_count,
            "best_moves": game.analysis.best_moves_count,
            "depth": game.analysis.analysis_depth,
        }

    return resp


# ═══════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════


async def _import_pgn_games(
    db: AsyncSession, user: User, pgn_text: str, platform: str
) -> int:
    """Parse multi-game PGN text and insert games. Returns count imported."""
    from datetime import datetime
    import hashlib

    pgn_io = StringIO(pgn_text)
    imported = 0

    # Eagerly read user attributes to avoid lazy-loading issues after rollback.
    # In async SQLAlchemy, accessing expired attributes triggers a sync IO call
    # which raises MissingGreenlet.
    user_id = user.id
    chesscom_name = user.chesscom_username
    lichess_name = user.lichess_username

    # Collect existing platform_game_ids for this user+platform to skip dupes
    existing_ids_result = await db.execute(
        select(Game.platform_game_id).where(
            Game.user_id == user_id, Game.platform == platform
        )
    )
    existing_ids: set[str] = {
        row[0] for row in existing_ids_result.fetchall() if row[0]
    }

    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        headers = game.headers
        moves_pgn = str(game)

        # Determine color and result
        white = headers.get("White", "")
        black = headers.get("Black", "")
        result_raw = headers.get("Result", "*")

        # Try to figure out which side is the user
        # For Lichess we have the username; for Chess.com PGN imports we
        # default to white unless we can match usernames later.
        color = "white"
        if chesscom_name and chesscom_name.lower() == black.lower():
            color = "black"
        elif lichess_name and lichess_name.lower() == black.lower():
            color = "black"

        if result_raw == "1-0":
            result = "win" if color == "white" else "loss"
        elif result_raw == "0-1":
            result = "win" if color == "black" else "loss"
        else:
            result = "draw"

        # Extract metadata
        date_str = headers.get("UTCDate", headers.get("Date", ""))
        time_str = headers.get("UTCTime", "00:00:00")

        try:
            dt = datetime.fromisoformat(f"{date_str.replace('.', '-')}T{time_str}")
        except (ValueError, AttributeError):
            dt = datetime.utcnow()

        # Platform-specific game ID
        site = headers.get("Site", "")
        platform_game_id = None
        if "lichess.org" in site:
            platform_game_id = site.split("/")[-1]
        elif "chess.com" in site:
            platform_game_id = site.split("/")[-1]
        else:
            # Use a hash of the PGN
            platform_game_id = hashlib.md5(moves_pgn.encode()).hexdigest()[:16]

        # Skip duplicates without touching the DB
        if platform_game_id and platform_game_id in existing_ids:
            continue

        # Count moves
        moves_list = list(game.mainline_moves())
        moves_count = len(moves_list)

        # ELO
        try:
            white_elo = int(headers.get("WhiteElo", 0))
        except (ValueError, TypeError):
            white_elo = None
        try:
            black_elo = int(headers.get("BlackElo", 0))
        except (ValueError, TypeError):
            black_elo = None

        player_elo = white_elo if color == "white" else black_elo
        opponent_elo = black_elo if color == "white" else white_elo

        opening = extract_opening_name(headers)
        eco = headers.get("ECO", None)
        time_control = headers.get("TimeControl", None)

        game_row = Game(
            user_id=user_id,
            platform=platform,
            platform_game_id=platform_game_id,
            date=dt,
            color=color,
            result=result,
            white_player=white or None,
            black_player=black or None,
            opening_name=opening,
            eco_code=eco,
            time_control=time_control,
            player_elo=player_elo,
            opponent_elo=opponent_elo,
            moves_count=moves_count,
            moves_pgn=moves_pgn,
        )

        try:
            db.add(game_row)
            await db.flush()
            imported += 1
            # Track so we don't try to insert the same ID again in this batch
            if platform_game_id:
                existing_ids.add(platform_game_id)
        except Exception:
            await db.rollback()
            continue

    await db.commit()
    return imported
