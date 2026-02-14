#!/usr/bin/env python3
"""
Generate tactical puzzles from chess.com opponent games.

Fetches recent games, analyzes with Stockfish depth 14 + multipv=2,
enforces >=300cp gap (one-good-move rule), detects tactical themes,
produces multi-move solution lines, and inserts into puzzle DB.
"""

import asyncio
import hashlib
import json
import sys
import time
from io import StringIO
from pathlib import Path

# Ensure /app is on sys.path when running inside Docker
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, "/app")

import chess
import chess.engine
import chess.pgn
import requests
from sqlalchemy import text

from app.config import get_settings
from app.db.session import async_session

# ── Config ──
ANALYSIS_DEPTH = 14
MAX_GAMES_PER_USER = 20
MIN_CP_LOSS = 100
MAX_EVAL_BEFORE = 600
MIN_BEST_SECOND_GAP = 300
PIECE_VALUES = {1: 1, 2: 3, 3: 3, 4: 5, 5: 9, 6: 0}

USERNAMES = [
    "wflorez1982", "sodem", "Nikhil-e-don", "dark0n0", "Rebah23",
    "RebekahZx", "tec97log", "Prin_Sirimethanon", "sonyandrei",
    "comeback-only", "PARTH9270", "Juan-Dor", "MateuszLupus91",
    "tysonsaz", "TacoMan1111", "Gabeassc", "HotelMoscowW",
    "videopuppy", "Zayn005", "sumit992", "zeetterone", "Sufiyan-69",
    "Stofish", "breeze_004", "Pocticlav", "omaewamuuuuuuu",
    "fernanviltebosch", "kinginds", "Taron7", "Tony201000",
    "lalka7777", "alaa1eddine2", "novecento60", "NikoVK2021",
    "Riccardoe", "awake6am", "Quang101212", "gwarren3210",
    "marcello45", "GladiatorKJo", "TidoMaster", "antonstat",
    "victorGcronto92m", "paynie80", "Mih4s86", "Mrstekkie",
    "hakonskj", "Puuhan", "Kiril77776",
]


# ═════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════

def score_to_cp(score_obj, turn):
    if score_obj is None:
        return None, False, None
    pov = score_obj.pov(turn)
    if pov.is_mate():
        m = pov.mate() or 0
        return (10000 if m > 0 else -10000), True, m
    return (pov.score() or 0), False, None


def score_to_cp_white(score_obj):
    if score_obj is None:
        return 0, False, None
    pov = score_obj.pov(chess.WHITE)
    if pov.is_mate():
        m = pov.mate() or 0
        return (1500 if m > 0 else -1500), True, m
    return max(-1500, min(1500, pov.score() or 0)), False, None


import math

def win_probability(cp, is_mate=False, mate_in=None):
    if is_mate:
        if mate_in is not None:
            return 1.0 if mate_in > 0 else 0.0
        return 1.0 if cp > 0 else 0.0
    return 1.0 / (1.0 + math.pow(10, -cp / 400.0))


def detect_phase(board, move_num, cw, cb):
    mat = 0
    for pt, v in {2: 3, 3: 3, 4: 5, 5: 9}.items():
        mat += len(board.pieces(pt, chess.WHITE)) * v
        mat += len(board.pieces(pt, chess.BLACK)) * v
    has_q = bool(board.pieces(5, chess.WHITE) or board.pieces(5, chess.BLACK))
    if mat == 0 or mat <= 13:
        return "endgame"
    if not has_q and mat <= 20:
        return "endgame"
    if move_num >= 40 and mat <= 24:
        return "endgame"
    if move_num >= 50 and mat <= 30:
        return "endgame"
    if move_num <= 15 and mat > 26:
        return "opening"
    return "middlegame"


# ═════════════════════════════════════════════════════
# Tactic Detection
# ═════════════════════════════════════════════════════

