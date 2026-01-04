"""
Difficulty Classification Module

Deterministic, rule-based difficulty classification for chess puzzles.
No AI/LLM - uses explicit thresholds and move characteristics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import chess

if TYPE_CHECKING:
    from .puzzle_types import Difficulty


# =============================================================================
# DIFFICULTY THRESHOLDS (centipawns)
# =============================================================================
# These thresholds determine puzzle difficulty based on eval loss

EASY_CP_THRESHOLD = 300     # Clear blunders: obvious mistake, easy to spot
MEDIUM_CP_THRESHOLD = 200   # Medium mistakes: requires some calculation
HARD_CP_THRESHOLD = 100     # Subtle mistakes: quiet moves, defensive resources

# =============================================================================
# MOVE CHARACTERISTIC ANALYSIS
# =============================================================================


def _is_capture_move(board: chess.Board, move: chess.Move) -> bool:
    """
    Check if a move is a capture.
    
    Captures are generally easier to find because:
    - They're forcing moves
    - Players naturally look for material gains
    """
    return board.is_capture(move)


def _is_check_move(board: chess.Board, move: chess.Move) -> bool:
    """
    Check if a move gives check.
    
    Check moves are easier to find because:
    - They're forcing (opponent must respond)
    - Check is a natural tactical goal
    """
    return board.gives_check(move)


def _is_promotion_move(move: chess.Move) -> bool:
    """
    Check if a move is a pawn promotion.
    
    Promotions are often easier to spot, especially queen promotions.
    """
    return move.promotion is not None


def _is_castle_move(board: chess.Board, move: chess.Move) -> bool:
    """
    Check if a move is castling.
    
    Castling as the 'best move' is usually obvious.
    """
    return board.is_castling(move)


def _has_tactical_motif(board: chess.Board, move: chess.Move) -> bool:
    """
    Detect if move has a tactical motif (fork potential, discovered attack, etc.)
    
    These are more satisfying but also more visible patterns.
    Heuristic detection only - no deep analysis.
    """
    # After playing the move, check if multiple pieces are attacked
    board_copy = board.copy()
    board_copy.push(move)
    
    # Count attacked pieces
    opponent_color = not board_copy.turn
    attacked_valuable_pieces = 0
    
    for square in chess.SQUARES:
        piece = board_copy.piece_at(square)
        if piece and piece.color == opponent_color:
            # Check if this piece is attacked
            if board_copy.is_attacked_by(not opponent_color, square):
                # Count valuable pieces (not pawns)
                if piece.piece_type != chess.PAWN:
                    attacked_valuable_pieces += 1
    
    # If we're attacking 2+ valuable pieces, likely a tactical motif
    return attacked_valuable_pieces >= 2


def _is_quiet_move(board: chess.Board, move: chess.Move) -> bool:
    """
    Determine if a move is 'quiet' - neither capture, check, nor promotion.
    
    Quiet moves are typically harder to find because:
    - No immediate material change
    - Requires positional understanding
    - Often defensive or prophylactic
    """
    if board.is_capture(move):
        return False
    if board.gives_check(move):
        return False
    if move.promotion is not None:
        return False
    return True


def _requires_calculation(board: chess.Board, move: chess.Move, eval_loss: int) -> bool:
    """
    Estimate if finding this move requires deeper calculation.
    
    Heuristic: moves in complex positions (many legal moves, unclear position)
    with moderate eval swings require calculation.
    """
    # Count legal moves - more options = more to calculate
    legal_moves = list(board.legal_moves)
    many_options = len(legal_moves) > 25
    
    # Complex position indicators
    has_queens = (
        len(board.pieces(chess.QUEEN, chess.WHITE)) +
        len(board.pieces(chess.QUEEN, chess.BLACK))
    ) > 0
    
    has_many_pieces = len(board.piece_map()) > 16
    
    return many_options and has_queens and has_many_pieces


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================


def classify_difficulty(
    fen: str,
    best_move_san: str,
    eval_loss_cp: int,
    phase: str,
) -> "Difficulty":
    """
    Classify puzzle difficulty using deterministic rules.
    
    Classification Rules:
    
    EASY (eval_loss >= 300cp):
    - Clear blunders
    - Single obvious best move
    - Usually involves capture, check, or clear tactical pattern
    - No deep calculation required
    
    MEDIUM (eval_loss >= 200cp):
    - Significant mistakes
    - Often involves tactical themes
    - May require short calculation (2-3 moves)
    
    HARD (eval_loss >= 100cp):
    - Subtle mistakes
    - Often quiet/defensive moves
    - May require positional understanding
    - Longer calculation or prophylactic thinking
    
    Additional modifiers:
    - Quiet moves increase difficulty
    - Endgame positions with technique increase difficulty
    - Clear tactical motifs decrease difficulty
    - Check/capture moves decrease difficulty
    
    Args:
        fen: FEN string of the puzzle position
        best_move_san: The correct move in SAN notation
        eval_loss_cp: Centipawn loss from the played mistake
        phase: Game phase ("opening", "middlegame", "endgame")
    
    Returns:
        Difficulty enum value (EASY, MEDIUM, HARD)
    """
    from .puzzle_types import Difficulty
    
    # Parse position and move
    try:
        board = chess.Board(fen)
        move = board.parse_san(best_move_san)
    except Exception:
        # If we can't parse, fall back to pure eval-based classification
        if eval_loss_cp >= EASY_CP_THRESHOLD:
            return Difficulty.EASY
        elif eval_loss_cp >= MEDIUM_CP_THRESHOLD:
            return Difficulty.MEDIUM
        return Difficulty.HARD
    
    # =================
    # BASE CLASSIFICATION
    # =================
    # Start with eval loss as primary factor
    
    if eval_loss_cp >= EASY_CP_THRESHOLD:
        base_difficulty = Difficulty.EASY
    elif eval_loss_cp >= MEDIUM_CP_THRESHOLD:
        base_difficulty = Difficulty.MEDIUM
    else:
        base_difficulty = Difficulty.HARD
    
    # =================
    # DIFFICULTY MODIFIERS
    # =================
    # Adjust based on move characteristics
    
    difficulty_score = _difficulty_to_score(base_difficulty)
    
    # --- Factors that DECREASE difficulty (easier) ---
    
    # Capture moves are easier to spot
    if _is_capture_move(board, move):
        difficulty_score -= 1
    
    # Check moves are forcing and obvious
    if _is_check_move(board, move):
        difficulty_score -= 1
    
    # Promotions are usually clear
    if _is_promotion_move(move):
        difficulty_score -= 1
    
    # Castling is almost always obvious when it's best
    if _is_castle_move(board, move):
        difficulty_score -= 2
    
    # Clear tactical patterns
    if _has_tactical_motif(board, move):
        difficulty_score -= 1
    
    # --- Factors that INCREASE difficulty (harder) ---
    
    # Quiet moves require positional understanding
    if _is_quiet_move(board, move):
        difficulty_score += 1
    
    # Endgame technique often requires precise calculation
    if phase == "endgame":
        difficulty_score += 1
    
    # Complex positions requiring calculation
    if _requires_calculation(board, move, eval_loss_cp):
        difficulty_score += 1
    
    # Opening errors before deep understanding develops
    if phase == "opening" and eval_loss_cp < 200:
        difficulty_score += 1
    
    # =================
    # FINAL CLASSIFICATION
    # =================
    # Convert score back to difficulty level
    
    return _score_to_difficulty(difficulty_score)


def _difficulty_to_score(difficulty: "Difficulty") -> int:
    """Convert difficulty enum to numeric score for adjustment."""
    from .puzzle_types import Difficulty
    
    if difficulty == Difficulty.EASY:
        return 0
    elif difficulty == Difficulty.MEDIUM:
        return 1
    else:  # HARD
        return 2


def _score_to_difficulty(score: int) -> "Difficulty":
    """Convert numeric score back to difficulty enum."""
    from .puzzle_types import Difficulty
    
    # Clamp to valid range
    if score <= 0:
        return Difficulty.EASY
    elif score == 1:
        return Difficulty.MEDIUM
    else:  # score >= 2
        return Difficulty.HARD


# =============================================================================
# DIFFICULTY UTILITIES
# =============================================================================


def get_difficulty_description(difficulty: "Difficulty") -> str:
    """Get human-readable description of difficulty level."""
    from .puzzle_types import Difficulty
    
    descriptions = {
        Difficulty.EASY: "Clear tactical opportunity - single best move is obvious",
        Difficulty.MEDIUM: "Requires short calculation - tactical pattern present",
        Difficulty.HARD: "Subtle move - may be quiet, defensive, or require deeper thought",
    }
    return descriptions.get(difficulty, "Unknown difficulty")


def get_difficulty_emoji(difficulty: "Difficulty") -> str:
    """Get emoji representation of difficulty."""
    from .puzzle_types import Difficulty
    
    emojis = {
        Difficulty.EASY: "🟢",
        Difficulty.MEDIUM: "🟡",
        Difficulty.HARD: "🔴",
    }
    return emojis.get(difficulty, "⚪")


def estimate_solve_time_seconds(difficulty: "Difficulty") -> tuple[int, int]:
    """
    Estimate time range to solve puzzle based on difficulty.
    
    Returns (min_seconds, max_seconds) range.
    """
    from .puzzle_types import Difficulty
    
    times = {
        Difficulty.EASY: (5, 30),
        Difficulty.MEDIUM: (20, 90),
        Difficulty.HARD: (45, 180),
    }
    return times.get(difficulty, (30, 120))
