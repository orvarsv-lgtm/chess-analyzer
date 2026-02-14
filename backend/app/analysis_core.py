"""
Shared analysis core – win probability, move classification, phase detection,
puzzle generation.

Used by both analysis.py (authenticated) and anonymous.py (unauthenticated).
Implements chess.com-style accuracy and move classification.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

import chess


# ═══════════════════════════════════════════════════════════
# Opening Name Extraction
# ═══════════════════════════════════════════════════════════


def extract_opening_name(headers: dict) -> str | None:
    """
    Extract a human-readable opening name from PGN headers.
    Handles both Lichess (Opening header) and Chess.com (ECOUrl header).
    Falls back to ECO code if nothing better is available.
    """
    # Lichess and some PGNs include an explicit Opening header
    opening = headers.get("Opening")
    if opening:
        return opening

    # Chess.com uses ECOUrl, e.g.
    # https://www.chess.com/openings/Queens-Gambit-Accepted-Central-Variation-Greco-Variation-4.a4
    eco_url = headers.get("ECOUrl", "")
    if "/openings/" in eco_url:
        slug = eco_url.split("/openings/")[-1]
        # Remove trailing move annotations like "-4.a4", "-3...d5"
        slug = re.sub(r'-\d+\.+.*$', '', slug)
        # Convert hyphens to spaces
        name = slug.replace("-", " ").strip()
        if name:
            return name

    # Last resort: ECO code
    return headers.get("ECO", None)


# ═══════════════════════════════════════════════════════════
# Win Probability (chess.com-style logistic model)
# ═══════════════════════════════════════════════════════════


def win_probability(cp: int, is_mate: bool = False, mate_in: int | None = None) -> float:
    """
    Convert a centipawn evaluation (from White's POV) to a win probability [0, 1].
    Uses the standard logistic model: 1 / (1 + 10^(-cp/400)).
    For mate scores, returns ~1.0 or ~0.0.
    """
    if is_mate:
        if mate_in is not None:
            return 1.0 if mate_in > 0 else 0.0
        # Fallback: use the capped cp value
        return 1.0 if cp > 0 else 0.0
    return 1.0 / (1.0 + math.pow(10, -cp / 400.0))


def move_accuracy(win_prob_before: float, win_prob_after: float, color: str) -> float:
    """
    Compute per-move accuracy from win probability change.
    Chess.com uses: accuracy = 103.1668 * exp(-0.04354 * (win%_loss * 100)) - 3.1668
    where win%_loss is the drop in win% from the player's perspective.

    Returns accuracy clamped to [0, 100].
    """
    if color == "white":
        win_pct_loss = max(0, (win_prob_before - win_prob_after) * 100)
    else:
        # From Black's perspective, a win prob increase for White is bad
        win_pct_loss = max(0, (win_prob_after - win_prob_before) * 100)

    # Chess.com-style exponential decay on win% loss
    # Coefficient softened from -0.04354 to -0.03 for more generous accuracy
    acc = 103.1668 * math.exp(-0.03 * win_pct_loss) - 3.1668
    return max(0.0, min(100.0, acc))


def compute_game_accuracy(move_accuracies: list[float]) -> float:
    """Average per-move accuracy for the game, rounded to 1 decimal."""
    if not move_accuracies:
        return 0.0
    return round(sum(move_accuracies) / len(move_accuracies), 1)


# ═══════════════════════════════════════════════════════════
# Move Classification (chess.com-style)
# ═══════════════════════════════════════════════════════════


# ── ELO-relative classification thresholds (chess.com-style) ──
# Each band defines (excellent, good, inaccuracy, mistake) max wp_loss_pct.
# Anything above the mistake threshold is a Blunder.
ELO_THRESHOLDS = {
    "beginner":     {"excellent": 3,   "good": 8,  "inaccuracy": 15, "mistake": 25},   # <1200
    "intermediate": {"excellent": 2,   "good": 5,  "inaccuracy": 10, "mistake": 20},   # 1200-1800
    "advanced":     {"excellent": 1.5, "good": 4,  "inaccuracy": 7,  "mistake": 15},   # 1800+
}


def _get_elo_band(player_elo: int | None) -> dict:
    """Return classification thresholds for the player's ELO band."""
    if player_elo is None or player_elo < 1200:
        return ELO_THRESHOLDS["beginner"]
    elif player_elo < 1800:
        return ELO_THRESHOLDS["intermediate"]
    else:
        return ELO_THRESHOLDS["advanced"]


def classify_move(
    *,
    cp_loss: int,
    win_prob_before: float,
    win_prob_after: float,
    color: str,
    board_before: chess.Board,
    move: chess.Move,
    best_move: chess.Move | None,
    is_only_legal: bool,
    eval_before_cp: int,
    eval_after_cp: int,
    is_mate_before: bool,
    is_mate_after: bool,
    mate_before: int | None,
    mate_after: int | None,
    player_elo: int | None = None,
) -> str:
    """
    Classify a move using chess.com-style categories.
    Thresholds are ELO-relative: lower-rated players get wider bands.

    Returns one of:
        Brilliant, Great, Best, Excellent, Good,
        Inaccuracy, Mistake, Blunder, Missed Win, Forced
    """
    # ── Forced: only one legal move ──
    if is_only_legal:
        return "Forced"

    # ── Win probability loss from player's perspective ──
    if color == "white":
        wp_loss = win_prob_before - win_prob_after  # positive = player lost winning chances
    else:
        wp_loss = win_prob_after - win_prob_before  # from Black POV

    # ── Missed Win: had a winning advantage but played a move that's no longer winning ──
    # Winning = win_prob > 0.75 from player's POV; after move, it's <= 0.55
    player_wp_before = win_prob_before if color == "white" else (1 - win_prob_before)
    player_wp_after = win_prob_after if color == "white" else (1 - win_prob_after)

    if player_wp_before >= 0.75 and player_wp_after < 0.55 and cp_loss >= 100:
        return "Missed Win"

    # Also missed win if had forced mate and lost it
    if is_mate_before and mate_before is not None:
        is_player_mating = (color == "white" and mate_before > 0) or (color == "black" and mate_before < 0)
        if is_player_mating and not is_mate_after:
            return "Missed Win"

    # ── Best move (cp_loss == 0) — but could be Brilliant or Great ──
    if cp_loss == 0 and best_move is not None:
        played_is_best = (move == best_move)

        if played_is_best:
            # Check for Brilliant: sacrifice that maintains/gains advantage
            # A sacrifice = the player gives up material on this move
            if _is_sacrifice(board_before, move, color):
                # Must be a hard-to-find move: position is complex enough
                # and the sacrifice leads to a tangible advantage
                if player_wp_after >= 0.55:
                    return "Brilliant"

            # Check for Great: best move in a sharp position with many alternatives
            # that would be significantly worse. Approximation: position is complex
            # (many legal moves) and the second-best move would lose significantly.
            legal_count = board_before.legal_moves.count()
            if legal_count >= 8 and wp_loss <= 0 and player_wp_before >= 0.4:
                # The position was sharp and the player found the only strong move
                if _is_tactical_position(board_before):
                    return "Great"

            return "Best"

    # For non-zero cp_loss, use win probability thresholds
    if cp_loss == 0:
        return "Best"

    # ── Classification by win% loss (ELO-relative thresholds) ──
    wp_loss_pct = wp_loss * 100  # convert to percentage points
    thresholds = _get_elo_band(player_elo)

    if wp_loss_pct <= thresholds["excellent"]:
        return "Excellent"
    elif wp_loss_pct <= thresholds["good"]:
        return "Good"
    elif wp_loss_pct <= thresholds["inaccuracy"]:
        return "Inaccuracy"
    elif wp_loss_pct <= thresholds["mistake"]:
        return "Mistake"
    else:
        return "Blunder"


def _is_sacrifice(board: chess.Board, move: chess.Move, color: str) -> bool:
    """
    Check if a move is a material sacrifice.
    A sacrifice = the player gives up material that isn't immediately recaptured
    by a forced sequence. Simple heuristic: move to a square attacked by opponent
    and the piece is worth more than what it captures (or it's a non-capture to
    an attacked square).
    """
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return False

    piece_values = {
        chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
        chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
    }

    moving_value = piece_values.get(moving_piece.piece_type, 0)

    # Not a sacrifice if it's a pawn or king move
    if moving_value <= 1:
        return False

    # Check if the destination square is attacked by opponent
    opponent_color = not board.turn
    if not board.is_attacked_by(opponent_color, move.to_square):
        return False

    # If it's a capture, check if we're giving up more than we get
    captured = board.piece_at(move.to_square)
    captured_value = piece_values.get(captured.piece_type, 0) if captured else 0

    # It's a sacrifice if we're losing material (piece value > captured value)
    return moving_value > captured_value + 1  # +1 margin for approximate equality


def _is_tactical_position(board: chess.Board) -> bool:
    """
    Heuristic check for whether a position is tactically sharp.
    Looks for: checks available, hanging pieces, pins, multiple captures.
    """
    captures = sum(1 for m in board.legal_moves if board.is_capture(m))
    checks = sum(1 for m in board.legal_moves if board.gives_check(m))
    return captures >= 3 or checks >= 2


# ═══════════════════════════════════════════════════════════
# Phase Detection
# ═══════════════════════════════════════════════════════════

PIECE_VALUES = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def count_material(board: chess.Board) -> int:
    """Count non-pawn material value (for phase detection)."""
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total += len(board.pieces(piece_type, chess.BLACK)) * value
    return total


def count_developed_minors(board: chess.Board) -> int:
    """Count how many minor pieces (N/B) have left their starting squares."""
    starting = {
        chess.WHITE: {
            chess.KNIGHT: [chess.B1, chess.G1],
            chess.BISHOP: [chess.C1, chess.F1],
        },
        chess.BLACK: {
            chess.KNIGHT: [chess.B8, chess.G8],
            chess.BISHOP: [chess.C8, chess.F8],
        },
    }
    developed = 0
    for color in [chess.WHITE, chess.BLACK]:
        for piece_type, home_squares in starting[color].items():
            for sq in home_squares:
                piece = board.piece_at(sq)
                if not piece or piece.piece_type != piece_type or piece.color != color:
                    developed += 1
    return developed


def queens_on_board(board: chess.Board) -> bool:
    """Check if any queens remain on the board."""
    return bool(board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK))


