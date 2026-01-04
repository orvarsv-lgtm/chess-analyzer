"""
Puzzle Explanation Engine - Coach-Quality Move Explanations

Generates high-quality, human-readable explanations for chess puzzles
using pure chess logic and engine signals. No AI/LLM - fully deterministic.

Design Philosophy:
- Accuracy > verbosity
- Clarity > cleverness  
- Determinism > style
- Think like a strong human chess coach writing annotations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple
import chess


# =============================================================================
# TACTICAL MOTIF DEFINITIONS
# =============================================================================


class TacticalMotif(str, Enum):
    """All recognized tactical motifs."""
    FORK = "fork"
    PIN_ABSOLUTE = "pin_absolute"  # Pinned to king
    PIN_RELATIVE = "pin_relative"  # Pinned to valuable piece
    SKEWER = "skewer"
    DISCOVERED_ATTACK = "discovered_attack"
    DISCOVERED_CHECK = "discovered_check"
    DOUBLE_CHECK = "double_check"
    REMOVING_DEFENDER = "removing_defender"
    BACK_RANK_THREAT = "back_rank_threat"
    BACK_RANK_MATE = "back_rank_mate"
    PROMOTION_THREAT = "promotion_threat"
    MATE_THREAT = "mate_threat"
    CHECKMATE = "checkmate"
    ZWISCHENZUG = "zwischenzug"
    TRAPPED_PIECE = "trapped_piece"
    OVERLOADED_PIECE = "overloaded_piece"
    DEFLECTION = "deflection"
    ATTRACTION = "attraction"
    CLEARANCE = "clearance"
    X_RAY_ATTACK = "x_ray_attack"


# Piece values for material calculations
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


# =============================================================================
# EXPLANATION DATA STRUCTURE
# =============================================================================


@dataclass
class PuzzleExplanation:
    """
    Structured explanation of why a chess move is correct.
    
    All fields are deterministically computed from board analysis.
    """
    # Primary tactical idea (most important motif)
    primary_motif: Optional[TacticalMotif] = None
    
    # Secondary tactical ideas
    secondary_motifs: List[TacticalMotif] = field(default_factory=list)
    
    # Threats created by the move
    threats_created: List[str] = field(default_factory=list)
    
    # Opponent threats that were stopped
    threats_stopped: List[str] = field(default_factory=list)
    
    # Material outcome description
    material_outcome: str = ""
    
    # King safety impact
    king_safety_impact: str = ""
    
    # Phase-specific guidance
    phase_specific_guidance: str = ""
    
    # The final human-readable summary
    human_readable_summary: str = ""
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "primary_motif": self.primary_motif.value if self.primary_motif else None,
            "secondary_motifs": [m.value for m in self.secondary_motifs],
            "threats_created": self.threats_created,
            "threats_stopped": self.threats_stopped,
            "material_outcome": self.material_outcome,
            "king_safety_impact": self.king_safety_impact,
            "phase_specific_guidance": self.phase_specific_guidance,
            "human_readable_summary": self.human_readable_summary,
        }


# =============================================================================
# TACTICAL MOTIF DETECTION
# =============================================================================


def detect_fork(board_after: chess.Board, attacker_color: chess.Color, 
                moving_piece_square: int) -> Tuple[bool, List[Tuple[int, int, bool]]]:
    """
    Detect if a fork exists (one piece attacks 2+ valuable pieces) AND wins material.
    
    A fork only "wins material" if:
    - One forked piece is the King (must move), OR
    - The forking piece is worth less than a forked piece that's undefended, OR
    - The forking piece is worth less than a forked piece (even if defended)
    
    For example:
    - Pawn forks King + defended Knight = wins Knight (pawn < knight)
    - Queen forks King + defended Knight = NOT winning (queen > knight)
    - Queen forks King + Queen = wins Queen (equal trade)
    
    Returns:
        (is_winning_fork, list of (piece_type, square, is_defended) tuples)
    """
    forking_piece = board_after.piece_at(moving_piece_square)
    if not forking_piece:
        return False, []
    
    forking_value = PIECE_VALUES.get(forking_piece.piece_type, 0)
    attacked_valuable = []
    defender_color = not attacker_color
    
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece and piece.color != attacker_color:
            # Check if this square is attacked by the piece that just moved
            if board_after.is_attacked_by(attacker_color, square):
                # Check if the attack comes from the moved piece
                attackers = board_after.attackers(attacker_color, square)
                if moving_piece_square in attackers:
                    # Only count valuable pieces (not pawns, unless it's the king)
                    if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, 
                                           chess.QUEEN, chess.KING):
                        is_defended = board_after.is_attacked_by(defender_color, square)
                        attacked_valuable.append((piece.piece_type, square, is_defended))
    
    # Need at least 2 pieces attacked
    if len(attacked_valuable) < 2:
        return False, attacked_valuable
    
    # Check if this fork actually wins material
    # A fork wins if: King is forked (must move) AND at least one other piece can be won
    has_king = any(pt == chess.KING for pt, sq, defended in attacked_valuable)
    
    if has_king:
        # King must move - check if we can profitably capture something else
        for pt, sq, is_defended in attacked_valuable:
            if pt != chess.KING:
                piece_value = PIECE_VALUES.get(pt, 0)
                if not is_defended:
                    # Undefended piece = free capture
                    return True, attacked_valuable
                elif forking_value < piece_value:
                    # Our piece is worth less than theirs = winning exchange
                    return True, attacked_valuable
                elif forking_value == piece_value and pt == chess.QUEEN:
                    # Trading queens is significant
                    return True, attacked_valuable
        # King is forked but other pieces are defended and worth less than forker
        # This is NOT a winning fork (e.g., Queen forks King + defended Knight)
        return False, attacked_valuable
    else:
        # No king - check if any piece is undefended or worth more than forker
        for pt, sq, is_defended in attacked_valuable:
            piece_value = PIECE_VALUES.get(pt, 0)
            if not is_defended:
                return True, attacked_valuable
            elif forking_value < piece_value:
                return True, attacked_valuable
        return False, attacked_valuable


def detect_pin(board: chess.Board, move: chess.Move) -> Tuple[bool, bool, Optional[str]]:
    """
    Detect if the move creates a pin.
    
    Returns:
        (creates_absolute_pin, creates_relative_pin, description)
    """
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return False, False, None
    
    attacker_color = moving_piece.color
    defender_color = not attacker_color
    
    # Find opponent's king
    king_square = board_after.king(defender_color)
    if king_square is None:
        return False, False, None
    
    # Check for pins created by sliding pieces
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece and piece.color == attacker_color:
            if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Check if there's a pin line to the king
                pin_info = _check_pin_line(board_after, square, king_square, defender_color)
                if pin_info:
                    pinned_piece, is_absolute = pin_info
                    pinned_name = chess.piece_name(pinned_piece.piece_type).title()
                    if is_absolute:
                        return True, False, f"The {pinned_name} is pinned to the King"
                    else:
                        return False, True, f"The {pinned_name} is pinned"
    
    return False, False, None


def _check_pin_line(board: chess.Board, attacker_sq: int, target_sq: int, 
                    defender_color: chess.Color) -> Optional[Tuple[chess.Piece, bool]]:
    """Check if there's a pin along the line from attacker to target."""
    attacker = board.piece_at(attacker_sq)
    if not attacker:
        return None
    
    # Get the ray between attacker and target
    if attacker_sq == target_sq:
        return None
    
    # Determine ray direction
    file_diff = chess.square_file(target_sq) - chess.square_file(attacker_sq)
    rank_diff = chess.square_rank(target_sq) - chess.square_rank(attacker_sq)
    
    # Normalize direction
    if file_diff != 0:
        file_step = file_diff // abs(file_diff)
    else:
        file_step = 0
    if rank_diff != 0:
        rank_step = rank_diff // abs(rank_diff)
    else:
        rank_step = 0
    
    # Check piece can move in this direction
    is_diagonal = abs(file_diff) == abs(rank_diff) and file_diff != 0
    is_straight = (file_diff == 0 or rank_diff == 0) and (file_diff != 0 or rank_diff != 0)
    
    if attacker.piece_type == chess.BISHOP and not is_diagonal:
        return None
    if attacker.piece_type == chess.ROOK and not is_straight:
        return None
    if attacker.piece_type == chess.QUEEN and not (is_diagonal or is_straight):
        return None
    
    # Walk along the ray looking for pinned piece
    current_file = chess.square_file(attacker_sq) + file_step
    current_rank = chess.square_rank(attacker_sq) + rank_step
    pinned_piece = None
    pinned_sq = None
    
    while 0 <= current_file <= 7 and 0 <= current_rank <= 7:
        current_sq = chess.square(current_file, current_rank)
        
        if current_sq == target_sq:
            # Reached the target (king)
            if pinned_piece:
                # Found a pin - check if target is king (absolute) or other (relative)
                target_piece = board.piece_at(target_sq)
                is_absolute = target_piece and target_piece.piece_type == chess.KING
                return pinned_piece, is_absolute
            return None
        
        piece_at_sq = board.piece_at(current_sq)
        if piece_at_sq:
            if piece_at_sq.color == defender_color:
                if pinned_piece is None:
                    pinned_piece = piece_at_sq
                    pinned_sq = current_sq
                else:
                    # Two pieces in the way, no pin
                    return None
            else:
                # Our own piece blocks
                return None
        
        current_file += file_step
        current_rank += rank_step
    
    return None


