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
    eval_before_cp: int | None = None,
) -> dict | None:
    """
    Generate puzzle data from a blunder/mistake/missed-win move.
    Returns a dict with puzzle fields, or None if not suitable.

    Filtering rules:
    - Only Blunder / Mistake / Missed Win moves qualify.
    - There must be essentially ONE good move: the gap between the best
      and second-best engine line must be >= 150 cp.  If the gap is
      smaller, multiple moves are acceptable and the position is not a
      clean puzzle.
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
    # If we have the gap between best and 2nd-best move, reject positions
    # where the 2nd-best move is close to the best (multiple good options).
    PUZZLE_GAP_THRESHOLD_CP = 150
    if best_second_gap_cp is not None and best_second_gap_cp < PUZZLE_GAP_THRESHOLD_CP:
        return None

    puzzle_key = hashlib.md5(f"{fen_before}|{san}".encode()).hexdigest()

    # Difficulty based on cp_loss
    if cp_loss >= 300:
        difficulty = "platinum"
    elif cp_loss >= 200:
        difficulty = "gold"
    elif cp_loss >= 100:
        difficulty = "silver"
    else:
        difficulty = "bronze"

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
        "difficulty": difficulty,
        "move_number": move_number,
        "themes": [puzzle_type, phase or "middlegame"],
    }


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


def classify_blunder_subtype(
    board_before: chess.Board,
    move: chess.Move,
    best_move: chess.Move | None,
    phase: str,
) -> str | None:
    """
    Classify a blunder into a subtype:
    - hanging_piece: player left a piece en prise or moved to an attacked square
    - missed_tactic: best move was a fork, pin, skewer, or winning capture
    - king_safety: move weakened own king (pawn shield, moved near open file)
    - endgame_technique: blunder in an endgame position

    Returns subtype string or None if unclassifiable.
    """
    if phase == "endgame":
        return "endgame_technique"

    # Check if the played move left a piece hanging
    board_after = board_before.copy()
    board_after.push(move)

    # Hanging piece: after the move, check if any of the player's pieces
    # are attacked by the opponent but not adequately defended
    player_color = board_before.turn
    opponent_color = not player_color

    # Check the piece that just moved — is it now hanging?
    moving_piece = board_before.piece_at(move.from_square)
    if moving_piece:
        attackers = len(board_after.attackers(opponent_color, move.to_square))
        defenders = len(board_after.attackers(player_color, move.to_square))
        piece_val = PIECE_VALUES_MAP.get(moving_piece.piece_type, 0)
        if attackers > defenders and piece_val >= 3:
            return "hanging_piece"

    # Check if any other piece is now hanging due to vacating the from_square
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if p and p.color == player_color and sq != move.to_square:
            atk = len(board_after.attackers(opponent_color, sq))
            dfs = len(board_after.attackers(player_color, sq))
            val = PIECE_VALUES_MAP.get(p.piece_type, 0)
            if atk > dfs and val >= 3:
                return "hanging_piece"

    # Missed tactic: check if the best move was a capture, check, or fork
    if best_move:
        # Best move is a capture of a high-value piece
        captured = board_before.piece_at(best_move.to_square)
        if captured and PIECE_VALUES_MAP.get(captured.piece_type, 0) >= 3:
            return "missed_tactic"

        # Best move gives check
        board_test = board_before.copy()
        board_test.push(best_move)
        if board_test.is_check():
            return "missed_tactic"

    # King safety: move involves king's pawn shield or king moved to open file
    if moving_piece and moving_piece.piece_type == chess.KING:
        # King moved (not castling) — potentially unsafe
        if not board_before.is_castling(move):
            return "king_safety"

    # Pawn move that weakens king's shield
    if moving_piece and moving_piece.piece_type == chess.PAWN:
        king_sq = board_before.king(player_color)
        if king_sq is not None:
            king_file = chess.square_file(king_sq)
            pawn_file = chess.square_file(move.from_square)
            if abs(king_file - pawn_file) <= 1:
                return "king_safety"

    # Default: missed tactic (most common blunder cause)
    return "missed_tactic"