def detect_phase(board: chess.Board, move_num: int, castled_white: bool, castled_black: bool) -> str:
    """
    Multi-factor game phase detection:
    - Opening: move ≤ 15 AND high material AND few pieces developed
    - Endgame: low material OR no queens with reduced material
    - Middlegame: everything else
    """
    material = count_material(board)
    developed = count_developed_minors(board)
    has_queens = queens_on_board(board)

    if material == 0:
        return "endgame"
    if material <= 13:
        return "endgame"
    if not has_queens and material <= 20:
        return "endgame"
    # Late-game with reduced material (e.g. Q+minor vs Q+minor)
    if move_num >= 40 and material <= 24:
        return "endgame"
    # Very late game with some pieces — endgame by definition
    if move_num >= 50 and material <= 30:
        return "endgame"

    if move_num <= 15 and material > 26 and developed < 6:
        return "opening"

    return "middlegame"


# ═══════════════════════════════════════════════════════════
# Puzzle Generation
# ═══════════════════════════════════════════════════════════


def generate_puzzle_data(
    *,
    fen_before: str,
    san: str,
    best_move_san: str | None,
    best_move_uci: str | None,
    cp_loss: int,
    phase: str,
    move_quality: str,
    move_number: int,
    best_second_gap_cp: int | None = None,
    is_only_legal: bool = False,
    eval_before_cp: int | None = None,
    solution_line: list[str] | None = None,
) -> dict | None:
    """
    Generate puzzle data from a blunder/mistake/missed-win move.
    Returns a dict with puzzle fields, or None if not suitable.

    Filtering rules:
    - Only Blunder / Mistake / Missed Win moves qualify.
        - There must be essentially ONE good move: the gap between the best
            and second-best engine line must be >= 300 cp. If the gap is
            smaller (or unknown), multiple moves may be acceptable and the
            position is not a clean puzzle.
        - Exception: if there is only one legal move, allow it even if
            second-best data is unavailable.
    - The position must not already be completely winning for one side
      (abs eval >= 600 cp) — those puzzles are trivial.
    - The user must have missed it (implied by move_quality check above;
      Best/Great/Excellent/Good moves never reach here).
    """
    if move_quality not in ("Blunder", "Mistake", "Missed Win"):
        return None
    if not fen_before or not best_move_san:
        return None

    # ── Reject completely winning positions ──
    # If one side is already up 600+ cp the puzzle is trivial/uninteresting.
    PUZZLE_EVAL_LIMIT_CP = 600
    if eval_before_cp is not None and abs(eval_before_cp) >= PUZZLE_EVAL_LIMIT_CP:
        return None

    # ── Only-one-good-move filter ──
    # Require a strong best-vs-second gap for non-forced positions.
    PUZZLE_GAP_THRESHOLD_CP = 300
    if not is_only_legal:
        if best_second_gap_cp is None:
            return None
        if best_second_gap_cp < PUZZLE_GAP_THRESHOLD_CP:
            return None

    puzzle_key = hashlib.md5(f"{fen_before}|{san}".encode()).hexdigest()

    # Side to move from FEN
    fen_parts = fen_before.split()
    side_to_move = "white" if len(fen_parts) > 1 and fen_parts[1] == "w" else "black"

    # Puzzle type
    if move_quality == "Missed Win":
        puzzle_type = "missed_win"
    elif move_quality == "Blunder":
        puzzle_type = "blunder"
    else:
        puzzle_type = "mistake"

    # Detect tactical themes
    tactic_tags = detect_puzzle_tactics(
        fen_before,
        best_move_uci,
        solution_line,
    ) if best_move_uci else [puzzle_type, phase or "middlegame"]

    # Always include phase as a theme
    p = phase or "middlegame"
    if p not in tactic_tags:
        tactic_tags.append(p)

    return {
        "puzzle_key": puzzle_key,
        "fen": fen_before,
        "side_to_move": side_to_move,
        "best_move_san": best_move_san,
        "best_move_uci": best_move_uci,
        "played_move_san": san,
        "eval_loss_cp": cp_loss,
        "phase": phase or "middlegame",
        "puzzle_type": puzzle_type,
        "difficulty": "standard",
        "move_number": move_number,
        "solution_line": solution_line or [],
        "themes": tactic_tags,
    }