def detect_skewer(board: chess.Board, move: chess.Move) -> Tuple[bool, Optional[str]]:
    """
    Detect if the move creates a skewer (attack on valuable piece that must move,
    exposing a piece behind it).
    """
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return False, None
    
    if moving_piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False, None
    
    attacker_color = moving_piece.color
    defender_color = not attacker_color
    
    # Check each direction from the piece
    directions = []
    if moving_piece.piece_type in (chess.BISHOP, chess.QUEEN):
        directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
    if moving_piece.piece_type in (chess.ROOK, chess.QUEEN):
        directions.extend([(1, 0), (-1, 0), (0, 1), (0, -1)])
    
    for df, dr in directions:
        front_piece = None
        front_sq = None
        back_piece = None
        
        current_file = chess.square_file(move.to_square) + df
        current_rank = chess.square_rank(move.to_square) + dr
        
        while 0 <= current_file <= 7 and 0 <= current_rank <= 7:
            current_sq = chess.square(current_file, current_rank)
            piece = board_after.piece_at(current_sq)
            
            if piece:
                if piece.color == defender_color:
                    if front_piece is None:
                        front_piece = piece
                        front_sq = current_sq
                    else:
                        back_piece = piece
                        break
                else:
                    break
            
            current_file += df
            current_rank += dr
        
        # Check for skewer: front piece more valuable, must move
        if front_piece and back_piece:
            front_val = PIECE_VALUES.get(front_piece.piece_type, 0)
            back_val = PIECE_VALUES.get(back_piece.piece_type, 0)
            
            if front_val >= back_val and front_piece.piece_type == chess.KING:
                # King in front - absolute skewer
                back_name = chess.piece_name(back_piece.piece_type).title()
                return True, f"Skewer! The King must move, exposing the {back_name}"
            elif front_val > back_val:
                front_name = chess.piece_name(front_piece.piece_type).title()
                back_name = chess.piece_name(back_piece.piece_type).title()
                return True, f"Skewer on the {front_name}, winning the {back_name} behind"
    
    return False, None