def detect_fork(board, move):
    p = board.piece_at(move.from_square)
    if not p:
        return False
    b2 = board.copy()
    b2.push(move)
    opp = not board.turn
    attacked = 0
    for sq in chess.SQUARES:
        t = b2.piece_at(sq)
        if t and t.color == opp:
            val = PIECE_VALUES.get(t.piece_type, 0)
            if val >= 3 or t.piece_type == chess.KING:
                if b2.is_attacked_by(board.turn, sq):
                    attacked += 1
    return attacked >= 2


def detect_pin(board, move):
    b2 = board.copy()
    b2.push(move)
    opp = not board.turn
    king_sq = b2.king(opp)
    if king_sq is None:
        return False
    for sq in chess.SQUARES:
        p = b2.piece_at(sq)
        if p and p.color == opp and sq != king_sq:
            if b2.is_attacked_by(board.turn, sq):
                b3 = b2.copy()
                b3.remove_piece_at(sq)
                if b3.is_attacked_by(board.turn, king_sq):
                    return True
    return False


def detect_skewer(board, move):
    p = board.piece_at(move.from_square)
    if not p or p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    b2 = board.copy()
    b2.push(move)
    if not b2.is_check():
        return False
    opp = not board.turn
    king_sq = b2.king(opp)
    if king_sq is None:
        return False
    df = chess.square_file(move.to_square) - chess.square_file(king_sq)
    dr = chess.square_rank(move.to_square) - chess.square_rank(king_sq)
    if df != 0:
        df = df // abs(df)
    if dr != 0:
        dr = dr // abs(dr)
    sq = king_sq
    while True:
        f = chess.square_file(sq) + df
        r = chess.square_rank(sq) + dr
        if not (0 <= f <= 7 and 0 <= r <= 7):
            break
        sq = chess.square(f, r)
        behind = b2.piece_at(sq)
        if behind:
            if behind.color == opp and PIECE_VALUES.get(behind.piece_type, 0) >= 3:
                return True
            break
    return False


def detect_back_rank(board, move):
    b2 = board.copy()
    b2.push(move)
    if not b2.is_checkmate():
        return False
    opp = not board.turn
    king_sq = b2.king(opp)
    if king_sq is None:
        return False
    kr = chess.square_rank(king_sq)
    return (opp == chess.WHITE and kr == 0) or (opp == chess.BLACK and kr == 7)


def detect_discovered_attack(board, move):
    p = board.piece_at(move.from_square)
    if not p:
        return False
    b2 = board.copy()
    b2.push(move)
    opp = not board.turn
    for sq in chess.SQUARES:
        t = b2.piece_at(sq)
        if t and t.color == opp and PIECE_VALUES.get(t.piece_type, 0) >= 3:
            if b2.is_attacked_by(board.turn, sq) and not board.is_attacked_by(board.turn, sq):
                if sq != move.to_square:
                    return True
    return False


def detect_deflection(board, move):
    captured = board.piece_at(move.to_square)
    if not captured:
        return False
    opp = not board.turn
    if captured.color != opp:
        return False
    b2 = board.copy()
    b2.push(move)
    for sq in chess.SQUARES:
        t = b2.piece_at(sq)
        if t and t.color == opp and PIECE_VALUES.get(t.piece_type, 0) >= 3:
            was_def = board.is_attacked_by(opp, sq)
            now_def = b2.is_attacked_by(opp, sq)
            if was_def and not now_def and b2.is_attacked_by(board.turn, sq):
                return True
    return False


def detect_mate_threat(board, move):
    b2 = board.copy()
    b2.push(move)
    if b2.is_checkmate():
        return 1
    if b2.is_check():
        for resp in b2.legal_moves:
            b3 = b2.copy()
            b3.push(resp)
            for m2 in b3.legal_moves:
                b4 = b3.copy()
                b4.push(m2)
                if b4.is_checkmate():
                    return 2
    return None


PIECE_NAMES = {1: "pawn", 2: "knight", 3: "bishop", 4: "rook", 5: "queen", 6: "king"}