async def compute_solution_line(
    fen: str,
    engine: "chess.engine.UciProtocol",
    depth: int = 12,
    max_moves: int = 6,
) -> list[str]:
    """
    Compute a multi-move solution line from a puzzle position using Stockfish.
    Returns a list of UCI move strings: [userMove, opponentReply, userMove2, ...].
    The line alternates: puzzle solver's move, then opponent's forced reply, etc.
    Stops when the position becomes clearly won/lost or max_moves reached.
    """
    board = chess.Board(fen)
    line: list[str] = []

    for i in range(max_moves):
        if board.is_game_over():
            break

        info = await engine.analyse(board, chess.engine.Limit(depth=depth))
        pv = info.get("pv")
        if not pv or len(pv) == 0:
            break

        best = pv[0]
        line.append(best.uci())
        board.push(best)

        # After opponent's reply (odd indices), check if position is decisive
        if i > 0 and i % 2 == 1:
            score = info.get("score")
            if score:
                pov = score.pov(board.turn)
                if pov.is_mate():
                    break
                cp = pov.score()
                if cp is not None and abs(cp) > 500:
                    break

    return line


# ═══════════════════════════════════════════════════════════
# Board Description for AI Explanations
# ═══════════════════════════════════════════════════════════


def describe_board_for_ai(fen: str, san: str) -> str:
    """
    Generate a human-readable board description from FEN for AI explanations.
    Includes piece positions, attacked squares, hanging pieces, and threats.
    This replaces relying on GPT to parse FEN notation.
    """
    try:
        board = chess.Board(fen)
    except (ValueError, TypeError):
        return "Could not parse position."

    try:
        move = board.parse_san(san)
    except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
        move = None

    lines = []

    # Piece positions
    white_pieces = []
    black_pieces = []
    piece_names = {
        chess.PAWN: "Pawn", chess.KNIGHT: "Knight", chess.BISHOP: "Bishop",
        chess.ROOK: "Rook", chess.QUEEN: "Queen", chess.KING: "King"
    }
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece:
            name = f"{piece_names.get(piece.piece_type, '?')} on {chess.square_name(sq)}"
            if piece.color == chess.WHITE:
                white_pieces.append(name)
            else:
                black_pieces.append(name)

    lines.append(f"White pieces: {', '.join(white_pieces)}")
    lines.append(f"Black pieces: {', '.join(black_pieces)}")

    # Who is to move
    side = "White" if board.turn == chess.WHITE else "Black"
    lines.append(f"{side} to move.")

    # Check status
    if board.is_check():
        lines.append(f"{side} is in check.")

    # Hanging pieces (pieces attacked by opponent but not defended)
    hanging = []
    opponent = not board.turn
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == board.turn:
            if board.is_attacked_by(opponent, sq):
                defenders = len(board.attackers(board.turn, sq))
                attackers = len(board.attackers(opponent, sq))
                if attackers > defenders:
                    hanging.append(f"{piece_names.get(piece.piece_type, '?')} on {chess.square_name(sq)}")

    if hanging:
        lines.append(f"Hanging pieces for {side}: {', '.join(hanging)}")

    # What the played move does
    if move:
        moving_piece = board.piece_at(move.from_square)
        if moving_piece:
            mp_name = piece_names.get(moving_piece.piece_type, "?")
            lines.append(f"The move {san} moves the {mp_name} from {chess.square_name(move.from_square)} to {chess.square_name(move.to_square)}.")

            # Is it a capture?
            if board.is_capture(move):
                captured = board.piece_at(move.to_square)
                if captured:
                    lines.append(f"This captures the {piece_names.get(captured.piece_type, '?')} on {chess.square_name(move.to_square)}.")
                elif board.is_en_passant(move):
                    lines.append("This is an en passant capture.")

            # Does it give check?
            board_after = board.copy()
            board_after.push(move)
            if board_after.is_check():
                lines.append("This move gives check.")
                if board_after.is_checkmate():
                    lines.append("This is checkmate!")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