def detect_discovered_attack(board: chess.Board, move: chess.Move) -> Tuple[bool, bool, Optional[str]]:
    """
    Detect discovered attacks and discovered checks.
    
    Returns:
        (is_discovered_attack, is_discovered_check, description)
    """
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return False, False, None
    
    attacker_color = moving_piece.color
    defender_color = not attacker_color
    
    # Check what pieces were behind the moving piece that now have new attack lines
    board_after = board.copy()
    board_after.push(move)
    
    # Find sliding pieces that now attack through the vacated square
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.color == attacker_color and square != move.from_square:
            if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Check if moving piece was blocking this piece's attack
                # and now a valuable target is exposed
                discovery = _check_discovery(board, board_after, square, 
                                            move.from_square, defender_color)
                if discovery:
                    return discovery
    
    return False, False, None


def _check_discovery(board_before: chess.Board, board_after: chess.Board,
                     attacker_sq: int, vacated_sq: int, 
                     defender_color: chess.Color) -> Optional[Tuple[bool, bool, str]]:
    """Check if vacating a square created a discovered attack."""
    attacker = board_after.piece_at(attacker_sq)
    if not attacker:
        return None
    
    # Get squares the attacker can reach through the vacated square
    file_diff = chess.square_file(vacated_sq) - chess.square_file(attacker_sq)
    rank_diff = chess.square_rank(vacated_sq) - chess.square_rank(attacker_sq)
    
    if file_diff == 0 and rank_diff == 0:
        return None
    
    # Check if attacker can move in this direction
    is_diagonal = abs(file_diff) == abs(rank_diff) and file_diff != 0
    is_straight = (file_diff == 0 or rank_diff == 0)
    
    if attacker.piece_type == chess.BISHOP and not is_diagonal:
        return None
    if attacker.piece_type == chess.ROOK and not is_straight:
        return None
    
    # Normalize direction
    if file_diff != 0:
        file_step = file_diff // abs(file_diff)
    else:
        file_step = 0
    if rank_diff != 0:
        rank_step = rank_diff // abs(rank_diff)
    else:
        rank_step = 0
    
    # Check that vacated square was actually blocking
    blocked_before = False
    current_file = chess.square_file(attacker_sq) + file_step
    current_rank = chess.square_rank(attacker_sq) + rank_step
    
    while 0 <= current_file <= 7 and 0 <= current_rank <= 7:
        current_sq = chess.square(current_file, current_rank)
        if current_sq == vacated_sq:
            blocked_before = True
            break
        if board_before.piece_at(current_sq):
            break
        current_file += file_step
        current_rank += rank_step
    
    if not blocked_before:
        return None
    
    # Now check what we're attacking through the vacated square
    current_file = chess.square_file(vacated_sq) + file_step
    current_rank = chess.square_rank(vacated_sq) + rank_step
    
    while 0 <= current_file <= 7 and 0 <= current_rank <= 7:
        current_sq = chess.square(current_file, current_rank)
        target = board_after.piece_at(current_sq)
        
        if target:
            if target.color == defender_color:
                target_name = chess.piece_name(target.piece_type).title()
                attacker_name = chess.piece_name(attacker.piece_type).title()
                
                if target.piece_type == chess.KING:
                    return True, True, f"Discovered check by the {attacker_name}"
                else:
                    return True, False, f"Discovered attack on the {target_name} by the {attacker_name}"
            break
        
        current_file += file_step
        current_rank += rank_step
    
    return None