def get_themes(board, move, solution_line, fen):
    tags = []
    p = board.piece_at(move.from_square)

    if detect_fork(board, move):
        tags.append("fork")
    if detect_pin(board, move):
        tags.append("pin")
    if detect_skewer(board, move):
        tags.append("skewer")
    if detect_discovered_attack(board, move):
        tags.append("discovered_attack")
    if detect_back_rank(board, move):
        tags.append("back_rank")
    if detect_deflection(board, move):
        tags.append("deflection")
    if move.promotion is not None:
        tags.append("promotion")

    mate_n = detect_mate_threat(board, move)
    if mate_n == 1:
        tags.append("mate_in_1")
    elif mate_n is not None:
        tags.append("checkmate_pattern")

    captured = board.piece_at(move.to_square)
    b2 = board.copy()
    b2.push(move)
    if captured:
        cv = PIECE_VALUES.get(captured.piece_type, 0)
        mv = PIECE_VALUES.get(p.piece_type, 0) if p else 0
        if cv > mv:
            tags.append("winning_capture")

    if b2.is_check() and "mate_in_1" not in tags and "back_rank" not in tags:
        tags.append("check")

    if p and p.piece_type == chess.KING and len(board.piece_map()) <= 12:
        tags.append("king_activity")

    # Multi-move solution analysis
    if solution_line and len(solution_line) >= 3:
        try:
            b = chess.Board(fen)
            for i, uci in enumerate(solution_line[:6]):
                m = chess.Move.from_uci(uci)
                if m in b.legal_moves:
                    if i % 2 == 0:
                        if detect_fork(b, m) and "fork" not in tags:
                            tags.append("fork")
                        if b.piece_at(m.to_square) and "combination" not in tags:
                            tags.append("combination")
                    b.push(m)
                else:
                    break
            if b.is_checkmate() and "checkmate_pattern" not in tags and "mate_in_1" not in tags:
                tags.append("checkmate_pattern")
        except Exception:
            pass

    if p:
        pn = PIECE_NAMES.get(p.piece_type)
        if pn and pn not in tags:
            tags.append(pn)

    if not any(t in tags for t in [
        "fork", "pin", "skewer", "discovered_attack", "back_rank", "deflection",
        "promotion", "mate_in_1", "checkmate_pattern", "winning_capture",
        "check", "king_activity", "combination",
    ]):
        tags.append("positional")

    return tags


# ═════════════════════════════════════════════════════
# Chess.com Fetcher
# ═════════════════════════════════════════════════════

def fetch_games(username, max_games=20):
    headers = {"User-Agent": "ChessAnalyzer/1.0 (puzzle generation)"}
    games = []
    try:
        resp = requests.get(
            f"https://api.chess.com/pub/player/{username}/games/archives",
            headers=headers, timeout=10,
        )
        if resp.status_code != 200:
            print(f"  Warning: {username} archives {resp.status_code}")
            return []
        archives = resp.json().get("archives", [])
        if not archives:
            return []
        for url in reversed(archives[-3:]):
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code != 200:
                    continue
                for g in reversed(r.json().get("games", [])):
                    pgn_str = g.get("pgn")
                    if not pgn_str:
                        continue
                    tc = g.get("time_class", "")
                    if tc not in ("rapid", "blitz", "bullet", "daily"):
                        continue
                    game = chess.pgn.read_game(StringIO(pgn_str))
                    if game and list(game.mainline_moves()):
                        games.append((game, username))
                    if len(games) >= max_games:
                        return games
                time.sleep(0.3)
            except Exception as e:
                print(f"  Warning month: {e}")
        return games
    except Exception as e:
        print(f"  Warning fetch {username}: {e}")
        return []


# ═════════════════════════════════════════════════════
# Game Analysis → Puzzles
# ═════════════════════════════════════════════════════