def avg(lst: list) -> float | None:
    """Average of a list, or None if empty."""
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)


# ═══════════════════════════════════════════════════════════
# Clock / Move Time Parsing
# ═══════════════════════════════════════════════════════════

_CLK_RE = re.compile(r'\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]')


def parse_clock_comment(comment: str | None) -> float | None:
    """
    Parse [%clk H:MM:SS] or [%clk H:MM:SS.s] from a PGN node comment.
    Returns remaining time in seconds, or None if not found.
    """
    if not comment:
        return None
    m = _CLK_RE.search(comment)
    if not m:
        return None
    hours, minutes, seconds = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return hours * 3600 + minutes * 60 + seconds


# ═══════════════════════════════════════════════════════════
# Blunder Subtype Classification
# ═══════════════════════════════════════════════════════════

PIECE_VALUES_MAP = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

PIECE_NAMES_MAP = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}

# ═══════════════════════════════════════════════════════════
# Tactical Pattern Detection Helpers
# ═══════════════════════════════════════════════════════════

def _detect_fork(board: chess.Board, move: chess.Move) -> bool:
    """Check if a move creates a fork (piece attacks 2+ higher-value targets)."""
    board_after = board.copy()
    board_after.push(move)
    attacker = board.piece_at(move.from_square)
    if not attacker:
        return False
    attacker_val = PIECE_VALUES_MAP.get(attacker.piece_type, 0)
    opponent = not board.turn
    attacked_targets = 0
    for sq in board_after.attacks(move.to_square):
        target = board_after.piece_at(sq)
        if target and target.color == opponent:
            target_val = PIECE_VALUES_MAP.get(target.piece_type, 0)
            if target_val > attacker_val or target.piece_type == chess.KING:
                attacked_targets += 1
    return attacked_targets >= 2