def detect_back_rank_threat(board: chess.Board, move: chess.Move) -> Tuple[bool, bool, Optional[str]]:
    """
    Detect back-rank mate threats or actual back-rank mates.
    
    Returns:
        (is_threat, is_mate, description)
    """
    board_after = board.copy()
    board_after.push(move)
    
    if board_after.is_checkmate():
        # Check if it's a back-rank mate
        defender_color = board_after.turn
        king_sq = board_after.king(defender_color)
        if king_sq is not None:
            king_rank = chess.square_rank(king_sq)
            if (defender_color == chess.WHITE and king_rank == 0) or \
               (defender_color == chess.BLACK and king_rank == 7):
                return True, True, "Back-rank checkmate!"
    
    # Check for back-rank mate threat (mate in 1)
    moving_piece = board.piece_at(move.from_square)
    if moving_piece and moving_piece.piece_type in (chess.ROOK, chess.QUEEN):
        attacker_color = moving_piece.color
        defender_color = not attacker_color
        
        # Check if opponent's back rank is weak
        back_rank = 0 if defender_color == chess.WHITE else 7
        king_sq = board_after.king(defender_color)
        
        if king_sq is not None:
            king_rank = chess.square_rank(king_sq)
            if king_rank == back_rank:
                # King on back rank - check if trapped
                escape_squares = 0
                for sq in chess.SQUARES:
                    if chess.square_rank(sq) == back_rank + (1 if defender_color == chess.WHITE else -1):
                        if abs(chess.square_file(sq) - chess.square_file(king_sq)) <= 1:
                            if not board_after.piece_at(sq) or board_after.piece_at(sq).color != defender_color:
                                escape_squares += 1
                
                if escape_squares == 0:
                    return True, False, "Creates a back-rank mate threat"
    
    return False, False, None


