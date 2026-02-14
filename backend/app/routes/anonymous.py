"""
Anonymous analysis routes – Allow unauthenticated users to fetch + analyze games.

Results are returned directly (no user account required).
The frontend stores them in memory and gates "Get Results" behind sign-in.
After sign-in, `/claim-results` persists the data into the user's account.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from io import StringIO
from typing import Optional

import chess
import chess.engine
import chess.pgn
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import get_settings
from app.db.models import Game, GameAnalysis, MoveEvaluation, OpeningRepertoire, Puzzle, User
from app.db.session import get_db
from app.analysis_core import (
    win_probability,
    move_accuracy,
    compute_game_accuracy,
    classify_move,
    detect_phase,
    count_material,
    generate_puzzle_data,
    compute_solution_line,
    extract_opening_name,
    avg,
    parse_clock_comment,
    classify_blunder_subtype,
)

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
    fen_before: Optional[str] = None
    best_move_san: Optional[str] = None
    best_move_uci: Optional[str] = None
    win_prob_before: Optional[float] = None
    win_prob_after: Optional[float] = None
    accuracy: Optional[float] = None
    time_remaining: Optional[float] = None
    blunder_subtype: Optional[str] = None


class PuzzleCandidateOut(BaseModel):
    puzzle_key: str
    fen: str
    side_to_move: str
    best_move_san: str
    best_move_uci: Optional[str] = None
    played_move_san: str
    eval_loss_cp: int
    phase: str
    puzzle_type: str
    difficulty: str
    move_number: int
    themes: list[str]


class ClaimPuzzleCandidateIn(BaseModel):
    puzzle_key: str
    fen: str
    side_to_move: str
    best_move_san: str
    best_move_uci: Optional[str] = None
    played_move_san: str
    eval_loss_cp: int
    phase: str
    puzzle_type: str
    difficulty: str
    move_number: int
    themes: list[str]


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
    accuracy: Optional[float] = None
    phase_opening_cpl: Optional[float]
    phase_middlegame_cpl: Optional[float]
    phase_endgame_cpl: Optional[float]
    blunders: int
    mistakes: int
    inaccuracies: int
    best_moves: int
    great_moves: int = 0
    brilliant_moves: int = 0
    missed_wins: int = 0
    average_move_time: Optional[float] = None
    time_trouble_blunders: int = 0
    moves: list[MoveEvalOut]
    puzzle_candidates: list[PuzzleCandidateOut] = []


class AnonAnalysisResponse(BaseModel):
    username: Optional[str]
    platform: str
    total_games: int
    games: list[GameAnalysisOut]
    overall_cpl: Optional[float]
    win_rate: Optional[float]
    blunder_rate: Optional[float]


class ClaimMoveIn(BaseModel):
    move_number: int
    color: str
    san: str
    cp_loss: int
    phase: Optional[str] = None
    move_quality: Optional[str] = None
    eval_before: Optional[int] = None
    eval_after: Optional[int] = None
    fen_before: Optional[str] = None
    best_move_san: Optional[str] = None
    best_move_uci: Optional[str] = None
    win_prob_before: Optional[float] = None
    win_prob_after: Optional[float] = None
    accuracy: Optional[float] = None
    time_remaining: Optional[float] = None
    blunder_subtype: Optional[str] = None
    puzzle_key: str
    fen: str
    side_to_move: str
    best_move_san: str
    best_move_uci: Optional[str] = None
    played_move_san: str
    eval_loss_cp: int
    phase: str
    puzzle_type: str
    difficulty: str
    move_number: int
    themes: list[str] = []


class ClaimGameIn(BaseModel):
    game_index: int
    white: str
    black: str
    result: str
    opening: Optional[str] = None
    eco: Optional[str] = None
    date: Optional[str] = None
    time_control: Optional[str] = None
    color: str
    overall_cpl: float
    accuracy: Optional[float] = None
    phase_opening_cpl: Optional[float] = None
    phase_middlegame_cpl: Optional[float] = None
    phase_endgame_cpl: Optional[float] = None
    blunders: int
    mistakes: int
    inaccuracies: int
    best_moves: int
    great_moves: int = 0
    brilliant_moves: int = 0
    missed_wins: int = 0
    average_move_time: Optional[float] = None
    time_trouble_blunders: int = 0
    moves: list[ClaimMoveIn]
    puzzle_candidates: list[ClaimPuzzleCandidateIn] = []


class ClaimResultsRequest(BaseModel):
    username: Optional[str] = None
    platform: str
    games: list[ClaimGameIn]


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
# Endpoint — Claim anonymous results into user account
# ═══════════════════════════════════════════════════════════


@router.post("/claim-results")
async def claim_anonymous_results(
    body: ClaimResultsRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Persist anonymous analysis results into the authenticated user's account.
    Creates Game + GameAnalysis + MoveEvaluation rows and updates OpeningRepertoire.
    Called by the frontend after the user signs up/in with cached results.
    """
    user_id = user.id
    platform = body.platform
    username = body.username

    # Update linked username on user profile if not set
    if platform == "lichess" and username and not user.lichess_username:
        user.lichess_username = username
    elif platform == "chess.com" and username and not user.chesscom_username:
        user.chesscom_username = username

    # Collect existing platform_game_ids to skip duplicates
    existing_ids_result = await db.execute(
        select(Game.platform_game_id).where(
            Game.user_id == user_id, Game.platform == platform
        )
    )
    existing_ids: set[str] = {
        row[0] for row in existing_ids_result.fetchall() if row[0]
    }

    imported = 0
    opening_stats: dict[tuple[str, str], dict] = {}  # (opening, color) → stats

    for g in body.games:
        # Parse date
        dt = datetime.utcnow()
        if g.date:
            try:
                dt = datetime.fromisoformat(g.date.replace(".", "-"))
            except (ValueError, AttributeError):
                pass

        # Generate a stable platform_game_id from game content
        game_hash = hashlib.md5(
            f"{g.white}|{g.black}|{g.date}|{g.result}|{g.color}|{g.game_index}".encode()
        ).hexdigest()[:16]

        if game_hash in existing_ids:
            continue

        # Determine result from player perspective (already done by anon analyze)
        result = g.result

        # Extract ELOs (not available in anon analysis)
        player_elo = None
        opponent_elo = None

        # g.moves now contains ALL moves (both players), so total count is direct
        moves_count = len(g.moves) if g.moves else 0

        # Reconstruct full PGN from the move SAN data
        result_pgn = _result_pgn(g.result, g.color)
        moves_pgn = f'[White "{g.white}"]\n[Black "{g.black}"]\n[Result "{result_pgn}"]\n'
        if g.opening:
            moves_pgn += f'[Opening "{g.opening}"]\n'
        if g.eco:
            moves_pgn += f'[ECO "{g.eco}"]\n'
        if g.date:
            moves_pgn += f'[Date "{g.date}"]\n'
        if g.time_control:
            moves_pgn += f'[TimeControl "{g.time_control}"]\n'
        moves_pgn += "\n"

        # Build the move text from SAN data
        move_text_parts: list[str] = []
        for m in g.moves:
            if m.color == "white":
                move_text_parts.append(f"{m.move_number}. {m.san}")
            else:
                move_text_parts.append(m.san)
        if move_text_parts:
            moves_pgn += " ".join(move_text_parts) + f" {result_pgn}\n"

        game_row = Game(
            user_id=user_id,
            platform=platform,
            platform_game_id=game_hash,
            date=dt,
            color=g.color,
            result=result,
            white_player=g.white or None,
            black_player=g.black or None,
            opening_name=g.opening,
            eco_code=g.eco,
            time_control=g.time_control,
            player_elo=player_elo,
            opponent_elo=opponent_elo,
            moves_count=moves_count,
            moves_pgn=moves_pgn,
        )

        try:
            db.add(game_row)
            await db.flush()  # get game_row.id
        except Exception:
            await db.rollback()
            continue

        # Create GameAnalysis row
        analysis_row = GameAnalysis(
            game_id=game_row.id,
            overall_cpl=g.overall_cpl,
            accuracy=g.accuracy,
            phase_opening_cpl=g.phase_opening_cpl,
            phase_middlegame_cpl=g.phase_middlegame_cpl,
            phase_endgame_cpl=g.phase_endgame_cpl,
            blunders_count=g.blunders,
            mistakes_count=g.mistakes,
            inaccuracies_count=g.inaccuracies,
            best_moves_count=g.best_moves,
            great_moves_count=g.great_moves,
            brilliant_moves_count=g.brilliant_moves,
            missed_wins_count=g.missed_wins,
            average_move_time=g.average_move_time,
            time_trouble_blunders=g.time_trouble_blunders,
            analysis_depth=12,
        )
        db.add(analysis_row)

        # Create MoveEvaluation rows
        for m in g.moves:
            move_row = MoveEvaluation(
                game_id=game_row.id,
                move_number=m.move_number,
                color=m.color,
                san=m.san,
                cp_loss=m.cp_loss,
                phase=m.phase,
                move_quality=m.move_quality,
                eval_before=m.eval_before,
                eval_after=m.eval_after,
                fen_before=m.fen_before,
                best_move_san=m.best_move_san,
                best_move_uci=m.best_move_uci,
                win_prob_before=m.win_prob_before,
                win_prob_after=m.win_prob_after,
                accuracy=m.accuracy,
                time_remaining=m.time_remaining,
                blunder_subtype=m.blunder_subtype,
            )
            db.add(move_row)

        # ── Save pre-generated puzzle candidates ──
        for pc in g.puzzle_candidates:
            # Skip duplicates silently
            existing_puzzle = await db.execute(
                select(Puzzle).where(Puzzle.puzzle_key == pc.puzzle_key)
            )
            if existing_puzzle.scalar_one_or_none():
                continue

            puzzle_row = Puzzle(
                puzzle_key=pc.puzzle_key,
                source_game_id=game_row.id,
                source_user_id=user_id,
                fen=pc.fen,
                side_to_move=pc.side_to_move,
                best_move_san=pc.best_move_san,
                best_move_uci=pc.best_move_uci,
                played_move_san=pc.played_move_san,
                eval_loss_cp=pc.eval_loss_cp,
                phase=pc.phase,
                puzzle_type=pc.puzzle_type,
                difficulty=pc.difficulty,
                move_number=pc.move_number,
                themes=pc.themes,
            )
            db.add(puzzle_row)

        existing_ids.add(game_hash)
        imported += 1

        # Accumulate opening stats
        if g.opening:
            key = (g.opening, g.color)
            if key not in opening_stats:
                opening_stats[key] = {
                    "eco": g.eco,
                    "games": 0,
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                    "cpl_sum": 0.0,
                    "cpl_count": 0,
                }
            stats = opening_stats[key]
            stats["games"] += 1
            if result == "win":
                stats["wins"] += 1
            elif result == "draw":
                stats["draws"] += 1
            else:
                stats["losses"] += 1
            stats["cpl_sum"] += g.overall_cpl
            stats["cpl_count"] += 1

    # Update OpeningRepertoire
    for (opening_name, color), stats in opening_stats.items():
        existing_q = await db.execute(
            select(OpeningRepertoire).where(
                OpeningRepertoire.user_id == user_id,
                OpeningRepertoire.opening_name == opening_name,
                OpeningRepertoire.color == color,
            )
        )
        existing_row = existing_q.scalar_one_or_none()

        if existing_row:
            existing_row.games_played += stats["games"]
            existing_row.games_won += stats["wins"]
            existing_row.games_drawn += stats["draws"]
            existing_row.games_lost += stats["losses"]
            total_cpl_games = (existing_row.games_played - stats["games"])
            if existing_row.average_cpl and total_cpl_games > 0:
                old_total = existing_row.average_cpl * total_cpl_games
                existing_row.average_cpl = round(
                    (old_total + stats["cpl_sum"]) / existing_row.games_played, 2
                )
            else:
                existing_row.average_cpl = round(stats["cpl_sum"] / stats["cpl_count"], 2) if stats["cpl_count"] else None
        else:
            new_row = OpeningRepertoire(
                user_id=user_id,
                opening_name=opening_name,
                eco_code=stats["eco"],
                color=color,
                games_played=stats["games"],
                games_won=stats["wins"],
                games_drawn=stats["draws"],
                games_lost=stats["losses"],
                average_cpl=round(stats["cpl_sum"] / stats["cpl_count"], 2) if stats["cpl_count"] else None,
            )
            db.add(new_row)

    await db.commit()

    return {"imported": imported, "total_submitted": len(body.games)}


