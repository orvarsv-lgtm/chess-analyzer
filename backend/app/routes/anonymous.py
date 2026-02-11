"""
Anonymous analysis routes – Allow unauthenticated users to fetch + analyze games.

Results are returned directly (no user account required).
The frontend stores them in memory and gates "Get Results" behind sign-in.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from typing import Optional

import chess
import chess.engine
import chess.pgn
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════


class AnonFetchRequest(BaseModel):
    platform: str  # "lichess" | "chess.com" | "pgn"
    username: Optional[str] = None
    pgn_text: Optional[str] = None
    max_games: int = 20


class MoveEvalOut(BaseModel):
    move_number: int
    color: str
    san: str
    cp_loss: int
    phase: Optional[str]
    move_quality: Optional[str]
    eval_before: Optional[int]
    eval_after: Optional[int]


class GameAnalysisOut(BaseModel):
    game_index: int
    white: str
    black: str
    result: str
    opening: Optional[str]
    eco: Optional[str]
    date: Optional[str]
    time_control: Optional[str]
    color: str
    overall_cpl: float
    phase_opening_cpl: Optional[float]
    phase_middlegame_cpl: Optional[float]
    phase_endgame_cpl: Optional[float]
    blunders: int
    mistakes: int
    inaccuracies: int
    best_moves: int
    moves: list[MoveEvalOut]


class AnonAnalysisResponse(BaseModel):
    username: Optional[str]
    platform: str
    total_games: int
    games: list[GameAnalysisOut]
    overall_cpl: Optional[float]
    win_rate: Optional[float]
    blunder_rate: Optional[float]


# ═══════════════════════════════════════════════════════════
# Endpoint — SSE stream for progress updates
# ═══════════════════════════════════════════════════════════


@router.post("/analyze")
async def anonymous_analyze(body: AnonFetchRequest):
    """
    Fetch games and analyze them with Stockfish in real-time.
    Returns an SSE stream with progress updates and final results.
    """
    import json

    # 1. Fetch PGN text
    pgn_text = ""
    username = body.username

    if body.platform == "lichess":
        if not body.username:
            raise HTTPException(400, "Username required for Lichess")
        pgn_text = await _fetch_lichess_pgn(body.username, body.max_games)
    elif body.platform == "chess.com":
        if not body.username:
            raise HTTPException(400, "Username required for Chess.com")
        pgn_text = await _fetch_chesscom_pgn(body.username, body.max_games)
    elif body.platform == "pgn":
        if not body.pgn_text:
            raise HTTPException(400, "PGN text required")
        pgn_text = body.pgn_text
    else:
        raise HTTPException(400, f"Unknown platform: {body.platform}")

    if not pgn_text.strip():
        raise HTTPException(404, "No games found")

    # 2. Parse all games first to get total count
    parsed_games = _parse_all_pgn(pgn_text, username)
    if not parsed_games:
        raise HTTPException(404, "Could not parse any games from the PGN data")

    total = len(parsed_games)

    async def event_stream():
        settings = get_settings()
        results: list[GameAnalysisOut] = []

        # Send initial event with total count
        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        try:
            transport, engine = await chess.engine.popen_uci(settings.stockfish_path)

            for idx, (pgn_game, color_guess) in enumerate(parsed_games):
                # Analyze each game
                analysis = await _analyze_game(engine, pgn_game, color_guess, idx)
                results.append(analysis)

                # Send progress
                yield f"data: {json.dumps({'type': 'progress', 'completed': idx + 1, 'total': total, 'game_cpl': analysis.overall_cpl})}\n\n"

            await engine.quit()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # Compute aggregate stats
        all_cpls = [g.overall_cpl for g in results]
        overall_cpl = round(sum(all_cpls) / len(all_cpls), 1) if all_cpls else None

        wins = sum(1 for g in results if g.result == "win")
        win_rate = round((wins / total) * 100, 1) if total > 0 else None

        total_blunders = sum(g.blunders for g in results)
        total_moves = sum(len(g.moves) for g in results)
        blunder_rate = round((total_blunders / total_moves) * 100, 1) if total_moves > 0 else None

        response = AnonAnalysisResponse(
            username=username,
            platform=body.platform,
            total_games=total,
            games=[g.model_dump() for g in results],
            overall_cpl=overall_cpl,
            win_rate=win_rate,
            blunder_rate=blunder_rate,
        )

        yield f"data: {json.dumps({'type': 'complete', 'results': response.model_dump()})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


async def _fetch_lichess_pgn(username: str, max_games: int) -> str:
    url = f"https://lichess.org/api/games/user/{username}"
    params = {
        "max": min(max_games, 50),
        "pgnInBody": "true",
        "clocks": "true",
        "evals": "false",
        "opening": "true",
    }
    headers = {"Accept": "application/x-chess-pgn"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)

    if resp.status_code == 404:
        raise HTTPException(404, f"Lichess user '{username}' not found")
    if resp.status_code != 200:
        raise HTTPException(502, "Lichess API error")

    return resp.text


async def _fetch_chesscom_pgn(username: str, max_games: int) -> str:
    base_url = f"https://api.chess.com/pub/player/{username.lower()}"
    req_headers = {
        "User-Agent": "ChessAnalyzer/2.0 (chess analysis platform)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        profile_resp = await client.get(base_url, headers=req_headers)
        if profile_resp.status_code == 404:
            raise HTTPException(404, f"Chess.com user '{username}' not found")
        if profile_resp.status_code != 200:
            raise HTTPException(502, "Chess.com API error")

        archives_resp = await client.get(f"{base_url}/games/archives", headers=req_headers)
        if archives_resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch Chess.com archives")

        archives = archives_resp.json().get("archives", [])
        if not archives:
            return ""

        all_pgn_parts: list[str] = []
        total_fetched = 0

        for archive_url in reversed(archives):
            if total_fetched >= max_games:
                break
            month_resp = await client.get(archive_url, headers=req_headers)
            if month_resp.status_code != 200:
                continue
            month_games = month_resp.json().get("games", [])
            for g in reversed(month_games):
                if total_fetched >= max_games:
                    break
                pgn = g.get("pgn", "")
                if pgn:
                    all_pgn_parts.append(pgn)
                    total_fetched += 1

    return "\n\n".join(all_pgn_parts)


def _parse_all_pgn(pgn_text: str, username: str | None) -> list[tuple]:
    """Parse PGN text and return list of (pgn_game, color) tuples."""
    pgn_io = StringIO(pgn_text)
    games = []

    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        headers = game.headers
        white = headers.get("White", "")
        black = headers.get("Black", "")

        # Determine which color the user is playing
        color = "white"
        if username and username.lower() == black.lower():
            color = "black"

        games.append((game, color))

    return games


async def _analyze_game(
    engine, pgn_game, color: str, game_index: int
) -> GameAnalysisOut:
    """Analyze a single game with the Stockfish engine."""
    settings = get_settings()
    depth = min(settings.default_analysis_depth, 12)

    headers = pgn_game.headers
    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    result_raw = headers.get("Result", "*")

    # Determine result from player's perspective
    if result_raw == "1-0":
        result = "win" if color == "white" else "loss"
    elif result_raw == "0-1":
        result = "win" if color == "black" else "loss"
    else:
        result = "draw"

    board = pgn_game.board()
    move_evals = []
    total_cp_loss = 0
    phase_losses = {"opening": [], "middlegame": [], "endgame": []}
    blunders = 0
    mistakes = 0
    inaccuracies = 0
    best_moves_count = 0
    move_num = 0
    prev_score_cp = 0

    for move in pgn_game.mainline_moves():
        move_num += 1
        mv_color = "white" if board.turn == chess.WHITE else "black"
        san = board.san(move)
        board.push(move)

        info = await engine.analyse(board, chess.engine.Limit(depth=depth))

        score = info.get("score")
        score_cp = 0
        if score:
            pov = score.pov(chess.WHITE)
            if pov.is_mate():
                mate_val = pov.mate()
                score_cp = 10000 if (mate_val and mate_val > 0) else -10000
            else:
                score_cp = pov.score() or 0

        # CP loss
        if mv_color == "white":
            cp_loss = max(0, prev_score_cp - score_cp)
        else:
            cp_loss = max(0, score_cp - prev_score_cp)

        # Quality
        if cp_loss == 0:
            quality = "Best"
            best_moves_count += 1
        elif cp_loss <= 10:
            quality = "Excellent"
        elif cp_loss <= 25:
            quality = "Good"
        elif cp_loss <= 100:
            quality = "Inaccuracy"
            inaccuracies += 1
        elif cp_loss <= 300:
            quality = "Mistake"
            mistakes += 1
        else:
            quality = "Blunder"
            blunders += 1

        # Phase
        total_material = _count_material(board)
        if move_num <= 10:
            phase = "opening"
        elif total_material <= 13:
            phase = "endgame"
        else:
            phase = "middlegame"

        phase_losses[phase].append(cp_loss)
        total_cp_loss += cp_loss

        # Only add evals for the player's moves
        if mv_color == color:
            move_evals.append(MoveEvalOut(
                move_number=move_num,
                color=mv_color,
                san=san,
                cp_loss=cp_loss,
                phase=phase,
                move_quality=quality,
                eval_before=prev_score_cp,
                eval_after=score_cp,
            ))

        prev_score_cp = score_cp

    overall_cpl = round(total_cp_loss / move_num, 1) if move_num > 0 else 0

    return GameAnalysisOut(
        game_index=game_index,
        white=white,
        black=black,
        result=result,
        opening=headers.get("Opening", headers.get("ECO")),
        eco=headers.get("ECO"),
        date=headers.get("UTCDate", headers.get("Date")),
        time_control=headers.get("TimeControl"),
        color=color,
        overall_cpl=overall_cpl,
        phase_opening_cpl=_avg(phase_losses["opening"]),
        phase_middlegame_cpl=_avg(phase_losses["middlegame"]),
        phase_endgame_cpl=_avg(phase_losses["endgame"]),
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        best_moves=best_moves_count,
        moves=move_evals,
    )


def _count_material(board) -> int:
    values = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    total = 0
    for piece_type, value in values.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total += len(board.pieces(piece_type, chess.BLACK)) * value
    return total


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)