def detect_promotion_threat(board: chess.Board, move: chess.Move) -> Tuple[bool, Optional[str]]:
    """Detect pawn promotion or unstoppable promotion threats."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece or moving_piece.piece_type != chess.PAWN:
        return False, None
    
    to_rank = chess.square_rank(move.to_square)
    
    # Actual promotion
    if (moving_piece.color == chess.WHITE and to_rank == 7) or \
       (moving_piece.color == chess.BLACK and to_rank == 0):
        promo_piece = move.promotion
        if promo_piece:
            promo_name = chess.piece_name(promo_piece).title()
            return True, f"Promotes to a {promo_name}"
        return True, "Pawn promotes"
    
    # Check for unstoppable passed pawn
    board_after = board.copy()
    board_after.push(move)
    
    if _is_passed_pawn(board_after, move.to_square):
        squares_to_promote = 7 - to_rank if moving_piece.color == chess.WHITE else to_rank
        if squares_to_promote <= 2:
            return True, "Creates an unstoppable passed pawn"
    
    return False, None


def _is_passed_pawn(board: chess.Board, pawn_sq: int) -> bool:
    """Check if a pawn is passed (no enemy pawns can block or capture it)."""
    pawn = board.piece_at(pawn_sq)
    if not pawn or pawn.piece_type != chess.PAWN:
        return False
    
    pawn_file = chess.square_file(pawn_sq)
    pawn_rank = chess.square_rank(pawn_sq)
    
    # Check files that could block: same file and adjacent files
    for file in [pawn_file - 1, pawn_file, pawn_file + 1]:
        if not 0 <= file <= 7:
            continue
        
        # Check ranks ahead of the pawn
        if pawn.color == chess.WHITE:
            ranks_to_check = range(pawn_rank + 1, 8)
        else:
            ranks_to_check = range(pawn_rank - 1, -1, -1)
        
        for rank in ranks_to_check:
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.PAWN and piece.color != pawn.color:
                return False
    
    return True


def detect_mate_threat(board: chess.Board, move: chess.Move) -> Tuple[bool, int, Optional[str]]:
    """
    Detect checkmate or mate threats.
    
    Returns:
        (is_mate_threat, mate_in_n, description)
    """
    board_after = board.copy()
    board_after.push(move)
    
    if board_after.is_checkmate():
        return True, 0, "Checkmate!"
    
    # Check for mate in 1 threat
    attacker_color = board.turn
    for response in board_after.legal_moves:
        board_response = board_after.copy()
        board_response.push(response)
        
        # After opponent's response, can we mate?
        for mate_move in board_response.legal_moves:
            board_final = board_response.copy()
            board_final.push(mate_move)
            if board_final.is_checkmate():
                return True, 1, "Threatens checkmate"
    
    return False, -1, None


def detect_removing_defender(board: chess.Board, move: chess.Move) -> Tuple[bool, Optional[str]]:
    """Detect if the move removes a key defender."""
    captured = board.piece_at(move.to_square)
    if not captured:
        return False, None
    
    board_after = board.copy()
    board_after.push(move)
    
    attacker_color = board.turn
    
    # Check if any valuable piece is now undefended after the capture
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece and piece.color != attacker_color:
            if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Was this piece defended by the captured piece?
                was_defended = board.is_attacked_by(not attacker_color, square)
                is_defended = board_after.is_attacked_by(not attacker_color, square)
                is_attacked = board_after.is_attacked_by(attacker_color, square)
                
                if was_defended and not is_defended and is_attacked:
                    piece_name = chess.piece_name(piece.piece_type).title()
                    captured_name = chess.piece_name(captured.piece_type).title()
                    return True, f"Captures the {captured_name}, removing the defender of the {piece_name}"
    
    return False, None


def detect_trapped_piece(board: chess.Board, move: chess.Move) -> Tuple[bool, Optional[str]]:
    """Detect if the move traps an opponent's piece."""
    board_after = board.copy()
    board_after.push(move)
    
    attacker_color = board.turn
    defender_color = not attacker_color
    
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece and piece.color == defender_color:
            if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Check if piece is attacked
                if board_after.is_attacked_by(attacker_color, square):
                    # Check if piece has any safe squares
                    has_escape = False
                    for move in board_after.legal_moves:
                        if move.from_square == square:
                            board_test = board_after.copy()
                            board_test.push(move)
                            if not board_test.is_attacked_by(attacker_color, move.to_square):
                                has_escape = True
                                break
                    
                    if not has_escape:
                        piece_name = chess.piece_name(piece.piece_type).title()
                        return True, f"Traps the {piece_name}"
    
    return False, None


# =============================================================================
# THREAT ANALYSIS
# =============================================================================


def analyze_opponent_threats(board: chess.Board) -> List[str]:
    """
    Analyze what threats the opponent has in the current position.
    """
    threats = []
    
    # Whose turn is it? The opponent just moved, so we analyze their threats
    opponent_color = not board.turn
    our_color = board.turn
    
    # Check for mate threats
    for move in board.legal_moves:
        board_after = board.copy()
        board_after.push(move)
        if board_after.is_checkmate():
            threats.append("Checkmate is threatened")
            break
    
    # Check for hanging pieces
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.color == our_color:
            if piece.piece_type != chess.PAWN:
                is_attacked = board.is_attacked_by(opponent_color, square)
                is_defended = board.is_attacked_by(our_color, square)
                
                if is_attacked and not is_defended:
                    piece_name = chess.piece_name(piece.piece_type).title()
                    threats.append(f"The {piece_name} on {chess.square_name(square)} is hanging")
    
    return threats