def _detect_pin(board: chess.Board, move: chess.Move) -> bool:
    """Check if a move creates or exploits a pin on a ray (file/rank/diagonal)."""
    board_after = board.copy()
    board_after.push(move)
    opponent = not board.turn
    # Check if any opponent piece is now pinned to their king
    opp_king_sq = board_after.king(opponent)
    if opp_king_sq is None:
        return False
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color == opponent and sq != opp_king_sq:
            if board_after.is_pinned(opponent, sq):
                # Verify that this pin involves our moved piece
                pin_dir = board_after.pin(opponent, sq)
                if pin_dir and move.to_square in pin_dir:
                    return True
    return False


def _detect_skewer(board: chess.Board, move: chess.Move) -> bool:
    """Check if a move creates a skewer (attacks high-value piece with lower behind it)."""
    board_after = board.copy()
    board_after.push(move)
    attacker = board.piece_at(move.from_square)
    if not attacker:
        return False
    # Skewers happen on rays — only bishops, rooks, queens can skewer
    if attacker.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    opponent = not board.turn
    to_sq = move.to_square
    to_rank, to_file = chess.square_rank(to_sq), chess.square_file(to_sq)

    # Check each ray direction from the moved piece
    ray_dirs = []
    if attacker.piece_type in (chess.ROOK, chess.QUEEN):
        ray_dirs += [(0, 1), (0, -1), (1, 0), (-1, 0)]
    if attacker.piece_type in (chess.BISHOP, chess.QUEEN):
        ray_dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

    for dr, df in ray_dirs:
        pieces_on_ray = []
        r, f = to_rank + dr, to_file + df
        while 0 <= r <= 7 and 0 <= f <= 7:
            sq = chess.square(f, r)
            p = board_after.piece_at(sq)
            if p:
                if p.color == opponent:
                    pieces_on_ray.append(p)
                break  # blocked by any piece
            r += dr
            f += df
        # Continue past first piece if it can move
        if len(pieces_on_ray) == 1:
            r2, f2 = r + dr, f + df
            while 0 <= r2 <= 7 and 0 <= f2 <= 7:
                sq2 = chess.square(f2, r2)
                p2 = board_after.piece_at(sq2)
                if p2:
                    if p2.color == opponent:
                        pieces_on_ray.append(p2)
                    break
                r2 += dr
                f2 += df
        if len(pieces_on_ray) >= 2:
            v1 = PIECE_VALUES_MAP.get(pieces_on_ray[0].piece_type, 0)
            v2 = PIECE_VALUES_MAP.get(pieces_on_ray[1].piece_type, 0)
            # Skewer: front piece is more valuable (or is king)
            if pieces_on_ray[0].piece_type == chess.KING or v1 > v2:
                return True
    return False


