# src/analytics/blunder_classifier.py
"""Module 1: Blunder Classification.

Classify every large evaluation loss into meaningful human-understandable categories.

Categories:
- Hanging piece: moved piece ends up under-defended
- Missed tactic: fork, pin, skewer, discovered attack available
- Endgame technique error: late-game positional/technique mistake
- Opening theory mistake: deviation leading to large eval loss
- Time pressure blunder: if clock data exists and time < threshold
- Overlooked recapture: simple recapture was available
- King safety blunder: king becomes exposed/attacked
- Back-rank weakness: vulnerable back rank exploited
- Pawn structure error: critical pawn structure damaged
- Piece activity error: piece became trapped or inactive
- Promotion oversight: failed to handle pawn promotion
- Unknown: unclassified

Implementation uses:
- Material delta + eval swing heuristics
- Board state analysis (attackers/defenders)
- Tactical pattern detection (forks, pins, skewers, discoveries)
- Pawn structure analysis
- Piece mobility assessment
- Phase context
- NO LLM inference
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import chess

from .schemas import BlunderClassification, BlunderByType, BlunderExample

if TYPE_CHECKING:
    from typing import Any

# Thresholds
BLUNDER_CP_THRESHOLD = 300
MISTAKE_CP_THRESHOLD = 100
TIME_PRESSURE_SECONDS = 30  # consider time pressure if clock < 30s
MATE_CP_THRESHOLD = 9000


@dataclass
class MoveContext:
    """Context for a single move being analyzed."""
    game_index: int
    move_number: int
    san: str
    move: chess.Move | None
    board_before: chess.Board
    board_after: chess.Board
    eval_before: int | None
    eval_after: int | None
    cp_loss: int
    phase: str
    clock_seconds: int | None = None  # remaining clock time
    fen_before: str | None = None
    move_sans_so_far: list[str] = field(default_factory=list)  # For FEN reconstruction


def _piece_value(piece_type: chess.PieceType) -> int:
    """Standard piece values."""
    return {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
        chess.KING: 0,
    }.get(piece_type, 0)


def _total_material(board: chess.Board) -> int:
    """Total material value on board."""
    total = 0
    for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        total += _piece_value(pt) * (
            len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK))
        )
    return total


def _reconstruct_board_from_moves(move_sans: list[str]) -> chess.Board:
    """Reconstruct board position from list of SAN moves."""
    board = chess.Board()
    for san in move_sans:
        try:
            move = board.parse_san(san)
            board.push(move)
        except Exception:
            break
    return board


def _get_piece_mobility(board: chess.Board, square: chess.Square, color: chess.Color) -> int:
    """Count legal moves for a piece."""
    piece = board.piece_at(square)
    if not piece or piece.color != color:
        return 0
    
    mobility = 0
    for move in board.legal_moves:
        if move.from_square == square:
            mobility += 1
    return mobility


def _is_piece_trapped(board: chess.Board, square: chess.Square) -> bool:
    """Check if a piece is trapped (few escape squares and attacked)."""
    piece = board.piece_at(square)
    if not piece or piece.piece_type in (chess.PAWN, chess.KING):
        return False
    
    color = piece.color
    opponent = not color
    
    # Check if attacked
    if not board.is_attacked_by(opponent, square):
        return False
    
    # Count escape squares
    mobility = _get_piece_mobility(board, square, color)
    
    # Trapped = attacked with low mobility
    return mobility <= 1


def _count_pawn_islands(board: chess.Board, color: chess.Color) -> int:
    """Count pawn islands (groups of connected pawns)."""
    pawn_files = set()
    for sq in board.pieces(chess.PAWN, color):
        pawn_files.add(chess.square_file(sq))
    
    if not pawn_files:
        return 0
    
    islands = 1
    sorted_files = sorted(pawn_files)
    for i in range(1, len(sorted_files)):
        if sorted_files[i] - sorted_files[i-1] > 1:
            islands += 1
    return islands


def _has_doubled_pawns(board: chess.Board, color: chess.Color) -> bool:
    """Check if color has doubled pawns."""
    file_counts: dict[int, int] = {}
    for sq in board.pieces(chess.PAWN, color):
        f = chess.square_file(sq)
        file_counts[f] = file_counts.get(f, 0) + 1
    return any(c >= 2 for c in file_counts.values())


def _has_isolated_pawn(board: chess.Board, color: chess.Color) -> bool:
    """Check if color has an isolated pawn."""
    pawn_files = set()
    for sq in board.pieces(chess.PAWN, color):
        pawn_files.add(chess.square_file(sq))
    
    for f in pawn_files:
        adjacent = {f - 1, f + 1}
        if not adjacent.intersection(pawn_files):
            return True
    return False


def _is_back_rank_weak(board: chess.Board, color: chess.Color) -> bool:
    """Check if the back rank is weak (king trapped without escape)."""
    king_sq = board.king(color)
    if king_sq is None:
        return False
    
    # Back rank for white is rank 0, for black is rank 7
    back_rank = 0 if color == chess.WHITE else 7
    king_rank = chess.square_rank(king_sq)
    
    # King must be on or near back rank
    if abs(king_rank - back_rank) > 1:
        return False
    
    # Check if king is blocked by own pieces
    escape_squares = []
    for dfile in [-1, 0, 1]:
        for drank in [-1, 0, 1]:
            if dfile == 0 and drank == 0:
                continue
            new_file = chess.square_file(king_sq) + dfile
            new_rank = king_rank + drank
            if 0 <= new_file <= 7 and 0 <= new_rank <= 7:
                sq = chess.square(new_file, new_rank)
                # Check if square is occupied by own piece
                piece = board.piece_at(sq)
                if piece is None or piece.color != color:
                    escape_squares.append(sq)
    
    # If very few escape squares and rooks/queens can attack back rank
    opponent = not color
    heavy_pieces = (
        len(board.pieces(chess.ROOK, opponent)) +
        len(board.pieces(chess.QUEEN, opponent))
    )
    
    return len(escape_squares) <= 1 and heavy_pieces > 0


def _has_fork_available(board: chess.Board, for_color: chess.Color) -> bool:
    """Check if a fork (knight/pawn attacking 2+ pieces) was available."""
    opponent = not for_color
    
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != for_color:
            continue
        
        if piece.piece_type not in (chess.KNIGHT, chess.PAWN):
            continue
        
        # Count valuable pieces this piece attacks
        attacked_value = 0
        attack_count = 0
        attacks = board.attacks(sq)
        for target_sq in attacks:
            target = board.piece_at(target_sq)
            if target and target.color == opponent:
                val = _piece_value(target.piece_type)
                if val >= 3 or target.piece_type == chess.KING:
                    attacked_value += val
                    attack_count += 1
        
        if attack_count >= 2 and attacked_value >= 6:
            return True
    
    return False


def _has_pin_or_skewer(board: chess.Board, for_color: chess.Color) -> bool:
    """Check if a pin or skewer exists on the board."""
    opponent = not for_color
    sliding_pieces = [chess.BISHOP, chess.ROOK, chess.QUEEN]
    
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != for_color or piece.piece_type not in sliding_pieces:
            continue
        
        # Check rays from this piece
        rays = board.attacks(sq)
        for target_sq in rays:
            target = board.piece_at(target_sq)
            if not target or target.color != opponent:
                continue
            
            # Check if there's another piece behind on the same ray
            direction = None
            file_diff = chess.square_file(target_sq) - chess.square_file(sq)
            rank_diff = chess.square_rank(target_sq) - chess.square_rank(sq)
            
            if file_diff != 0:
                file_diff = file_diff // abs(file_diff)
            if rank_diff != 0:
                rank_diff = rank_diff // abs(rank_diff)
            
            # Follow the ray
            check_sq = target_sq
            while True:
                check_sq = chess.square(
                    chess.square_file(check_sq) + file_diff,
                    chess.square_rank(check_sq) + rank_diff
                ) if (
                    0 <= chess.square_file(check_sq) + file_diff <= 7 and
                    0 <= chess.square_rank(check_sq) + rank_diff <= 7
                ) else None
                
                if check_sq is None:
                    break
                
                behind = board.piece_at(check_sq)
                if behind:
                    if behind.color == opponent and _piece_value(behind.piece_type) >= 3:
                        return True
                    break
    
    return False


def _has_discovered_attack(board_before: chess.Board, board_after: chess.Board, move: chess.Move, mover_color: chess.Color) -> bool:
    """Check if moving created a discovered attack."""
    opponent = not mover_color
    
    # After the move, check if any of our sliding pieces now attack valuable enemy pieces
    # that they weren't attacking before
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if not piece or piece.color != mover_color:
            continue
        if piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        if sq == move.to_square:  # Not the moved piece itself
            continue
        
        attacks_after = board_after.attacks(sq)
        attacks_before = board_before.attacks(sq)
        
        new_attacks = attacks_after - attacks_before
        for target_sq in new_attacks:
            target = board_after.piece_at(target_sq)
            if target and target.color == opponent and _piece_value(target.piece_type) >= 5:
                return True
    
    return False


def _missed_promotion(ctx: MoveContext) -> bool:
    """Check if a pawn promotion opportunity was missed."""
    if ctx.move is None:
        return False
    
    mover_color = not ctx.board_after.turn
    promotion_rank = 7 if mover_color == chess.WHITE else 0
    
    # Check if we had a pawn one step from promotion that we didn't push
    for sq in ctx.board_before.pieces(chess.PAWN, mover_color):
        pawn_rank = chess.square_rank(sq)
        pre_promo_rank = 6 if mover_color == chess.WHITE else 1
        
        if pawn_rank == pre_promo_rank:
            # There was a promotable pawn
            target_sq = chess.square(chess.square_file(sq), promotion_rank)
            promo_move = chess.Move(sq, target_sq, promotion=chess.QUEEN)
            
            if promo_move in ctx.board_before.legal_moves:
                # Promotion was available but we played something else
                if ctx.move.to_square != target_sq or not ctx.move.promotion:
                    return True
    
    return False


def _is_hanging_piece(ctx: MoveContext) -> bool:
    """Check if the moved piece is now hanging (under-defended)."""
    if ctx.move is None:
        return False

    moved_piece = ctx.board_after.piece_at(ctx.move.to_square)
    if moved_piece is None or moved_piece.piece_type in (chess.PAWN, chess.KING):
        return False

    # Who attacks/defends the piece now?
    opponent = ctx.board_after.turn  # opponent to move after our move
    mover_color = not opponent
    attackers = ctx.board_after.attackers(opponent, ctx.move.to_square)
    defenders = ctx.board_after.attackers(mover_color, ctx.move.to_square)

    # Basic hanging: more attackers than defenders
    if len(attackers) > 0 and len(attackers) > len(defenders):
        return True

    # SEE (Static Exchange Evaluation) approximation: check if we lose material
    if len(attackers) > 0:
        piece_val = _piece_value(moved_piece.piece_type)
        lowest_attacker_val = min(_piece_value(ctx.board_after.piece_at(sq).piece_type) 
                                   for sq in attackers if ctx.board_after.piece_at(sq))
        if piece_val > lowest_attacker_val:
            return True

    # Check if we left a piece en prise elsewhere
    for sq in chess.SQUARES:
        piece = ctx.board_after.piece_at(sq)
        if piece and piece.color == mover_color and piece.piece_type not in (chess.PAWN, chess.KING):
            att = ctx.board_after.attackers(opponent, sq)
            defs = ctx.board_after.attackers(mover_color, sq)
            if len(att) > 0 and len(att) > len(defs):
                # Check if this piece was safe before
                att_before = ctx.board_before.attackers(opponent, sq)
                defs_before = ctx.board_before.attackers(mover_color, sq)
                if len(att_before) <= len(defs_before):
                    return True

    return False


def _is_overlooked_recapture(ctx: MoveContext) -> bool:
    """Check if a simple recapture was available but not played."""
    if ctx.move is None:
        return False

    mover_color = not ctx.board_after.turn

    # Find valuable captures available before our move
    valuable_captures: list[chess.Move] = []
    for legal in ctx.board_before.legal_moves:
        if ctx.board_before.is_capture(legal):
            captured = ctx.board_before.piece_at(legal.to_square)
            if captured and _piece_value(captured.piece_type) >= 3:
                valuable_captures.append(legal)

    # If there were valuable captures and we didn't take any
    if valuable_captures and ctx.move not in valuable_captures:
        # Check if any capture was a recapture (opponent just took on that square)
        # For simplicity, any missed valuable capture counts
        return True

    return False


def _is_missed_tactic(ctx: MoveContext) -> bool:
    """Check if there was an obvious tactical shot available."""
    # Lower threshold to catch more missed tactics
    if ctx.cp_loss < 150:
        return False

    mover_color = not ctx.board_after.turn

    # Check for missed forks
    if _has_fork_available(ctx.board_before, mover_color):
        return True

    # Check for pins/skewers we could have exploited
    if _has_pin_or_skewer(ctx.board_before, mover_color):
        return True

    # Look for forcing moves that existed
    forcing_moves_available = 0
    for legal in ctx.board_before.legal_moves:
        # Check for checks
        if ctx.board_before.gives_check(legal):
            forcing_moves_available += 1
            if ctx.move != legal and ctx.cp_loss >= 200:
                return True

        # Check for high-value captures (rook or queen)
        if ctx.board_before.is_capture(legal):
            captured = ctx.board_before.piece_at(legal.to_square)
            if captured and _piece_value(captured.piece_type) >= 5:
                if ctx.move != legal:
                    return True
            # Also flag missed minor piece captures with large eval loss
            if captured and _piece_value(captured.piece_type) >= 3 and ctx.cp_loss >= 300:
                if ctx.move != legal:
                    return True

    # If there were multiple forcing moves available and large eval loss, likely missed tactic
    if forcing_moves_available >= 2 and ctx.cp_loss >= 300:
        return True

    # Large eval swing in middlegame often indicates tactical oversight
    if ctx.phase == "middlegame" and ctx.cp_loss >= 400:
        return True

    return False


def _is_king_safety_blunder(ctx: MoveContext) -> bool:
    """Check if king becomes more exposed after the move."""
    if ctx.move is None:
        return False

    mover = not ctx.board_after.turn  # who just moved
    king_sq_after = ctx.board_after.king(mover)
    king_sq_before = ctx.board_before.king(mover)

    if king_sq_after is None or king_sq_before is None:
        return False

    opponent = not mover

    # Count attackers on king
    attackers_after = len(ctx.board_after.attackers(opponent, king_sq_after))
    attackers_before = len(ctx.board_before.attackers(opponent, king_sq_before))

    if attackers_after > 0 and attackers_after > attackers_before:
        return True

    # Check if we weakened our king's pawn shield
    if ctx.board_before.has_castling_rights(mover):
        # We hadn't castled yet, but if we just moved a pawn in front of our king...
        moved_piece = ctx.board_before.piece_at(ctx.move.from_square)
        if moved_piece and moved_piece.piece_type == chess.PAWN:
            king_file = chess.square_file(king_sq_before)
            pawn_file = chess.square_file(ctx.move.from_square)
            if abs(king_file - pawn_file) <= 1:
                return True

    return False


def _is_back_rank_blunder(ctx: MoveContext) -> bool:
    """Check if we allowed a back rank threat or weakness."""
    if ctx.move is None:
        return False

    mover = not ctx.board_after.turn
    opponent = not mover

    # Check if back rank is now weak after our move
    was_weak = _is_back_rank_weak(ctx.board_before, mover)
    is_weak = _is_back_rank_weak(ctx.board_after, mover)

    if is_weak and not was_weak:
        return True

    # Check if we blocked our own back rank escape
    back_rank = 0 if mover == chess.WHITE else 7
    if ctx.move.to_square and chess.square_rank(ctx.move.to_square) == back_rank:
        king_sq = ctx.board_after.king(mover)
        if king_sq and chess.square_rank(king_sq) == back_rank:
            return True

    return False


def _is_pawn_structure_error(ctx: MoveContext) -> bool:
    """Check if we damaged our pawn structure unnecessarily."""
    if ctx.move is None:
        return False

    mover = not ctx.board_after.turn

    # Count pawn structure metrics before and after
    islands_before = _count_pawn_islands(ctx.board_before, mover)
    islands_after = _count_pawn_islands(ctx.board_after, mover)

    doubled_before = _has_doubled_pawns(ctx.board_before, mover)
    doubled_after = _has_doubled_pawns(ctx.board_after, mover)

    isolated_before = _has_isolated_pawn(ctx.board_before, mover)
    isolated_after = _has_isolated_pawn(ctx.board_after, mover)

    # Only count if we made structure worse
    structure_damage = 0
    if islands_after > islands_before:
        structure_damage += 1
    if doubled_after and not doubled_before:
        structure_damage += 1
    if isolated_after and not isolated_before:
        structure_damage += 1

    # Only flag as pawn structure error if significant and large cp loss
    return structure_damage >= 2 and ctx.cp_loss >= 150


def _is_piece_activity_error(ctx: MoveContext) -> bool:
    """Check if we trapped our own piece or reduced activity significantly."""
    if ctx.move is None:
        return False

    mover = not ctx.board_after.turn

    # Check if we trapped one of our pieces
    for sq in chess.SQUARES:
        piece = ctx.board_after.piece_at(sq)
        if piece and piece.color == mover and piece.piece_type not in (chess.PAWN, chess.KING):
            if _is_piece_trapped(ctx.board_after, sq):
                # Was it trapped before?
                if not _is_piece_trapped(ctx.board_before, sq):
                    return True

    # Check if the moved piece itself got trapped
    if ctx.move.to_square:
        moved_piece = ctx.board_after.piece_at(ctx.move.to_square)
        if moved_piece and moved_piece.piece_type not in (chess.PAWN, chess.KING):
            if _is_piece_trapped(ctx.board_after, ctx.move.to_square):
                return True

    return False


def _is_promotion_oversight(ctx: MoveContext) -> bool:
    """Check if we missed a pawn promotion."""
    return _missed_promotion(ctx)


def _is_discovered_attack_missed(ctx: MoveContext) -> bool:
    """Check if opponent can now deliver a discovered attack on us."""
    if ctx.move is None:
        return False

    opponent = ctx.board_after.turn

    # Check if our move enabled opponent's discovered attack
    if _has_discovered_attack(ctx.board_before, ctx.board_after, ctx.move, opponent):
        return True

    return False


def _is_endgame_technique_error(ctx: MoveContext) -> bool:
    """Check if this is an endgame technique error."""
    if ctx.phase != "endgame":
        return False

    # Low material + large swing = technique error
    material = _total_material(ctx.board_after)
    if material <= 13 and ctx.cp_loss >= 150:
        return True

    # King activity in endgame - check if we moved king away from action
    mover = not ctx.board_after.turn
    king_sq_before = ctx.board_before.king(mover)
    king_sq_after = ctx.board_after.king(mover)

    if king_sq_before and king_sq_after and material <= 15:
        # In endgame, king should generally be active
        # Check if we're moving king to edge (usually bad)
        rank_after = chess.square_rank(king_sq_after)
        file_after = chess.square_file(king_sq_after)
        is_edge = rank_after in (0, 7) or file_after in (0, 7)

        rank_before = chess.square_rank(king_sq_before)
        file_before = chess.square_file(king_sq_before)
        was_edge = rank_before in (0, 7) or file_before in (0, 7)

        if is_edge and not was_edge and ctx.cp_loss >= 100:
            return True

    return False


def _is_opening_error(ctx: MoveContext) -> bool:
    """Check if this is an opening theory mistake."""
    if ctx.phase != "opening":
        return False

    # Early game + large swing = opening error
    if ctx.move_number <= 15 and ctx.cp_loss >= 100:
        return True

    return False


def _is_time_pressure_blunder(ctx: MoveContext) -> bool:
    """Check if blunder occurred under time pressure."""
    if ctx.clock_seconds is None:
        return False
    return ctx.clock_seconds <= TIME_PRESSURE_SECONDS


def _fallback_classification(ctx: MoveContext) -> str:
    """Fallback classification when board heuristics don't match.
    
    Uses eval magnitude, phase, and move characteristics to infer likely cause.
    """
    cp_loss = ctx.cp_loss
    phase = ctx.phase
    move_num = ctx.move_number
    san = ctx.san or ""
    
    # Very large swings (500+ cp) usually indicate major tactical oversights
    if cp_loss >= 500:
        # If in endgame, likely technique
        if phase == "endgame":
            return "endgame_technique"
        # Otherwise, most likely a missed tactic
        return "missed_tactic"
    
    # Medium-large swings (300-500 cp)
    if cp_loss >= 300:
        # Opening errors in first 15 moves
        if phase == "opening" or move_num <= 15:
            return "opening_error"
        
        # Endgame technique in endgame
        if phase == "endgame":
            return "endgame_technique"
        
        # Check move characteristics for hints
        # Piece moves in middlegame are often hanging pieces or tactical misses
        if san and san[0].isupper() and san[0] not in "KQRBN":
            # Pawn moves (lowercase starting)
            pass
        elif san and san[0] in "QRBN":
            # Major/minor piece moves - often hanging or missed tactic
            return "hanging_piece"
        
        # Default for middlegame large swings
        return "missed_tactic"
    
    # Smaller blunders (100-300 cp) - could be positional
    if phase == "opening":
        return "opening_error"
    elif phase == "endgame":
        return "endgame_technique"
    else:
        # Middlegame moderate errors - likely piece activity or positional
        return "piece_activity"


def classify_single_blunder(ctx: MoveContext) -> str:
    """Classify a single blunder into a category.
    
    Priority order matters - check most specific/reliable patterns first.
    Enhanced heuristics include back-rank, pawn structure, piece activity,
    promotion oversight, and discovered attack detection.
    
    Falls back to inference based on eval swing and phase when board analysis is limited.
    """
    # Time pressure (if clock data exists) - most definitive
    if _is_time_pressure_blunder(ctx):
        return "time_pressure"

    # Phase-specific errors first (opening/endgame)
    if _is_endgame_technique_error(ctx):
        return "endgame_technique"

    if _is_opening_error(ctx):
        return "opening_error"

    # Tactical patterns - check specific patterns before generic "missed tactic"
    
    # Promotion oversight - very specific
    if _is_promotion_oversight(ctx):
        return "promotion_oversight"

    # Back rank weakness - specific pattern
    if _is_back_rank_blunder(ctx):
        return "back_rank"

    # Hanging piece - common and clear
    if _is_hanging_piece(ctx):
        return "hanging_piece"

    # Discovered attack allowed
    if _is_discovered_attack_missed(ctx):
        return "discovered_attack"

    # King safety
    if _is_king_safety_blunder(ctx):
        return "king_safety"

    # Missed tactic (forks, pins, skewers, forcing moves)
    if _is_missed_tactic(ctx):
        return "missed_tactic"

    # Overlooked recapture
    if _is_overlooked_recapture(ctx):
        return "overlooked_recapture"

    # Positional errors
    if _is_piece_activity_error(ctx):
        return "piece_activity"

    if _is_pawn_structure_error(ctx):
        return "pawn_structure"

    # Fallback classification based on cp_loss magnitude and phase
    # Large swings usually indicate tactical misses
    return _fallback_classification(ctx)


def analyze_blunders(games_data: list[dict[str, Any]]) -> BlunderClassification:
    """Analyze all games and classify blunders.

    Args:
        games_data: List of game dicts with move_evals, each containing:
            - move_san, cp_loss, phase, eval_before, eval_after, fen_before, fen_after, clock_seconds

    Returns:
        BlunderClassification with categorized blunders and statistics.
    """
    result = BlunderClassification()
    by_type = BlunderByType()
    by_phase: dict[str, int] = {"opening": 0, "middlegame": 0, "endgame": 0}
    first_blunder_moves: list[int] = []
    total_moves = 0
    examples: list[BlunderExample] = []

    for game_idx, game in enumerate(games_data):
        move_evals = game.get("move_evals", []) or []
        first_blunder_in_game: int | None = None
        
        # Build board state by replaying moves for better FEN reconstruction
        running_board = chess.Board()
        move_sans_so_far: list[str] = []

        for move_idx, m in enumerate(move_evals):
            total_moves += 1
            cp_loss = int(m.get("cp_loss") or 0)
            san = str(m.get("san") or m.get("move_san") or "")
            
            # Track moves for reconstruction
            if san:
                move_sans_so_far.append(san)

            # Skip mate positions
            eval_before = m.get("eval_before")
            eval_after = m.get("eval_after")
            if eval_before is not None and abs(int(eval_before)) >= MATE_CP_THRESHOLD:
                # Still update running board
                try:
                    running_board.push_san(san)
                except Exception:
                    pass
                continue
            if eval_after is not None and abs(int(eval_after)) >= MATE_CP_THRESHOLD:
                try:
                    running_board.push_san(san)
                except Exception:
                    pass
                continue

            if cp_loss < MISTAKE_CP_THRESHOLD:
                try:
                    running_board.push_san(san)
                except Exception:
                    pass
                continue

            # Count mistakes
            if cp_loss >= MISTAKE_CP_THRESHOLD:
                result.total_mistakes += 1

            # Only classify blunders (>= 300cp)
            if cp_loss < BLUNDER_CP_THRESHOLD:
                try:
                    running_board.push_san(san)
                except Exception:
                    pass
                continue

            result.total_blunders += 1

            # Build context for classification
            move_number = int(m.get("move_num") or m.get("move_number") or 1)
            phase = str(m.get("phase") or "middlegame")
            fen_before = m.get("fen_before")
            fen_after = m.get("fen_after") or m.get("fen")
            clock = m.get("clock_seconds")

            # Try to reconstruct boards - use running_board as fallback
            try:
                if fen_before:
                    board_before = chess.Board(fen_before)
                else:
                    # Use running board state (position before this move)
                    board_before = running_board.copy()
                
                if fen_after:
                    board_after = chess.Board(fen_after)
                elif san:
                    board_after = board_before.copy()
                    move_obj_temp = board_after.parse_san(san)
                    board_after.push(move_obj_temp)
                else:
                    board_after = board_before.copy()
                
                move_obj = board_before.parse_san(san) if san else None
            except Exception:
                board_before = running_board.copy() if running_board else chess.Board()
                board_after = board_before.copy()
                move_obj = None

            ctx = MoveContext(
                game_index=game_idx + 1,
                move_number=move_number,
                san=san,
                move=move_obj,
                board_before=board_before,
                board_after=board_after,
                eval_before=int(eval_before) if eval_before is not None else None,
                eval_after=int(eval_after) if eval_after is not None else None,
                cp_loss=cp_loss,
                phase=phase,
                clock_seconds=int(clock) if clock is not None else None,
                fen_before=fen_before,
                move_sans_so_far=move_sans_so_far.copy(),
            )

            blunder_type = classify_single_blunder(ctx)
            
            # Update running board for next iteration
            try:
                if san:
                    running_board.push_san(san)
            except Exception:
                pass

            # Update counts - now handles all enhanced blunder types
            if blunder_type == "hanging_piece":
                by_type.hanging_piece += 1
            elif blunder_type == "missed_tactic":
                by_type.missed_tactic += 1
            elif blunder_type == "endgame_technique":
                by_type.endgame_technique += 1
            elif blunder_type == "opening_error":
                by_type.opening_error += 1
            elif blunder_type == "king_safety":
                by_type.king_safety += 1
            elif blunder_type == "time_pressure":
                by_type.time_pressure += 1
            elif blunder_type == "overlooked_recapture":
                by_type.overlooked_recapture += 1
            elif blunder_type == "back_rank":
                by_type.back_rank += 1
            elif blunder_type == "pawn_structure":
                by_type.pawn_structure += 1
            elif blunder_type == "piece_activity":
                by_type.piece_activity += 1
            elif blunder_type == "promotion_oversight":
                by_type.promotion_oversight += 1
            elif blunder_type == "discovered_attack":
                by_type.discovered_attack += 1
            else:
                by_type.unknown += 1

            # Phase distribution
            if phase in by_phase:
                by_phase[phase] += 1

            # Track first blunder per game
            if first_blunder_in_game is None:
                first_blunder_in_game = move_number
                first_blunder_moves.append(move_number)

            # Collect examples
            if len(examples) < 10:
                # Determine color from move index (even = white, odd = black)
                color = "white" if move_idx % 2 == 0 else "black"
                examples.append(BlunderExample(
                    game_index=game_idx + 1,
                    move_number=move_number,
                    san=san,
                    blunder_type=blunder_type,
                    cp_loss=cp_loss,
                    phase=phase,
                    fen_before=fen_before,
                    color=color,
                ))

    # Compute aggregates
    result.by_type = by_type
    result.by_phase = by_phase

    if first_blunder_moves:
        result.first_blunder_avg_move = sum(first_blunder_moves) / len(first_blunder_moves)

    if total_moves > 0:
        result.blunder_rate_per_100_moves = (result.total_blunders / total_moves) * 100

    result.examples = examples

    return result