async def analyze_game(game, username, engine, depth=14):
    puzzles = []
    board = game.board()
    prev_cp = 0
    prev_is_mate = False
    prev_mate_in = None
    cw = cb = False

    white_player = game.headers.get("White", "").lower()
    user_is_white = white_player == username.lower()
    moves = list(game.mainline_moves())
    if len(moves) < 10:
        return []

    for mi, move in enumerate(moves):
        mn = mi // 2 + 1
        is_w = mi % 2 == 0
        color = "white" if is_w else "black"
        is_player = (is_w and user_is_white) or (not is_w and not user_is_white)
        fen_before = board.fen()

        if board.is_castling(move):
            if color == "white":
                cw = True
            else:
                cb = True

        best_san = best_uci = None
        gap_cp = None
        is_only_legal = board.legal_moves.count() == 1

        if is_player:
            try:
                multi = await engine.analyse(
                    board, chess.engine.Limit(depth=depth),
                    multipv=2, info=chess.engine.INFO_ALL,
                )
                pv = multi[0].get("pv") if multi else None
                if pv and len(pv) > 0:
                    best_uci = pv[0].uci()
                    best_san = board.san(pv[0])
                if len(multi) >= 2:
                    s1 = multi[0].get("score")
                    s2 = multi[1].get("score")
                    if s1 and s2:
                        c1, _, _ = score_to_cp(s1, board.turn)
                        c2, _, _ = score_to_cp(s2, board.turn)
                        if c1 is not None and c2 is not None:
                            gap_cp = c1 - c2
            except Exception:
                pass

        san = board.san(move)
        board.push(move)

        try:
            info = await engine.analyse(board, chess.engine.Limit(depth=depth))
        except Exception:
            prev_cp = 0
            prev_is_mate = False
            prev_mate_in = None
            continue

        score_cp, is_mate, mate_in = score_to_cp_white(info.get("score"))

        if prev_is_mate and is_mate:
            cp_loss = 0
        elif color == "white":
            cp_loss = max(0, prev_cp - score_cp)
        else:
            cp_loss = max(0, score_cp - prev_cp)
        cp_loss = min(cp_loss, 800)

        phase = detect_phase(board, mn, cw, cb)

        if cp_loss >= 300:
            quality = "Blunder"
        elif cp_loss >= 100:
            quality = "Mistake"
        else:
            quality = "Good"

        if is_player and quality in ("Blunder", "Mistake") and best_san:
            # Enforce 300cp gap (one-good-move rule)
            if not is_only_legal:
                if gap_cp is None or gap_cp < MIN_BEST_SECOND_GAP:
                    prev_cp = score_cp
                    prev_is_mate = is_mate
                    prev_mate_in = mate_in
                    continue

            # Reject trivially winning positions
            if abs(prev_cp) >= MAX_EVAL_BEFORE:
                prev_cp = score_cp
                prev_is_mate = is_mate
                prev_mate_in = mate_in
                continue

            # Compute multi-move solution line
            sol_line = []
            try:
                sb = chess.Board(fen_before)
                for step in range(6):
                    si = await engine.analyse(sb, chess.engine.Limit(depth=depth))
                    sp = si.get("pv", [])
                    if not sp:
                        break
                    sol_line.append(sp[0].uci())
                    sb.push(sp[0])
                    if sb.is_game_over():
                        break
            except Exception:
                pass

            # Detect themes using the best move
            try:
                best_move_obj = chess.Move.from_uci(best_uci) if best_uci else None
                board_before = chess.Board(fen_before)
                if best_move_obj and best_move_obj in board_before.legal_moves:
                    themes = get_themes(board_before, best_move_obj, sol_line, fen_before)
                else:
                    themes = [quality.lower(), phase]
            except Exception:
                themes = [quality.lower(), phase]

            # Always include phase
            if phase not in themes:
                themes.append(phase)

            # Filter: require at least 1 real tactic tag
            real_tactics = [t for t in themes if t not in (
                "positional", "opening", "middlegame", "endgame",
                "blunder", "mistake", "missed_win",
                "pawn", "knight", "bishop", "rook", "queen", "king",
            )]
            if len(real_tactics) < 1:
                prev_cp = score_cp
                prev_is_mate = is_mate
                prev_mate_in = mate_in
                continue

            side = "white" if fen_before.split()[1] == "w" else "black"
            ptype = "blunder" if quality == "Blunder" else "mistake"
            pk = hashlib.md5(f"{fen_before}|{san}".encode()).hexdigest()

            puzzles.append({
                "puzzle_key": pk,
                "fen": fen_before,
                "side_to_move": side,
                "best_move_san": best_san,
                "best_move_uci": best_uci,
                "played_move_san": san,
                "eval_loss_cp": cp_loss,
                "phase": phase,
                "puzzle_type": ptype,
                "move_number": mn,
                "solution_line": sol_line,
                "themes": themes,
            })

        prev_cp = score_cp
        prev_is_mate = is_mate
        prev_mate_in = mate_in

    return puzzles