def _detect_discovered_attack(board: chess.Board, move: chess.Move) -> bool:
    """Check if moving a piece reveals an attack from another piece behind it."""
    board_after = board.copy()
    board_after.push(move)
    player = board.turn
    opponent = not player
    from_sq = move.from_square
    # Check if removing the piece from from_sq opened a line for our sliding pieces
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != player or sq == move.from_square:
            continue
        if piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        # Did this piece gain new attacks by the move?
        attacks_before = board.attacks(sq)
        attacks_after = board_after.attacks(sq)
        new_attacks = attacks_after & ~attacks_before
        for atk_sq in new_attacks:
            target = board_after.piece_at(atk_sq)
            if target and target.color == opponent and PIECE_VALUES_MAP.get(target.piece_type, 0) >= 3:
                return True
    return False


def _detect_back_rank(board: chess.Board, move: chess.Move) -> bool:
    """Check if a move delivers or threatens back-rank mate."""
    board_after = board.copy()
    board_after.push(move)
    if board_after.is_checkmate():
        opponent = not board.turn
        king_sq = board_after.king(opponent)
        if king_sq is not None:
            king_rank = chess.square_rank(king_sq)
            if (opponent == chess.WHITE and king_rank == 0) or (opponent == chess.BLACK and king_rank == 7):
                return True
    # Also check if it creates a back-rank mate threat
    if board_after.is_check():
        opponent = not board.turn
        king_sq = board_after.king(opponent)
        if king_sq is not None:
            king_rank = chess.square_rank(king_sq)
            if (opponent == chess.WHITE and king_rank == 0) or (opponent == chess.BLACK and king_rank == 7):
                return True
    return False


def _is_pawn_promotion_tactic(board: chess.Board, move: chess.Move) -> bool:
    """Check if the move involves pawn promotion or a key promotion push."""
    if move.promotion:
        return True
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.PAWN:
        to_rank = chess.square_rank(move.to_square)
        # Pawn reaching 7th rank (about to promote)
        if (piece.color == chess.WHITE and to_rank == 6) or (piece.color == chess.BLACK and to_rank == 1):
            return True
    return False


def _detect_mate_threat(board: chess.Board, move: chess.Move) -> int | None:
    """Check if a move delivers mate or mate-in-N (up to 3). Returns N or None."""
    board_after = board.copy()
    board_after.push(move)
    if board_after.is_checkmate():
        return 1
    # Check mate in 2-3 by examining if all opponent responses lead to forced mate
    # (Simplified: just check for mate-in-1 and obvious check sequences)
    if board_after.is_check():
        # After opponent's only legal responses, can we mate?
        for response in board_after.legal_moves:
            b2 = board_after.copy()
            b2.push(response)
            for our_move in b2.legal_moves:
                b3 = b2.copy()
                b3.push(our_move)
                if b3.is_checkmate():
                    return 2
    return None


def _detect_deflection(board: chess.Board, move: chess.Move) -> bool:
    """Check if a move forces a defender away from a critical square."""
    board_after = board.copy()
    board_after.push(move)
    # If the move is a capture or attack on a piece that was defending something
    captured = board.piece_at(move.to_square)
    if not captured:
        return False
    opponent = not board.turn
    player = board.turn
    # What was the captured piece defending?
    for sq in board.attacks(move.to_square):
        other = board.piece_at(sq)
        if other and other.color == opponent and PIECE_VALUES_MAP.get(other.piece_type, 0) >= 3:
            # Was the captured piece a defender of this square?
            defenders_before = len(board.attackers(opponent, sq))
            defenders_after = len(board_after.attackers(opponent, sq))
            if defenders_after < defenders_before:
                attackers_after = len(board_after.attackers(player, sq))
                if attackers_after > defenders_after:
                    return True
    return False