def analyze_threats_created(board: chess.Board, move: chess.Move) -> List[str]:
    """Analyze what new threats the move creates."""
    threats = []
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return threats
    
    attacker_color = moving_piece.color
    defender_color = not attacker_color
    
    # Check what pieces are now attacked
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece and piece.color == defender_color:
            was_attacked = board.is_attacked_by(attacker_color, square)
            is_attacked = board_after.is_attacked_by(attacker_color, square)
            is_defended = board_after.is_attacked_by(defender_color, square)
            
            if is_attacked and not was_attacked:
                piece_name = chess.piece_name(piece.piece_type).title()
                if not is_defended:
                    threats.append(f"Attacks the undefended {piece_name}")
                elif PIECE_VALUES.get(piece.piece_type, 0) > PIECE_VALUES.get(moving_piece.piece_type, 0):
                    threats.append(f"Attacks the {piece_name}")
    
    return threats


# =============================================================================
# MATERIAL ANALYSIS
# =============================================================================


def analyze_material_outcome(board: chess.Board, move: chess.Move) -> str:
    """Analyze the material outcome of the move."""
    captured = board.piece_at(move.to_square)
    moving_piece = board.piece_at(move.from_square)
    
    if not moving_piece:
        return ""
    
    if not captured:
        # Check for promotion
        if move.promotion:
            promo_name = chess.piece_name(move.promotion).title()
            return f"Gains a {promo_name} through promotion"
        return ""
    
    board_after = board.copy()
    board_after.push(move)
    
    captured_name = chess.piece_name(captured.piece_type).title()
    captured_value = PIECE_VALUES.get(captured.piece_type, 0)
    moving_value = PIECE_VALUES.get(moving_piece.piece_type, 0)
    
    # Check if capture is safe
    is_recapturable = board_after.is_attacked_by(board_after.turn, move.to_square)
    
    if not is_recapturable:
        return f"Wins the {captured_name}"
    else:
        moving_name = chess.piece_name(moving_piece.piece_type).title()
        if captured_value > moving_value:
            diff = (captured_value - moving_value) // 100
            return f"Wins the exchange ({captured_name} for {moving_name})"
        elif captured_value == moving_value:
            return f"Trades {moving_name} for {captured_name}"
        else:
            return ""


# =============================================================================
# PHASE-SPECIFIC GUIDANCE
# =============================================================================


