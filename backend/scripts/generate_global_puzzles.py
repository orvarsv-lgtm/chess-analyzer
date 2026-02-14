#!/usr/bin/env python3
"""
Generate high-quality tactical puzzles from chess.com games.

Fetches recent games from a list of chess.com usernames, analyzes with Stockfish,
extracts puzzle candidates, and inserts them into the database with tactic tags.

Usage:
    python generate_global_puzzles.py [--max-games-per-user 20] [--depth 14]

Requirements:
    - Stockfish installed (path configured below)
    - DATABASE_URL environment variable set
    - python-chess, requests, sqlalchemy[asyncio], asyncpg
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import requests
from io import StringIO

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ── Config ──
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/bin/stockfish")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ANALYSIS_DEPTH = 14
MAX_GAMES_PER_USER = 20
MIN_CP_LOSS = 100          # Minimum centipawn loss for a puzzle candidate
MAX_EVAL_BEFORE = 600      # Don't generate from already-won positions
MIN_BEST_SECOND_GAP = 300  # Only-one-good-move filter
MIN_TACTIC_TAGS = 1        # Require at least 1 real tactic (not just 'positional')

CHESS_COM_USERNAMES = [
    "5alidibnolwalid", "AliAhmedHabib", "theDave_Chess", "MasterChessLSH",
    "sidjones", "zaneti62", "iz_amine", "DayalVishal7", "AFiroud", "hsgEndy",
    "raulpecomartin3z", "drsebastian1", "1karka", "NicolasCarmona23",
    "dino18saur", "nitishajoshieuh", "GMObie", "Martinmogger", "Lorenz725",
    "Cnyr96", "INSINUAT", "Yohoni19", "djolek91", "thicc-man69", "Bulmer07",
    "Rahul_goday", "cicciosca1", "henkibett", "Lemur012", "avrgplayerreal",
    "Stankovski_Filip", "KiyotakaWTRH", "Chess_Player3099", "KingSchmebulock",
    "mc0657", "SiggiTheIceman", "Muhib56", "Bujar123456-5", "AlexChitpasong",
    "orthencia", "Lehoanganh13", "netohilario", "Sywio",
]

# Import analysis functions
from app.analysis_core import (
    detect_phase,
    win_probability,
    move_accuracy,
    classify_move,
    generate_puzzle_data,
    detect_puzzle_tactics,
    avg,
)


def fetch_chesscom_games(username: str, max_games: int = 20) -> list[chess.pgn.Game]:
    """Fetch recent games from chess.com API."""
    headers = {"User-Agent": "ChessAnalyzer/1.0 (puzzle generation)"}
    games = []

    try:
        # Get archives list
        archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
        resp = requests.get(archives_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"  ⚠ Could not fetch archives for {username}: {resp.status_code}")
            return []

        archives = resp.json().get("archives", [])
        if not archives:
            return []

        # Get most recent month(s)
        for archive_url in reversed(archives[-3:]):  # Last 3 months
            try:
                r = requests.get(archive_url, headers=headers, timeout=15)
                if r.status_code != 200:
                    continue
                month_games = r.json().get("games", [])

                for g in reversed(month_games):  # Most recent first
                    pgn_str = g.get("pgn")
                    if not pgn_str:
                        continue
                    # Only standard/rapid/blitz
                    time_class = g.get("time_class", "")
                    if time_class not in ("rapid", "blitz", "bullet", "daily"):
                        continue

                    game = chess.pgn.read_game(StringIO(pgn_str))
                    if game and game.mainline_moves():
                        games.append((game, username))

                    if len(games) >= max_games:
                        return games

                time.sleep(0.3)  # Rate limiting
            except Exception as e:
                print(f"  ⚠ Error fetching month: {e}")
                continue

    except Exception as e:
        print(f"  ⚠ Error fetching games for {username}: {e}")

    return games


async def analyze_game_for_puzzles(
    game: chess.pgn.Game,
    username: str,
    engine: chess.engine.UciProtocol,
    depth: int = 14,
) -> list[dict]:
    """Analyze a single game and extract puzzle candidates."""
    puzzles = []
    board = game.board()
    prev_score_cp = 0
    prev_is_mate = False
    prev_mate_in = None
    castled_white = False
    castled_black = False

    # Determine which color the user played
    white_player = game.headers.get("White", "").lower()
    user_is_white = white_player == username.lower()

    moves = list(game.mainline_moves())
    if len(moves) < 10:
        return []  # Skip very short games

    for move_idx, move in enumerate(moves):
        move_num = move_idx // 2 + 1
        is_white = move_idx % 2 == 0
        mv_color = "white" if is_white else "black"
        is_player_move = (is_white and user_is_white) or (not is_white and not user_is_white)

        fen_before = board.fen()

        if board.is_castling(move):
            if mv_color == "white":
                castled_white = True
            else:
                castled_black = True

        # Only analyze player moves for puzzle generation
        best_move_san = None
        best_move_uci = None
        best_second_gap_cp = None

        if is_player_move:
            try:
                multi_info = await engine.analyse(
                    board, chess.engine.Limit(depth=depth),
                    multipv=2, info=chess.engine.INFO_ALL
                )
                pre_info = multi_info[0] if multi_info else {}
                pv = pre_info.get("pv")
                if pv and len(pv) > 0:
                    best_move_uci = pv[0].uci()
                    best_move_san = board.san(pv[0])

                if len(multi_info) >= 2:
                    s1 = multi_info[0].get("score")
                    s2 = multi_info[1].get("score")
                    if s1 and s2:
                        pov1 = s1.pov(board.turn)
                        pov2 = s2.pov(board.turn)
                        cp1 = 10000 if pov1.is_mate() and (pov1.mate() or 0) > 0 else (-10000 if pov1.is_mate() else (pov1.score() or 0))
                        cp2 = 10000 if pov2.is_mate() and (pov2.mate() or 0) > 0 else (-10000 if pov2.is_mate() else (pov2.score() or 0))
                        best_second_gap_cp = cp1 - cp2
            except Exception:
                pass

        san = board.san(move)
        board.push(move)

        try:
            info = await engine.analyse(board, chess.engine.Limit(depth=depth))
        except Exception:
            continue

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

        phase = detect_phase(board, move_num, castled_white, castled_black)

        # Classify move quality
        wp_before = win_probability(prev_score_cp, prev_is_mate, prev_mate_in)
        wp_after = win_probability(score_cp, is_mate, mate_in)

        if cp_loss >= 300:
            quality = "Blunder"
        elif cp_loss >= 100:
            quality = "Mistake"
        elif cp_loss == 0 and not is_mate:
            quality = "Best"
        else:
            quality = "Good"

        # Generate puzzle data
        if is_player_move and quality in ("Blunder", "Mistake"):
            # Compute solution line
            sol_line = []
            try:
                sol_board = chess.Board(fen_before)
                for step in range(6):
                    sol_info = await engine.analyse(
                        sol_board, chess.engine.Limit(depth=depth)
                    )
                    sol_pv = sol_info.get("pv", [])
                    if not sol_pv:
                        break
                    sol_line.append(sol_pv[0].uci())
                    sol_board.push(sol_pv[0])
            except Exception:
                pass

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
                solution_line=sol_line,
            )

            if puzzle_data:
                puzzle_data["solution_line"] = sol_line

                # Quality check: must have real tactic tags
                tactic_themes = [t for t in puzzle_data.get("themes", [])
                                if t not in ("positional", "opening", "middlegame", "endgame",
                                           "blunder", "mistake", "missed_win")]
                if len(tactic_themes) >= MIN_TACTIC_TAGS:
                    puzzles.append(puzzle_data)

        prev_score_cp = score_cp
        prev_is_mate = is_mate
        prev_mate_in = mate_in

    return puzzles


async def main():
    if not DATABASE_URL:
        print("❌ DATABASE_URL not set. Export it first.")
        sys.exit(1)

    # Convert postgres:// to postgresql+asyncpg://
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine_db = create_async_engine(db_url)
    async_session = sessionmaker(engine_db, class_=AsyncSession, expire_on_commit=False)

    # Start Stockfish
    print(f"🔧 Starting Stockfish at {STOCKFISH_PATH}...")
    transport, stockfish = await chess.engine.popen_uci(STOCKFISH_PATH)
    await stockfish.configure({"Threads": 2, "Hash": 256})

    total_puzzles = 0
    total_skipped = 0
    total_errors = 0

    print(f"\n📊 Processing {len(CHESS_COM_USERNAMES)} chess.com accounts...")
    print("=" * 60)

    for i, username in enumerate(CHESS_COM_USERNAMES, 1):
        print(f"\n[{i}/{len(CHESS_COM_USERNAMES)}] 🎯 {username}")
        user_puzzles = 0

        games_with_user = fetch_chesscom_games(username, max_games=MAX_GAMES_PER_USER)
        print(f"  📥 Fetched {len(games_with_user)} games")

        for game, uname in games_with_user:
            try:
                puzzles = await analyze_game_for_puzzles(game, uname, stockfish, depth=ANALYSIS_DEPTH)

                async with async_session() as db:
                    for pd in puzzles:
                        # Check for duplicates
                        existing = await db.execute(
                            text("SELECT 1 FROM puzzles WHERE puzzle_key = :pk"),
                            {"pk": pd["puzzle_key"]}
                        )
                        if existing.scalar():
                            total_skipped += 1
                            continue

                        # Insert puzzle
                        await db.execute(
                            text("""
                                INSERT INTO puzzles (
                                    puzzle_key, fen, side_to_move, best_move_san, best_move_uci,
                                    played_move_san, eval_loss_cp, phase, puzzle_type, difficulty,
                                    move_number, solution_line, themes
                                ) VALUES (
                                    :puzzle_key, :fen, :side_to_move, :best_move_san, :best_move_uci,
                                    :played_move_san, :eval_loss_cp, :phase, :puzzle_type, 'standard',
                                    :move_number, :solution_line, :themes
                                )
                            """),
                            {
                                "puzzle_key": pd["puzzle_key"],
                                "fen": pd["fen"],
                                "side_to_move": pd["side_to_move"],
                                "best_move_san": pd["best_move_san"],
                                "best_move_uci": pd.get("best_move_uci"),
                                "played_move_san": pd.get("played_move_san"),
                                "eval_loss_cp": pd["eval_loss_cp"],
                                "phase": pd["phase"],
                                "puzzle_type": pd["puzzle_type"],
                                "move_number": pd.get("move_number"),
                                "solution_line": json.dumps(pd.get("solution_line", [])),
                                "themes": json.dumps(pd.get("themes", [])),
                            }
                        )
                        user_puzzles += 1
                        total_puzzles += 1

                    await db.commit()

            except Exception as e:
                total_errors += 1
                if "rate" in str(e).lower() or "429" in str(e):
                    print(f"  ⚠ Rate limited, waiting 5s...")
                    time.sleep(5)
                continue

        print(f"  ✅ Generated {user_puzzles} puzzles from {username}")
        time.sleep(1)  # Rate limiting between users

    await stockfish.quit()
    await engine_db.dispose()

    print("\n" + "=" * 60)
    print(f"🎉 DONE!")
    print(f"   Total puzzles generated: {total_puzzles}")
    print(f"   Duplicates skipped: {total_skipped}")
    print(f"   Errors: {total_errors}")


if __name__ == "__main__":
    asyncio.run(main())