# ═══════════════════════════════════════════════════════════
# Tactic Detection Engine — for puzzles
# ═══════════════════════════════════════════════════════════

def detect_puzzle_tactics(
    fen: str,
    best_move_uci: str,
    solution_line: list[str] | None = None,
) -> list[str]:
    """
    Analyze a puzzle position and its solution to detect tactical themes.
    Returns a list of tactic tags like ['fork', 'knight', 'middlegame'].
    """
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(best_move_uci)
    except Exception:
        return []

    if move not in board.legal_moves:
        return []

    tags: list[str] = []
    moving_piece = board.piece_at(move.from_square)

    # ── Core tactical patterns ──
    if _detect_fork(board, move):
        tags.append("fork")
    if _detect_pin(board, move):
        tags.append("pin")
    if _detect_skewer(board, move):
        tags.append("skewer")
    if _detect_discovered_attack(board, move):
        tags.append("discovered_attack")
    if _detect_back_rank(board, move):
        tags.append("back_rank")
    if _detect_deflection(board, move):
        tags.append("deflection")
    if _is_pawn_promotion_tactic(board, move):
        tags.append("promotion")

    # ── Mate patterns ──
    mate_n = _detect_mate_threat(board, move)
    if mate_n == 1:
        tags.append("mate_in_1")
    elif mate_n is not None:
        tags.append("checkmate_pattern")

    # ── Captures ──
    captured = board.piece_at(move.to_square)
    board_after = board.copy()
    board_after.push(move)

    if captured:
        cap_val = PIECE_VALUES_MAP.get(captured.piece_type, 0)
        mov_val = PIECE_VALUES_MAP.get(moving_piece.piece_type, 0) if moving_piece else 0
        if cap_val > mov_val:
            tags.append("winning_capture")
        if _is_sacrifice(board, move, "white" if board.turn == chess.WHITE else "black"):
            tags.append("sacrifice")
    elif _is_sacrifice(board, move, "white" if board.turn == chess.WHITE else "black"):
        tags.append("sacrifice")

    # ── Check patterns ──
    if board_after.is_check() and "mate_in_1" not in tags and "back_rank" not in tags:
        tags.append("check")

    # ── King activity (endgame king play) ──
    if moving_piece and moving_piece.piece_type == chess.KING:
        total_pieces = len(board.piece_map())
        if total_pieces <= 12:
            tags.append("king_activity")

    # ── Piece tags (what piece is involved) ──
    if moving_piece:
        piece_name = PIECE_NAMES_MAP.get(moving_piece.piece_type)
        if piece_name and piece_name not in tags:
            tags.append(piece_name)

    # ── Analyze solution line for multi-move tactics ──
    if solution_line and len(solution_line) >= 3:
        try:
            b = chess.Board(fen)
            for i, uci in enumerate(solution_line[:4]):
                m = chess.Move.from_uci(uci)
                if m in b.legal_moves:
                    if i % 2 == 0:  # Our moves
                        if _detect_fork(b, m) and "fork" not in tags:
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

    # If no specific tactic found, mark as positional
    if not any(t in tags for t in [
        "fork", "pin", "skewer", "discovered_attack", "back_rank", "deflection",
        "promotion", "mate_in_1", "checkmate_pattern", "sacrifice", "winning_capture",
        "check", "king_activity", "combination",
    ]):
        tags.append("positional")

    return tags


# ═══════════════════════════════════════════════════════════
# Blunder Subtype Classification (Redesigned)
# ═══════════════════════════════════════════════════════════