# ═════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════

async def main():
    settings = get_settings()
    transport, engine = await chess.engine.popen_uci(settings.stockfish_path)
    await engine.configure({"Threads": 2, "Hash": 256})

    total = 0
    skipped = 0
    errors = 0

    print(f"Processing {len(USERNAMES)} chess.com opponents...")
    print("=" * 60)

    for i, uname in enumerate(USERNAMES, 1):
        print(f"[{i}/{len(USERNAMES)}] {uname}")
        user_count = 0

        games = fetch_games(uname, MAX_GAMES_PER_USER)
        print(f"  Fetched {len(games)} games")

        for game, un in games:
            try:
                pzs = await analyze_game(game, un, engine, ANALYSIS_DEPTH)
                async with async_session() as db:
                    for pd in pzs:
                        ex = await db.execute(
                            text("SELECT 1 FROM puzzles WHERE puzzle_key = :pk"),
                            {"pk": pd["puzzle_key"]},
                        )
                        if ex.scalar():
                            skipped += 1
                            continue
                        await db.execute(
                            text("""INSERT INTO puzzles (
                                puzzle_key, fen, side_to_move, best_move_san, best_move_uci,
                                played_move_san, eval_loss_cp, phase, puzzle_type, difficulty,
                                move_number, solution_line, themes
                            ) VALUES (
                                :puzzle_key, :fen, :side_to_move, :best_move_san, :best_move_uci,
                                :played_move_san, :eval_loss_cp, :phase, :puzzle_type, 'standard',
                                :move_number, :solution_line, :themes
                            )"""),
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
                            },
                        )
                        user_count += 1
                        total += 1
                    await db.commit()
            except Exception as e:
                errors += 1
                if "rate" in str(e).lower() or "429" in str(e):
                    print(f"  Rate limited, waiting 5s...")
                    time.sleep(5)
                continue

        print(f"  -> {user_count} puzzles")
        time.sleep(1)

    await engine.quit()

    # Get final count + theme summary
    async with async_session() as db:
        r = await db.execute(text("SELECT COUNT(*) FROM puzzles"))
        final_count = r.scalar()

        # Theme breakdown of newly added puzzles
        r2 = await db.execute(text("""
            SELECT themes, solution_line, best_move_san, fen, side_to_move, puzzle_type, phase
            FROM puzzles
            ORDER BY id DESC
            LIMIT :lim
        """), {"lim": total if total > 0 else 1})
        rows = r2.fetchall()

    print()
    print("=" * 60)
    print(f"DONE!")
    print(f"  New puzzles inserted: {total}")
    print(f"  Duplicates skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total puzzles in DB: {final_count}")

    # Theme summary
    if rows:
        theme_counts = {}
        multi_move = 0
        one_move = 0
        for r in rows:
            themes = r[0] if isinstance(r[0], list) else json.loads(r[0] or "[]")
            sol = r[1] if isinstance(r[1], list) else json.loads(r[1] or "[]")
            if len(sol) > 1:
                multi_move += 1
            else:
                one_move += 1
            for t in themes:
                theme_counts[t] = theme_counts.get(t, 0) + 1
        print(f"\n  Multi-move puzzles: {multi_move}")
        print(f"  Single-move puzzles: {one_move}")
        print(f"\n  Theme breakdown:")
        for t, c in sorted(theme_counts.items(), key=lambda x: -x[1]):
            print(f"    {t}: {c}")


asyncio.run(main())