def _result_pgn(result: str, color: str) -> str:
    """Convert player-perspective result back to PGN result string."""
    if result == "win":
        return "1-0" if color == "white" else "0-1"
    elif result == "loss":
        return "0-1" if color == "white" else "1-0"
    return "1/2-1/2"


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

    # Extract ELO from PGN headers for ELO-relative classification
    try:
        white_elo = int(headers.get("WhiteElo", 0)) or None
    except (ValueError, TypeError):
        white_elo = None
    try:
        black_elo = int(headers.get("BlackElo", 0)) or None
    except (ValueError, TypeError):
        black_elo = None
    player_elo = white_elo if color == "white" else black_elo

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
    player_accuracies = []
    phase_losses = {"opening": [], "middlegame": [], "endgame": []}
    blunders = 0
    mistakes = 0
    inaccuracies = 0
    best_moves_count = 0
    great_moves_count = 0
    brilliant_moves_count = 0
    missed_wins_count = 0
    player_move_count = 0
    total_move_count = 0
    move_num = 0
    prev_score_cp = 0
    prev_is_mate = False
    prev_mate_in = None
    castled_white = False
    castled_black = False
    puzzle_candidates: list[dict] = []

    prev_clock: float | None = None
    move_times: list[float] = []
    time_trouble_blunders_count = 0

    for node in pgn_game.mainline():
        move = node.move
        move_num += 1
        mv_color = "white" if board.turn == chess.WHITE else "black"
        san = board.san(move)
        fen_before = board.fen()
        is_player_move = (mv_color == color)

        # Parse clock annotation
        clock_remaining = parse_clock_comment(node.comment) if node.comment else None
        time_remaining_val = clock_remaining

        # Track castling
        if board.is_castling(move):
            if mv_color == "white":
                castled_white = True
            else:
                castled_black = True

        # Pre-move engine query for player moves
        best_move_san = None
        best_move_uci = None
        best_move_obj = None
        best_second_gap_cp = None
        is_only_legal = (board.legal_moves.count() == 1)

        if is_player_move:
            multi_info = await engine.analyse(
                board, chess.engine.Limit(depth=depth),
                multipv=2, info=chess.engine.INFO_ALL
            )
            pre_info = multi_info[0] if multi_info else {}
            pv = pre_info.get("pv")
            if pv and len(pv) > 0:
                best_move_obj = pv[0]
                best_move_uci = pv[0].uci()
                best_move_san = board.san(pv[0])

            # Compute gap between best and 2nd-best move
            # for puzzle quality filtering
            if len(multi_info) >= 2:
                s1 = multi_info[0].get("score")
                s2 = multi_info[1].get("score")
                if s1 and s2:
                    pov1 = s1.pov(board.turn)
                    pov2 = s2.pov(board.turn)
                    cp1 = 10000 if pov1.is_mate() and (pov1.mate() or 0) > 0 else (-10000 if pov1.is_mate() else (pov1.score() or 0))
                    cp2 = 10000 if pov2.is_mate() and (pov2.mate() or 0) > 0 else (-10000 if pov2.is_mate() else (pov2.score() or 0))
                    best_second_gap_cp = cp1 - cp2

        board.push(move)

        info = await engine.analyse(board, chess.engine.Limit(depth=depth))

        score = info.get("score")
        score_cp = 0
        is_mate = False
        mate_in = None
        if score:
            pov = score.pov(chess.WHITE)
            if pov.is_mate():
                is_mate = True
                mate_in = pov.mate()
                score_cp = 1500 if (mate_in and mate_in > 0) else -1500
            else:
                score_cp = max(-1500, min(1500, pov.score() or 0))

        # CP loss
        if prev_is_mate and is_mate:
            cp_loss = 0
        elif mv_color == "white":
            cp_loss = max(0, prev_score_cp - score_cp)
        else:
            cp_loss = max(0, score_cp - prev_score_cp)
        cp_loss = min(cp_loss, 800)

        # Win probability
        wp_before = win_probability(prev_score_cp, prev_is_mate, prev_mate_in)
        wp_after = win_probability(score_cp, is_mate, mate_in)

        # Per-move accuracy
        mv_accuracy = move_accuracy(wp_before, wp_after, mv_color)

        # Phase
        phase = detect_phase(board, move_num, castled_white, castled_black)

        # Classification
        if is_player_move:
            board.pop()
            quality = classify_move(
                cp_loss=cp_loss,
                win_prob_before=wp_before,
                win_prob_after=wp_after,
                color=mv_color,
                board_before=board,
                move=move,
                best_move=best_move_obj,
                is_only_legal=is_only_legal,
                eval_before_cp=prev_score_cp,
                eval_after_cp=score_cp,
                is_mate_before=prev_is_mate,
                is_mate_after=is_mate,
                mate_before=prev_mate_in,
                mate_after=mate_in,
                player_elo=player_elo,
            )
            board.push(move)
        else:
            if cp_loss == 0:
                quality = "Best"
            elif cp_loss <= 10:
                quality = "Excellent"
            elif cp_loss <= 25:
                quality = "Good"
            elif cp_loss <= 100:
                quality = "Inaccuracy"
            elif cp_loss <= 300:
                quality = "Mistake"
            else:
                quality = "Blunder"

        # Aggregate metrics for player's moves
        blunder_sub = None
        if is_player_move:
            player_move_count += 1
            player_accuracies.append(mv_accuracy)
            phase_losses[phase].append(cp_loss)
            total_cp_loss += cp_loss

            if quality == "Best":
                best_moves_count += 1
            elif quality == "Great":
                great_moves_count += 1
            elif quality == "Brilliant":
                brilliant_moves_count += 1
            elif quality == "Missed Win":
                missed_wins_count += 1
            elif quality == "Inaccuracy":
                inaccuracies += 1
            elif quality == "Mistake":
                mistakes += 1
            elif quality == "Blunder":
                blunders += 1

            # ── Blunder subtype classification ──
            blunder_sub = None
            if quality == "Blunder":
                board.pop()  # undo for classification context
                blunder_sub = classify_blunder_subtype(board, move, best_move_obj, phase)
                board.push(move)  # re-push
                if time_remaining_val is not None and time_remaining_val < 30:
                    time_trouble_blunders_count += 1

            # ── Track move time for player moves ──
            if clock_remaining is not None and prev_clock is not None:
                mt = prev_clock - clock_remaining
                if mt > 0:
                    move_times.append(mt)

            if is_player_move and clock_remaining is not None:
                prev_clock = clock_remaining

            # Collect puzzle candidates (filtered by quality)
            puzzle_data = generate_puzzle_data(
                fen_before=fen_before,
                san=san,
                best_move_san=best_move_san,
                best_move_uci=best_move_uci,
                cp_loss=cp_loss,
                phase=phase,
                move_quality=quality,
                move_number=move_num,
                best_second_gap_cp=best_second_gap_cp,
                eval_before_cp=prev_score_cp,
            )
            if puzzle_data:
                # Compute multi-move solution line
                sol_line = await compute_solution_line(
                    fen_before, engine, depth=depth, max_moves=6
                )
                puzzle_data["solution_line"] = sol_line
                puzzle_candidates.append(puzzle_data)

        move_evals.append(MoveEvalOut(
            move_number=move_num,
            color=mv_color,
            san=san,
            cp_loss=cp_loss,
            phase=phase,
            move_quality=quality,
            eval_before=prev_score_cp,
            eval_after=score_cp,
            fen_before=fen_before,
            best_move_san=best_move_san if is_player_move else None,
            best_move_uci=best_move_uci if is_player_move else None,
            win_prob_before=round(wp_before, 4),
            win_prob_after=round(wp_after, 4),
            accuracy=round(mv_accuracy, 1),
            time_remaining=time_remaining_val,
            blunder_subtype=blunder_sub if is_player_move else None,
        ))

        prev_score_cp = score_cp
        prev_is_mate = is_mate
        prev_mate_in = mate_in
        total_move_count += 1

    overall_cpl = round(total_cp_loss / player_move_count, 1) if player_move_count > 0 else 0
    game_acc = compute_game_accuracy(player_accuracies)

    return GameAnalysisOut(
        game_index=game_index,
        white=white,
        black=black,
        result=result,
        opening=extract_opening_name(headers),
        eco=headers.get("ECO"),
        date=headers.get("UTCDate", headers.get("Date")),
        time_control=headers.get("TimeControl"),
        color=color,
        overall_cpl=overall_cpl,
        accuracy=game_acc,
        phase_opening_cpl=avg(phase_losses["opening"]),
        phase_middlegame_cpl=avg(phase_losses["middlegame"]),
        phase_endgame_cpl=avg(phase_losses["endgame"]),
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        best_moves=best_moves_count,
        great_moves=great_moves_count,
        brilliant_moves=brilliant_moves_count,
        missed_wins=missed_wins_count,
        average_move_time=round(sum(move_times) / len(move_times), 1) if move_times else None,
        time_trouble_blunders=time_trouble_blunders_count,
        moves=move_evals,
        puzzle_candidates=[PuzzleCandidateOut(**p) for p in puzzle_candidates],
    )


def _avg(lst: list) -> float | None:
    return avg(lst)