def classify_blunder_subtype(
    board_before: chess.Board,
    move: chess.Move,
    best_move: chess.Move | None,
    phase: str,
) -> str:
    """
    Classify a blunder into a subtype based on what happened and what was missed.

    Subtypes (expanded from 4 to 10):
    - hanging_piece: left a piece undefended or moved to an attacked square
    - missed_fork: best move was a fork the player didn't see
    - missed_pin: best move exploited or created a pin
    - missed_skewer: best move was a skewer
    - missed_discovery: best move created a discovered attack
    - back_rank: blunder related to back-rank weakness
    - king_safety: weakened own king position
    - endgame_technique: genuine endgame principle error (king activity, opposition, pawn play)
    - missed_mate: missed a checkmate or mate-in-N
    - positional: none of the above — a positional or strategic error
    """
    player_color = board_before.turn
    opponent_color = not player_color

    # ── 1. Check what the BEST move would have achieved ──
    if best_move and best_move in board_before.legal_moves:
        # Missed checkmate?
        mate_n = _detect_mate_threat(board_before, best_move)
        if mate_n is not None:
            return "missed_mate"

        # Missed fork?
        if _detect_fork(board_before, best_move):
            return "missed_fork"

        # Missed pin?
        if _detect_pin(board_before, best_move):
            return "missed_pin"

        # Missed skewer?
        if _detect_skewer(board_before, best_move):
            return "missed_skewer"

        # Missed discovered attack?
        if _detect_discovered_attack(board_before, best_move):
            return "missed_discovery"

        # Missed back-rank threat?
        if _detect_back_rank(board_before, best_move):
            return "back_rank"

    # ── 2. Check what the PLAYED move caused ──
    board_after = board_before.copy()
    board_after.push(move)

    # Did the player hang a piece?
    moving_piece = board_before.piece_at(move.from_square)
    if moving_piece:
        attackers = len(board_after.attackers(opponent_color, move.to_square))
        defenders = len(board_after.attackers(player_color, move.to_square))
        piece_val = PIECE_VALUES_MAP.get(moving_piece.piece_type, 0)
        if attackers > defenders and piece_val >= 3:
            return "hanging_piece"

    # Did the move expose another piece?
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if p and p.color == player_color and sq != move.to_square:
            atk_after = len(board_after.attackers(opponent_color, sq))
            def_after = len(board_after.attackers(player_color, sq))
            # Was this piece safe before?
            atk_before = len(board_before.attackers(opponent_color, sq))
            def_before = len(board_before.attackers(player_color, sq))
            val = PIECE_VALUES_MAP.get(p.piece_type, 0)
            if val >= 3 and atk_after > def_after and atk_before <= def_before:
                return "hanging_piece"

    # ── 3. King safety checks (all phases) ──
    if moving_piece and moving_piece.piece_type == chess.KING:
        if not board_before.is_castling(move):
            # King walked into danger or left safety
            if phase != "endgame":
                return "king_safety"

    # Pawn move weakening king shelter (opening/middlegame)
    if phase != "endgame" and moving_piece and moving_piece.piece_type == chess.PAWN:
        king_sq = board_before.king(player_color)
        if king_sq is not None:
            king_file = chess.square_file(king_sq)
            pawn_file = chess.square_file(move.from_square)
            if abs(king_file - pawn_file) <= 1:
                return "king_safety"

    # ── 4. Back-rank vulnerability (opponent can now exploit) ──
    # Check if after our move, opponent has a back-rank threat
    for i, opp_move in enumerate(board_after.legal_moves):
        if _detect_back_rank(board_after, opp_move):
            return "back_rank"
        if i >= 4:  # Only check a few to avoid being too slow
            break
    # More thorough: check if opponent's response is check on back rank
    if board_after.is_check():
        king_sq = board_after.king(player_color)
        if king_sq is not None:
            king_rank = chess.square_rank(king_sq)
            if (player_color == chess.WHITE and king_rank == 0) or \
               (player_color == chess.BLACK and king_rank == 7):
                return "back_rank"

    # ── 5. Endgame-specific errors (only genuine endgame patterns) ──
    if phase == "endgame":
        total_pieces = len(board_before.piece_map())
        # King not centralized when it should be
        if moving_piece and moving_piece.piece_type != chess.KING and total_pieces <= 10:
            king_sq = board_before.king(player_color)
            if king_sq is not None:
                kr, kf = chess.square_rank(king_sq), chess.square_file(king_sq)
                if kr in (0, 7) or kf in (0, 7):
                    # King stuck on edge while not playing with it — endgame technique
                    return "endgame_technique"

        # Pawn endgame errors (opposition, passed pawns)
        if total_pieces <= 8:
            return "endgame_technique"

    # ── 6. Missed winning capture ──
    if best_move:
        captured = board_before.piece_at(best_move.to_square)
        if captured and PIECE_VALUES_MAP.get(captured.piece_type, 0) >= 3:
            return "missed_capture"

    # ── Default: positional error (NOT missed_tactic) ──
    return "positional"