def get_phase_guidance(board: chess.Board, move: chess.Move, phase: str) -> str:
    """Generate phase-specific coaching advice."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return ""
    
    board_after = board.copy()
    board_after.push(move)
    
    gives_check = board.gives_check(move)
    
    if phase == "opening":
        # Opening principles
        if moving_piece.piece_type == chess.KING:
            # Castling check
            if abs(chess.square_file(move.from_square) - chess.square_file(move.to_square)) > 1:
                return "Castling secures the king and connects the rooks."
        
        if moving_piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            # Development
            from_rank = chess.square_rank(move.from_square)
            is_initial = (moving_piece.color == chess.WHITE and from_rank == 0) or \
                        (moving_piece.color == chess.BLACK and from_rank == 7)
            if is_initial:
                return "Develops a piece toward the center, following opening principles."
        
        # Center control
        to_file = chess.square_file(move.to_square)
        to_rank = chess.square_rank(move.to_square)
        if to_file in (3, 4) and to_rank in (3, 4):
            return "Controls or occupies a central square."
    
    elif phase == "middlegame":
        if gives_check:
            return "In the middlegame, forcing moves like checks maintain the initiative."
        
        # Attack on king
        opponent_king = board_after.king(not moving_piece.color)
        if opponent_king:
            king_zone = _get_king_zone(opponent_king)
            if move.to_square in king_zone:
                return "Increases pressure on the opponent's king."
    
    elif phase == "endgame":
        if moving_piece.piece_type == chess.KING:
            # King activity
            to_file = chess.square_file(move.to_square)
            to_rank = chess.square_rank(move.to_square)
            if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
                return "King activity is crucial in the endgame. The king becomes a fighting piece."
        
        if moving_piece.piece_type == chess.PAWN:
            if _is_passed_pawn(board_after, move.to_square):
                return "Advancing a passed pawn is a key endgame technique."
        
        # Rook behind passed pawn
        if moving_piece.piece_type == chess.ROOK:
            return "Active rooks are essential in the endgame."
    
    return ""


def _get_king_zone(king_sq: int) -> Set[int]:
    """Get the squares around the king (king zone for attacking)."""
    zone = set()
    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
    
    for df in range(-2, 3):
        for dr in range(-2, 3):
            f = king_file + df
            r = king_rank + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                zone.add(chess.square(f, r))
    
    return zone


# =============================================================================
# MAIN EXPLANATION GENERATOR
# =============================================================================


def generate_puzzle_explanation_v2(
    board: chess.Board,
    best_move: chess.Move,
    eval_before: Optional[float] = None,
    eval_after: Optional[float] = None,
    eval_loss_cp: int = 0,
    phase: str = "middlegame",
) -> PuzzleExplanation:
    """
    Generate a comprehensive, coach-quality explanation for a puzzle move.
    
    This is the main entry point for explanation generation.
    
    Args:
        board: Position before the move
        best_move: The correct move (engine best move)
        eval_before: Engine eval before (optional, in pawns)
        eval_after: Engine eval after best move (optional, in pawns)
        eval_loss_cp: Centipawn loss if best move is missed
        phase: Game phase (opening/middlegame/endgame)
    
    Returns:
        PuzzleExplanation with all analysis and human-readable summary
    """
    explanation = PuzzleExplanation()
    
    moving_piece = board.piece_at(best_move.from_square)
    if not moving_piece:
        explanation.human_readable_summary = "Find the best move in this position."
        return explanation
    
    piece_name = chess.piece_name(moving_piece.piece_type).title()
    
    # Make the move for analysis
    board_after = board.copy()
    board_after.push(best_move)
    
    gives_check = board.gives_check(best_move)
    is_checkmate = board_after.is_checkmate()
    
    motifs_found = []
    descriptions = []
    
    # =========================================================================
    # DETECT ALL TACTICAL MOTIFS
    # =========================================================================
    
    # 1. Checkmate
    if is_checkmate:
        explanation.primary_motif = TacticalMotif.CHECKMATE
        back_rank_threat, back_rank_mate, br_desc = detect_back_rank_threat(board, best_move)
        if back_rank_mate:
            descriptions.append(br_desc)
        else:
            descriptions.append("Checkmate!")
        explanation.human_readable_summary = descriptions[0]
        return explanation
    
    # 2. Fork detection (only counts as fork if it actually wins material)
    is_winning_fork, forked_pieces = detect_fork(board_after, moving_piece.color, best_move.to_square)
    if is_winning_fork:
        motifs_found.append(TacticalMotif.FORK)
        piece_names = []
        for pt, sq, is_defended in forked_pieces:
            if pt == chess.KING:
                piece_names.append("King")
            else:
                defended_note = "" if not is_defended else ""
                piece_names.append(f"{chess.piece_name(pt).title()} on {chess.square_name(sq)}")
        
        if gives_check:
            fork_desc = f"This check forks the {' and '.join(piece_names)}, winning material."
        else:
            fork_desc = f"The {piece_name} forks the {' and '.join(piece_names)}, winning material."
        descriptions.append(fork_desc)
    
    # 3. Pin detection
    abs_pin, rel_pin, pin_desc = detect_pin(board, best_move)
    if abs_pin:
        motifs_found.append(TacticalMotif.PIN_ABSOLUTE)
        descriptions.append(pin_desc + " (absolute pin).")
    elif rel_pin:
        motifs_found.append(TacticalMotif.PIN_RELATIVE)
        descriptions.append(pin_desc + ".")
    
    # 4. Skewer detection
    is_skewer, skewer_desc = detect_skewer(board, best_move)
    if is_skewer:
        motifs_found.append(TacticalMotif.SKEWER)
        descriptions.append(skewer_desc)
    
    # 5. Discovered attack/check
    is_discovery, is_disc_check, disc_desc = detect_discovered_attack(board, best_move)
    if is_disc_check:
        motifs_found.append(TacticalMotif.DISCOVERED_CHECK)
        descriptions.append(disc_desc)
    elif is_discovery:
        motifs_found.append(TacticalMotif.DISCOVERED_ATTACK)
        descriptions.append(disc_desc)
    
    # 6. Back-rank threats
    br_threat, br_mate, br_desc = detect_back_rank_threat(board, best_move)
    if br_mate:
        motifs_found.append(TacticalMotif.BACK_RANK_MATE)
        descriptions.append(br_desc)
    elif br_threat:
        motifs_found.append(TacticalMotif.BACK_RANK_THREAT)
        descriptions.append(br_desc)
    
    # 7. Promotion threats
    is_promo, promo_desc = detect_promotion_threat(board, best_move)
    if is_promo:
        motifs_found.append(TacticalMotif.PROMOTION_THREAT)
        descriptions.append(promo_desc)
    
    # 8. Mate threats
    is_mate_threat, mate_in_n, mate_desc = detect_mate_threat(board, best_move)
    if is_mate_threat and mate_in_n > 0:
        motifs_found.append(TacticalMotif.MATE_THREAT)
        descriptions.append(mate_desc)
    
    # 9. Removing defender
    removes_def, def_desc = detect_removing_defender(board, best_move)
    if removes_def:
        motifs_found.append(TacticalMotif.REMOVING_DEFENDER)
        descriptions.append(def_desc)
    
    # 10. Trapped piece
    traps_piece, trap_desc = detect_trapped_piece(board, best_move)
    if traps_piece:
        motifs_found.append(TacticalMotif.TRAPPED_PIECE)
        descriptions.append(trap_desc)
    
    # Set primary and secondary motifs
    if motifs_found:
        explanation.primary_motif = motifs_found[0]
        explanation.secondary_motifs = motifs_found[1:]
    
    # =========================================================================
    # THREAT ANALYSIS
    # =========================================================================
    
    # Threats stopped (what opponent was threatening)
    opponent_threats = analyze_opponent_threats(board)
    if opponent_threats:
        explanation.threats_stopped = opponent_threats
        if not descriptions:
            descriptions.append(f"This stops {opponent_threats[0].lower()}.")
    
    # Threats created
    new_threats = analyze_threats_created(board, best_move)
    explanation.threats_created = new_threats
    
    # =========================================================================
    # MATERIAL ANALYSIS
    # =========================================================================
    
    material_desc = analyze_material_outcome(board, best_move)
    if material_desc:
        explanation.material_outcome = material_desc
        if not descriptions:
            descriptions.append(material_desc + ".")
    
    # =========================================================================
    # PHASE-SPECIFIC GUIDANCE
    # =========================================================================
    
    phase_guidance = get_phase_guidance(board, best_move, phase)
    if phase_guidance:
        explanation.phase_specific_guidance = phase_guidance
    
    # =========================================================================
    # BUILD HUMAN-READABLE SUMMARY
    # =========================================================================
    
    summary_parts = []
    
    # Main tactical idea
    if descriptions:
        summary_parts.append(descriptions[0])
    
    # Add threat context if relevant and not redundant
    if opponent_threats and len(summary_parts) == 1:
        threat_context = opponent_threats[0]
        if "checkmate" in threat_context.lower() or "hanging" in threat_context.lower():
            summary_parts.append(f"Before this move, {threat_context.lower()}, making this the critical response.")
    
    # Add phase guidance if space permits
    if phase_guidance and len(summary_parts) < 3:
        summary_parts.append(phase_guidance)
    
    # Fallback if nothing detected
    if not summary_parts:
        # Simple check
        if gives_check:
            summary_parts.append(f"The {piece_name} delivers check.")
        # Simple capture
        elif board.piece_at(best_move.to_square):
            captured = board.piece_at(best_move.to_square)
            captured_name = chess.piece_name(captured.piece_type).title()
            summary_parts.append(f"Captures the {captured_name}.")
        # Positional
        else:
            summary_parts.append(f"The {piece_name} improves to {chess.square_name(best_move.to_square)}, strengthening the position.")
    
    explanation.human_readable_summary = " ".join(summary_parts)
    
    return explanation


def generate_explanation_string(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int = 0,
    puzzle_type = None,
    phase: str = "middlegame",
) -> str:
    """
    Simplified wrapper that returns just the human-readable string.
    
    This is the drop-in replacement for the old generate_puzzle_explanation.
    """
    explanation = generate_puzzle_explanation_v2(
        board=board,
        best_move=best_move,
        eval_loss_cp=eval_loss_cp,
        phase=phase,
    )
    return explanation.human_readable_summary
