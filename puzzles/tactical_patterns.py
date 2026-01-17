"""
Tactical Pattern Detection Module (Engine-First, Constraint-Based)

DESIGN PHILOSOPHY:
==================
1. ENGINE TRUTH PRECEDES PATTERN LABELING
   - Only detect patterns AFTER Stockfish confirms a forcing outcome
   - Patterns EXPLAIN why alternatives fail, they don't PREDICT tactics

2. PATTERNS ARE EXPLANATIONS, NOT DETECTORS
   - Engine discovers the forcing sequence
   - Patterns explain which legal defenses disappear and why

3. CONSTRAINT-BASED REASONING
   - Every legal reply is evaluated against atomic constraints
   - Constraints explain WHY a branch terminates (not just that it does)

4. COMPOSABLE ATOMIC PATTERNS
   - Complex patterns = composition of simpler ones
   - Example: Smothered Mate = King-confinement + Knight-only-attacker + Check

PATTERN TAXONOMY (4-Tier Hierarchy):
====================================
TIER 0: Meta/Structural (Internal only, not shown to users)
    - engine_verified, single_legal_reply, all_branches_lose

TIER 1: Atomic Constraints (Core building blocks, ~15 patterns)
    King-Legality: king_in_check, king_confined, king_cutoff
    Defender-Availability: defender_pinned, defender_overloaded, defender_captured
    Attack Geometry: double_attack, discovered_attack, x_ray_attack
    Mobility/Escape: no_flight_squares, piece_trapped, interposition_impossible

TIER 2: Tactical Outcomes (Results of constraints, ~7 patterns)
    material_win, checkmate, promotion_unstoppable, perpetual_check, stalemate_trap
    
TIER 3: Named Composites (Pedagogical labels, ~10 patterns)
    back_rank_mate, smothered_mate, anastasia_mate, arabian_mate
    greek_gift, windmill, desperado, zwischenzug, skewer, discovered_check

TIER 4: Rare/Advanced (~5 patterns)
    fortress_breaker, zugzwang, mutual_zugzwang, opposition, pawn_breakthrough

All patterns include confidence scores (0.0-1.0) and support evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple, Dict
import chess
import chess.engine
import os

# =============================================================================
# PATTERN TAXONOMY ENUMS
# =============================================================================

class PatternTier(int, Enum):
    """Hierarchical tier for pattern classification."""
    META = 0           # Internal structural markers
    ATOMIC = 1         # Core constraint detectors
    OUTCOME = 2        # Result patterns
    COMPOSITE = 3      # Named pedagogical patterns
    ADVANCED = 4       # Rare/positional patterns


class AtomicConstraint(str, Enum):
    """Tier 1: Atomic constraints that explain why defenses fail."""
    # King-Legality constraints
    KING_IN_CHECK = "king_in_check"
    KING_CONFINED = "king_confined"          # Limited flight squares (≤2)
    KING_CUTOFF = "king_cutoff"              # King blocked by pieces or edge
    
    # Defender-Availability constraints
    DEFENDER_PINNED = "defender_pinned"      # Defender can't move (absolute pin)
    DEFENDER_OVERLOADED = "defender_overloaded"  # Defender has 2+ duties
    DEFENDER_CAPTURED = "defender_captured"  # Defender removed
    DEFENDER_DEFLECTED = "defender_deflected"  # Defender lured away
    
    # Attack Geometry constraints
    DOUBLE_ATTACK = "double_attack"          # Two+ pieces attacked by one piece
    DISCOVERED_ATTACK = "discovered_attack"  # Attack revealed by moving piece
    X_RAY_ATTACK = "x_ray_attack"            # Attack through another piece
    BATTERY = "battery"                      # Aligned pieces on same line
    
    # Mobility/Escape constraints
    NO_FLIGHT_SQUARES = "no_flight_squares"  # Piece has no safe squares
    PIECE_TRAPPED = "piece_trapped"          # Piece cannot escape capture
    INTERPOSITION_IMPOSSIBLE = "interposition_impossible"  # No blocking piece
    
    # Special constraints
    FORCED_RECAPTURE = "forced_recapture"    # Must recapture or lose material
    TEMPO_GAIN = "tempo_gain"                # Gains time via threat


class TacticalOutcome(str, Enum):
    """Tier 2: Outcomes that result from constraint satisfaction."""
    MATERIAL_WIN = "material_win"
    CHECKMATE = "checkmate"
    PROMOTION_UNSTOPPABLE = "promotion_unstoppable"
    PERPETUAL_CHECK = "perpetual_check"
    STALEMATE_TRAP = "stalemate_trap"
    DRAW_ESCAPE = "draw_escape"              # Forcing draw from losing position
    EXCHANGE_WIN = "exchange_win"            # Win exchange (rook for minor)


class CompositePattern(str, Enum):
    """Tier 3: Named composite patterns (pedagogical labels)."""
    # Mate patterns
    BACK_RANK_MATE = "back_rank_mate"
    SMOTHERED_MATE = "smothered_mate"
    ANASTASIA_MATE = "anastasia_mate"
    ARABIAN_MATE = "arabian_mate"
    EPAULETTE_MATE = "epaulette_mate"
    CORRIDOR_MATE = "corridor_mate"
    
    # Tactical patterns
    FORK = "fork"
    PIN = "pin"
    SKEWER = "skewer"
    DISCOVERED_CHECK = "discovered_check"
    DOUBLE_CHECK = "double_check"
    WINDMILL = "windmill"
    DESPERADO = "desperado"
    ZWISCHENZUG = "zwischenzug"
    REMOVING_THE_GUARD = "removing_the_guard"
    GREEK_GIFT = "greek_gift"


class AdvancedPattern(str, Enum):
    """Tier 4: Rare/advanced patterns."""
    ZUGZWANG = "zugzwang"
    MUTUAL_ZUGZWANG = "mutual_zugzwang"
    OPPOSITION = "opposition"
    FORTRESS_BREAKER = "fortress_breaker"
    PAWN_BREAKTHROUGH = "pawn_breakthrough"
    TRIANGULATION = "triangulation"


# =============================================================================
# PIECE VALUES (centipawns)
# =============================================================================

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,  # Can't be captured
}

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


# =============================================================================
# PATTERN ATTRIBUTION DATA STRUCTURE
# =============================================================================

@dataclass
class ConstraintEvidence:
    """Evidence supporting an atomic constraint detection."""
    constraint: AtomicConstraint
    confidence: float  # 0.0 - 1.0
    
    # Squares/pieces involved
    primary_square: Optional[int] = None      # Main square (e.g., pinned piece)
    secondary_square: Optional[int] = None    # Supporting square (e.g., pinner)
    affected_piece_type: Optional[int] = None # chess.QUEEN, etc.
    
    # Human-readable evidence
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "constraint": self.constraint.value,
            "confidence": self.confidence,
            "primary_square": chess.square_name(self.primary_square) if self.primary_square is not None else None,
            "secondary_square": chess.square_name(self.secondary_square) if self.secondary_square is not None else None,
            "affected_piece_type": PIECE_NAMES.get(self.affected_piece_type) if self.affected_piece_type else None,
            "description": self.description,
        }


@dataclass
class PatternAttribution:
    """
    Complete attribution for why a tactical position works.
    
    Engine truth comes first (outcome verified), then we explain WHY
    the alternatives fail using atomic constraints.
    """
    # Engine verification (required)
    is_engine_verified: bool = False
    engine_eval_before: Optional[int] = None  # centipawns
    engine_eval_after: Optional[int] = None   # centipawns
    eval_swing: int = 0                        # How much position changed
    
    # Primary tactical outcome
    primary_outcome: Optional[TacticalOutcome] = None
    
    # Named composite pattern (if applicable)
    composite_pattern: Optional[CompositePattern] = None
    
    # Advanced pattern (if applicable)
    advanced_pattern: Optional[AdvancedPattern] = None
    
    # Atomic constraints that explain WHY the tactic works
    primary_constraints: List[ConstraintEvidence] = field(default_factory=list)
    secondary_constraints: List[ConstraintEvidence] = field(default_factory=list)
    
    # Suppressed patterns (detected but not primary)
    suppressed_patterns: List[str] = field(default_factory=list)
    
    # Structural meta-info
    solution_depth: int = 1        # Number of moves in solution
    opponent_alternatives: int = 0  # How many reasonable replies opponent had
    is_only_move: bool = False     # True if all alternatives lose significantly
    
    # Human-readable summary
    pattern_summary: str = ""
    why_it_works: str = ""
    
    def get_primary_pattern_name(self) -> str:
        """Get the most specific pattern name for display."""
        if self.composite_pattern:
            return self.composite_pattern.value.replace("_", " ").title()
        if self.advanced_pattern:
            return self.advanced_pattern.value.replace("_", " ").title()
        if self.primary_outcome:
            return self.primary_outcome.value.replace("_", " ").title()
        if self.primary_constraints:
            return self.primary_constraints[0].constraint.value.replace("_", " ").title()
        return "Tactical Position"
    
    def to_dict(self) -> dict:
        return {
            "is_engine_verified": self.is_engine_verified,
            "eval_swing": self.eval_swing,
            "primary_outcome": self.primary_outcome.value if self.primary_outcome else None,
            "composite_pattern": self.composite_pattern.value if self.composite_pattern else None,
            "advanced_pattern": self.advanced_pattern.value if self.advanced_pattern else None,
            "primary_constraints": [c.to_dict() for c in self.primary_constraints],
            "secondary_constraints": [c.to_dict() for c in self.secondary_constraints],
            "solution_depth": self.solution_depth,
            "is_only_move": self.is_only_move,
            "pattern_summary": self.pattern_summary,
            "why_it_works": self.why_it_works,
        }


# =============================================================================
# ATOMIC CONSTRAINT DETECTORS
# =============================================================================

def detect_king_in_check(board: chess.Board) -> Optional[ConstraintEvidence]:
    """Detect if the king is in check."""
    if not board.is_check():
        return None
    
    king_square = board.king(board.turn)
    if king_square is None:
        return None
    
    # Find the checking piece(s)
    attackers = board.attackers(not board.turn, king_square)
    attacker_squares = list(attackers)
    
    if len(attacker_squares) == 0:
        return None
    
    attacker_sq = attacker_squares[0]
    attacker_piece = board.piece_at(attacker_sq)
    
    description = f"King on {chess.square_name(king_square)} is in check"
    if attacker_piece:
        description += f" from {PIECE_NAMES[attacker_piece.piece_type]} on {chess.square_name(attacker_sq)}"
    
    return ConstraintEvidence(
        constraint=AtomicConstraint.KING_IN_CHECK,
        confidence=1.0,
        primary_square=king_square,
        secondary_square=attacker_sq,
        description=description,
    )


def detect_king_confined(board: chess.Board, color: chess.Color) -> Optional[ConstraintEvidence]:
    """
    Detect if king has limited flight squares (≤2 safe squares).
    
    A confined king is vulnerable to mating attacks.
    """
    king_sq = board.king(color)
    if king_sq is None:
        return None
    
    # Count safe squares for the king
    safe_squares = []
    for sq in chess.SQUARES:
        if chess.square_distance(king_sq, sq) == 1:  # Adjacent squares
            piece = board.piece_at(sq)
            # Can't go to square occupied by own piece
            if piece and piece.color == color:
                continue
            # Check if square is attacked by opponent
            if board.is_attacked_by(not color, sq):
                continue
            safe_squares.append(sq)
    
    if len(safe_squares) <= 2:
        description = f"King on {chess.square_name(king_sq)} has only {len(safe_squares)} flight square(s)"
        return ConstraintEvidence(
            constraint=AtomicConstraint.KING_CONFINED,
            confidence=min(1.0, 1.0 - len(safe_squares) * 0.3),
            primary_square=king_sq,
            description=description,
        )
    
    return None


def detect_king_cutoff(board: chess.Board, color: chess.Color) -> Optional[ConstraintEvidence]:
    """
    Detect if king is cut off from the rest of the board (e.g., rook cutoff).
    
    Common in endgames and mating attacks.
    """
    king_sq = board.king(color)
    if king_sq is None:
        return None
    
    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
    
    # Check for rook/queen cutoff along file or rank
    opponent = not color
    
    # File cutoff (rook/queen controlling adjacent file)
    cutoff_file = None
    for df in [-1, 1]:
        test_file = king_file + df
        if 0 <= test_file <= 7:
            # Check if opponent controls entire file
            file_controlled = True
            for rank in range(8):
                sq = chess.square(test_file, rank)
                if not board.is_attacked_by(opponent, sq):
                    file_controlled = False
                    break
            if file_controlled:
                cutoff_file = test_file
                break
    
    # Rank cutoff (rook/queen controlling adjacent rank)
    cutoff_rank = None
    for dr in [-1, 1]:
        test_rank = king_rank + dr
        if 0 <= test_rank <= 7:
            rank_controlled = True
            for file in range(8):
                sq = chess.square(file, test_rank)
                if not board.is_attacked_by(opponent, sq):
                    rank_controlled = False
                    break
            if rank_controlled:
                cutoff_rank = test_rank
                break
    
    if cutoff_file is not None or cutoff_rank is not None:
        desc_parts = []
        if cutoff_file is not None:
            desc_parts.append(f"{chr(ord('a') + cutoff_file)}-file")
        if cutoff_rank is not None:
            desc_parts.append(f"rank {cutoff_rank + 1}")
        
        return ConstraintEvidence(
            constraint=AtomicConstraint.KING_CUTOFF,
            confidence=0.9,
            primary_square=king_sq,
            description=f"King cut off along {' and '.join(desc_parts)}",
        )
    
    return None


def detect_pinned_pieces(board: chess.Board, color: chess.Color) -> List[ConstraintEvidence]:
    """
    Detect all pinned pieces for a given color.
    
    Returns list of evidence for each pinned piece.
    """
    results = []
    king_sq = board.king(color)
    if king_sq is None:
        return results
    
    opponent = not color
    
    # Check each piece for pins
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != color:
            continue
        if piece.piece_type == chess.KING:
            continue
        
        # Check if this piece is pinned to the king
        is_pinned = board.is_pinned(color, sq)
        if is_pinned:
            # Find the pinner
            pinner_sq = None
            for attacker_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                for attacker_sq in board.pieces(attacker_type, opponent):
                    # Check if attacker, pinned piece, and king are aligned
                    if _squares_aligned(attacker_sq, sq, king_sq):
                        pinner_sq = attacker_sq
                        break
                if pinner_sq:
                    break
            
            pinner_name = ""
            if pinner_sq:
                pinner_piece = board.piece_at(pinner_sq)
                if pinner_piece:
                    pinner_name = f" by {PIECE_NAMES[pinner_piece.piece_type]} on {chess.square_name(pinner_sq)}"
            
            results.append(ConstraintEvidence(
                constraint=AtomicConstraint.DEFENDER_PINNED,
                confidence=1.0,
                primary_square=sq,
                secondary_square=pinner_sq,
                affected_piece_type=piece.piece_type,
                description=f"{PIECE_NAMES[piece.piece_type].title()} on {chess.square_name(sq)} is pinned{pinner_name}",
            ))
    
    return results


def detect_overloaded_pieces(board: chess.Board, color: chess.Color) -> List[ConstraintEvidence]:
    """
    Detect overloaded defenders (pieces with 2+ defensive duties).
    
    A piece is overloaded if it defends multiple attacked pieces.
    """
    results = []
    opponent = not color
    
    # Find all attacked pieces that need defense
    attacked_pieces = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == color and piece.piece_type != chess.KING:
            if board.is_attacked_by(opponent, sq):
                attacked_pieces.append((sq, piece))
    
    # For each defending piece, count how many pieces it defends
    defender_duties: Dict[int, List[int]] = {}  # defender_sq -> list of defended squares
    
    for att_sq, att_piece in attacked_pieces:
        defenders = board.attackers(color, att_sq)
        for def_sq in defenders:
            if def_sq not in defender_duties:
                defender_duties[def_sq] = []
            defender_duties[def_sq].append(att_sq)
    
    # Find overloaded defenders (2+ duties)
    for def_sq, duties in defender_duties.items():
        if len(duties) >= 2:
            def_piece = board.piece_at(def_sq)
            if def_piece:
                duty_desc = ", ".join(chess.square_name(sq) for sq in duties[:3])
                results.append(ConstraintEvidence(
                    constraint=AtomicConstraint.DEFENDER_OVERLOADED,
                    confidence=0.8 + 0.1 * min(len(duties) - 2, 2),
                    primary_square=def_sq,
                    affected_piece_type=def_piece.piece_type,
                    description=f"{PIECE_NAMES[def_piece.piece_type].title()} on {chess.square_name(def_sq)} defends {duty_desc}",
                ))
    
    return results


def detect_double_attack(
    board_before: chess.Board, 
    board_after: chess.Board, 
    move: chess.Move
) -> Optional[ConstraintEvidence]:
    """
    Detect if a move creates a double attack (fork).
    
    A double attack is when one piece attacks 2+ enemy pieces.
    """
    attacker_color = board_before.turn
    defender_color = not attacker_color
    
    to_sq = move.to_square
    moving_piece = board_after.piece_at(to_sq)
    if not moving_piece:
        return None
    
    # Find all pieces attacked by the moved piece
    attacked_valuable = []
    for sq in chess.SQUARES:
        target = board_after.piece_at(sq)
        if target and target.color == defender_color:
            if board_after.is_attacked_by(attacker_color, sq):
                # Verify attack comes from the moved piece
                attackers = board_after.attackers(attacker_color, sq)
                if to_sq in attackers:
                    # Only count valuable pieces
                    if target.piece_type != chess.PAWN or target.piece_type == chess.KING:
                        attacked_valuable.append((sq, target))
    
    if len(attacked_valuable) >= 2:
        # Check if this is a winning fork (not just attacking defended pieces)
        targets_desc = " and ".join(
            f"{PIECE_NAMES[p.piece_type]} on {chess.square_name(sq)}" 
            for sq, p in attacked_valuable[:2]
        )
        
        return ConstraintEvidence(
            constraint=AtomicConstraint.DOUBLE_ATTACK,
            confidence=0.9,
            primary_square=to_sq,
            affected_piece_type=moving_piece.piece_type,
            description=f"{PIECE_NAMES[moving_piece.piece_type].title()} forks {targets_desc}",
        )
    
    return None


def detect_discovered_attack(
    board_before: chess.Board,
    board_after: chess.Board,
    move: chess.Move
) -> Optional[ConstraintEvidence]:
    """
    Detect discovered attacks (piece moves, revealing attack by another piece).
    """
    from_sq = move.from_square
    attacker_color = board_before.turn
    defender_color = not attacker_color
    
    # Find pieces that now have new attack lines through the vacated square
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if not piece or piece.color != attacker_color:
            continue
        if piece.piece_type not in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
            continue
        if sq == move.to_square:  # Skip the piece that moved
            continue
        
        # Check if this piece now attacks something through the vacated square
        # that it couldn't attack before
        for target_sq in chess.SQUARES:
            target = board_after.piece_at(target_sq)
            if not target or target.color != defender_color:
                continue
            
            # Was this target blocked before?
            was_blocked = not board_before.is_attacked_by(attacker_color, target_sq) or \
                         sq not in board_before.attackers(attacker_color, target_sq)
            
            # Is it attacked now from this piece?
            is_attacked_now = sq in board_after.attackers(attacker_color, target_sq)
            
            if was_blocked and is_attacked_now:
                # Verify the vacated square is on the line
                if _squares_aligned(sq, from_sq, target_sq):
                    is_check = target.piece_type == chess.KING
                    constraint = AtomicConstraint.DISCOVERED_ATTACK
                    
                    return ConstraintEvidence(
                        constraint=constraint,
                        confidence=0.95 if is_check else 0.85,
                        primary_square=sq,
                        secondary_square=target_sq,
                        affected_piece_type=piece.piece_type,
                        description=f"Discovered attack: {PIECE_NAMES[piece.piece_type]} reveals attack on {PIECE_NAMES[target.piece_type]}",
                    )
    
    return None


def detect_no_flight_squares(board: chess.Board, square: int) -> Optional[ConstraintEvidence]:
    """
    Detect if a piece has no safe squares to move to (trapped).
    """
    piece = board.piece_at(square)
    if not piece:
        return None
    
    color = piece.color
    opponent = not color
    
    # Count safe squares this piece can move to
    safe_squares = 0
    
    # Generate all pseudo-legal moves for this piece
    for move in board.legal_moves:
        if move.from_square == square:
            # Would this square be safe?
            target_sq = move.to_square
            # Check if moving there loses material
            board_copy = board.copy()
            board_copy.push(move)
            
            # If piece can be captured for less value, it's not safe
            if not board_copy.is_attacked_by(opponent, target_sq):
                safe_squares += 1
            else:
                # Check if adequately defended
                attackers = len(board_copy.attackers(opponent, target_sq))
                defenders = len(board_copy.attackers(color, target_sq))
                if defenders >= attackers:
                    safe_squares += 1
    
    if safe_squares == 0:
        return ConstraintEvidence(
            constraint=AtomicConstraint.NO_FLIGHT_SQUARES,
            confidence=1.0,
            primary_square=square,
            affected_piece_type=piece.piece_type,
            description=f"{PIECE_NAMES[piece.piece_type].title()} on {chess.square_name(square)} has no safe squares",
        )
    
    return None


def detect_piece_trapped(board: chess.Board, color: chess.Color) -> List[ConstraintEvidence]:
    """
    Detect pieces that are trapped (attacked and cannot escape).
    """
    results = []
    opponent = not color
    
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != color:
            continue
        if piece.piece_type in [chess.PAWN, chess.KING]:
            continue
        
        # Is this piece under attack?
        if not board.is_attacked_by(opponent, sq):
            continue
        
        # Check if it's adequately defended
        attackers = len(board.attackers(opponent, sq))
        defenders = len(board.attackers(color, sq))
        
        if defenders >= attackers and piece.piece_type != chess.QUEEN:
            continue  # Defended
        
        # Check if piece can escape to a safe square
        has_escape = detect_no_flight_squares(board, sq) is None
        
        if not has_escape:
            results.append(ConstraintEvidence(
                constraint=AtomicConstraint.PIECE_TRAPPED,
                confidence=0.9,
                primary_square=sq,
                affected_piece_type=piece.piece_type,
                description=f"{PIECE_NAMES[piece.piece_type].title()} on {chess.square_name(sq)} is trapped",
            ))
    
    return results


def detect_interposition_impossible(board: chess.Board) -> Optional[ConstraintEvidence]:
    """
    Detect if king is in check and no interposition is possible.
    """
    if not board.is_check():
        return None
    
    king_sq = board.king(board.turn)
    if king_sq is None:
        return None
    
    # Get checking pieces
    attackers = board.attackers(not board.turn, king_sq)
    attacker_list = list(attackers)
    
    # Double check - interposition never possible
    if len(attacker_list) >= 2:
        return ConstraintEvidence(
            constraint=AtomicConstraint.INTERPOSITION_IMPOSSIBLE,
            confidence=1.0,
            primary_square=king_sq,
            description="Double check - interposition impossible, king must move",
        )
    
    attacker_sq = attacker_list[0]
    attacker_piece = board.piece_at(attacker_sq)
    
    # Knight or pawn check - can't interpose
    if attacker_piece and attacker_piece.piece_type in [chess.KNIGHT, chess.PAWN]:
        return ConstraintEvidence(
            constraint=AtomicConstraint.INTERPOSITION_IMPOSSIBLE,
            confidence=1.0,
            primary_square=attacker_sq,
            affected_piece_type=attacker_piece.piece_type,
            description=f"{PIECE_NAMES[attacker_piece.piece_type].title()} check - interposition impossible",
        )
    
    # Check if any interposition is actually legal
    has_interposition = False
    for move in board.legal_moves:
        if move.from_square == king_sq:
            continue  # King move, not interposition
        # This is a non-king move that deals with check - must be interposition or capture
        board_copy = board.copy()
        board_copy.push(move)
        if not board_copy.is_check():
            has_interposition = True
            break
    
    if not has_interposition:
        return ConstraintEvidence(
            constraint=AtomicConstraint.INTERPOSITION_IMPOSSIBLE,
            confidence=0.95,
            primary_square=king_sq,
            description="No piece can block the check",
        )
    
    return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _squares_aligned(sq1: int, sq2: int, sq3: int) -> bool:
    """Check if three squares are on the same line (rank, file, or diagonal)."""
    if sq1 == sq2 or sq2 == sq3 or sq1 == sq3:
        return False
    
    f1, r1 = chess.square_file(sq1), chess.square_rank(sq1)
    f2, r2 = chess.square_file(sq2), chess.square_rank(sq2)
    f3, r3 = chess.square_file(sq3), chess.square_rank(sq3)
    
    # Same file
    if f1 == f2 == f3:
        return True
    # Same rank
    if r1 == r2 == r3:
        return True
    # Same diagonal
    if abs(f2 - f1) == abs(r2 - r1) and abs(f3 - f1) == abs(r3 - r1):
        df1, dr1 = f2 - f1, r2 - r1
        df2, dr2 = f3 - f1, r3 - r1
        # Check same diagonal direction
        if df1 != 0 and df2 != 0:
            return (df1 // abs(df1)) == (df2 // abs(df2)) or \
                   (dr1 // abs(dr1)) == (dr2 // abs(dr2)) if dr1 != 0 and dr2 != 0 else False
    
    return False


def _get_stockfish_path() -> str:
    """Get Stockfish binary path."""
    env_path = os.getenv("STOCKFISH_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path
    for path in ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish",
                 "/usr/bin/stockfish", "/usr/games/stockfish"]:
        if os.path.exists(path):
            return path
    return "stockfish"


# =============================================================================
# ADDITIONAL ATOMIC CONSTRAINT DETECTORS
# =============================================================================

def detect_battery(board: chess.Board, color: chess.Color) -> List[ConstraintEvidence]:
    """
    Detect batteries (two pieces on the same line attacking same target).
    
    Examples: Queen + Bishop on diagonal, Queen + Rook on file/rank.
    """
    results = []
    
    # Find all sliding piece pairs
    queens = list(board.pieces(chess.QUEEN, color))
    rooks = list(board.pieces(chess.ROOK, color))
    bishops = list(board.pieces(chess.BISHOP, color))
    
    # Check rook-rook batteries (doubled rooks)
    for i, r1 in enumerate(rooks):
        for r2 in rooks[i+1:]:
            f1, f2 = chess.square_file(r1), chess.square_file(r2)
            r1_rank, r2_rank = chess.square_rank(r1), chess.square_rank(r2)
            
            if f1 == f2:  # Same file
                # Check if path is clear
                clear = True
                for rank in range(min(r1_rank, r2_rank) + 1, max(r1_rank, r2_rank)):
                    if board.piece_at(chess.square(f1, rank)):
                        clear = False
                        break
                if clear:
                    results.append(ConstraintEvidence(
                        constraint=AtomicConstraint.BATTERY,
                        confidence=0.9,
                        primary_square=r1,
                        secondary_square=r2,
                        description=f"Doubled rooks on {chr(ord('a') + f1)}-file",
                    ))
            
            elif r1_rank == r2_rank:  # Same rank
                # Check if path is clear
                clear = True
                for file in range(min(f1, f2) + 1, max(f1, f2)):
                    if board.piece_at(chess.square(file, r1_rank)):
                        clear = False
                        break
                if clear:
                    results.append(ConstraintEvidence(
                        constraint=AtomicConstraint.BATTERY,
                        confidence=0.9,
                        primary_square=r1,
                        secondary_square=r2,
                        description=f"Doubled rooks on rank {r1_rank + 1}",
                    ))
    
    # Check queen-rook batteries
    for q in queens:
        q_file, q_rank = chess.square_file(q), chess.square_rank(q)
        for r in rooks:
            r_file, r_rank = chess.square_file(r), chess.square_rank(r)
            
            if q_file == r_file or q_rank == r_rank:
                # Check if on same file or rank
                results.append(ConstraintEvidence(
                    constraint=AtomicConstraint.BATTERY,
                    confidence=0.85,
                    primary_square=q,
                    secondary_square=r,
                    description=f"Queen-rook battery",
                ))
    
    # Check queen-bishop batteries (on diagonal)
    for q in queens:
        for b in bishops:
            if _squares_on_diagonal(q, b):
                results.append(ConstraintEvidence(
                    constraint=AtomicConstraint.BATTERY,
                    confidence=0.85,
                    primary_square=q,
                    secondary_square=b,
                    description=f"Queen-bishop battery on diagonal",
                ))
    
    return results


def _squares_on_diagonal(sq1: int, sq2: int) -> bool:
    """Check if two squares are on the same diagonal."""
    f1, r1 = chess.square_file(sq1), chess.square_rank(sq1)
    f2, r2 = chess.square_file(sq2), chess.square_rank(sq2)
    return abs(f1 - f2) == abs(r1 - r2) and sq1 != sq2


def detect_x_ray_attack(
    board: chess.Board,
    color: chess.Color,
) -> List[ConstraintEvidence]:
    """
    Detect x-ray attacks (attack through another piece).
    
    Example: Rook attacks queen through a pawn.
    """
    results = []
    opponent = not color
    
    # Check each sliding piece for x-ray potential
    for piece_type in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
        for sq in board.pieces(piece_type, color):
            # Get attack directions based on piece type
            if piece_type == chess.ROOK:
                directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            elif piece_type == chess.BISHOP:
                directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
            else:  # Queen
                directions = [(1, 0), (-1, 0), (0, 1), (0, -1),
                             (1, 1), (1, -1), (-1, 1), (-1, -1)]
            
            for df, dr in directions:
                # Walk along direction
                f, r = chess.square_file(sq), chess.square_rank(sq)
                blocking_piece = None
                blocking_sq = None
                
                while True:
                    f += df
                    r += dr
                    if not (0 <= f <= 7 and 0 <= r <= 7):
                        break
                    
                    curr_sq = chess.square(f, r)
                    piece = board.piece_at(curr_sq)
                    
                    if piece:
                        if blocking_piece is None:
                            # First piece encountered - could be the "through" piece
                            blocking_piece = piece
                            blocking_sq = curr_sq
                        else:
                            # Second piece - check for x-ray
                            if piece.color == opponent and blocking_piece.color == opponent:
                                # X-ray: attacking through one enemy piece to another
                                front_val = PIECE_VALUES.get(blocking_piece.piece_type, 0)
                                back_val = PIECE_VALUES.get(piece.piece_type, 0)
                                
                                if back_val > front_val:
                                    results.append(ConstraintEvidence(
                                        constraint=AtomicConstraint.X_RAY_ATTACK,
                                        confidence=0.8,
                                        primary_square=sq,
                                        secondary_square=curr_sq,
                                        description=f"X-ray attack on {PIECE_NAMES[piece.piece_type]} through {PIECE_NAMES[blocking_piece.piece_type]}",
                                    ))
                            break
    
    return results


def detect_tempo_gain(
    board_before: chess.Board,
    board_after: chess.Board,
    move: chess.Move,
) -> Optional[ConstraintEvidence]:
    """
    Detect if a move gains tempo (makes a threat that forces opponent response).
    """
    attacker = board_before.turn
    
    # Check if the move creates a threat
    threats = []
    
    # Check for check
    if board_after.is_check():
        threats.append("check")
    
    # Check for attack on undefended piece
    to_sq = move.to_square
    moving_piece = board_after.piece_at(to_sq)
    
    if moving_piece:
        for sq in chess.SQUARES:
            target = board_after.piece_at(sq)
            if target and target.color != attacker and target.piece_type != chess.KING:
                if board_after.is_attacked_by(attacker, sq):
                    attackers = board_after.attackers(attacker, sq)
                    if to_sq in attackers:
                        # The moved piece attacks this target
                        if not board_after.is_attacked_by(not attacker, sq):
                            threats.append(f"attacks undefended {PIECE_NAMES[target.piece_type]}")
    
    if threats:
        return ConstraintEvidence(
            constraint=AtomicConstraint.TEMPO_GAIN,
            confidence=0.75,
            primary_square=to_sq,
            description=f"Gains tempo: {', '.join(threats[:2])}",
        )
    
    return None


# =============================================================================
# COMPOSITE PATTERN DETECTION
# =============================================================================

def detect_back_rank_mate(board: chess.Board, move: chess.Move) -> Optional[ConstraintEvidence]:
    """Detect back rank mate pattern."""
    board_after = board.copy()
    board_after.push(move)
    
    if not board_after.is_checkmate():
        return None
    
    loser = board_after.turn
    king_sq = board_after.king(loser)
    if king_sq is None:
        return None
    
    # Check if king is on back rank
    king_rank = chess.square_rank(king_sq)
    back_rank = 0 if loser == chess.WHITE else 7
    
    if king_rank != back_rank:
        return None
    
    # Check if blocked by own pawns/pieces
    king_file = chess.square_file(king_sq)
    blocked_by_own = 0
    for f in [king_file - 1, king_file, king_file + 1]:
        if 0 <= f <= 7:
            second_rank = 1 if loser == chess.WHITE else 6
            sq = chess.square(f, second_rank)
            piece = board_after.piece_at(sq)
            if piece and piece.color == loser:
                blocked_by_own += 1
    
    if blocked_by_own >= 2:
        return ConstraintEvidence(
            constraint=AtomicConstraint.KING_CONFINED,
            confidence=1.0,
            primary_square=king_sq,
            description="Back rank mate - king trapped by own pieces",
        )
    
    return None


def detect_smothered_mate(board: chess.Board, move: chess.Move) -> Optional[ConstraintEvidence]:
    """Detect smothered mate pattern (knight mate with king surrounded)."""
    board_after = board.copy()
    board_after.push(move)
    
    if not board_after.is_checkmate():
        return None
    
    # Must be knight delivering mate
    moving_piece = board_after.piece_at(move.to_square)
    if not moving_piece or moving_piece.piece_type != chess.KNIGHT:
        return None
    
    loser = board_after.turn
    king_sq = board_after.king(loser)
    if king_sq is None:
        return None
    
    # Check if all adjacent squares are blocked by own pieces
    adjacent_blocked = 0
    for sq in chess.SQUARES:
        if chess.square_distance(king_sq, sq) == 1:
            piece = board_after.piece_at(sq)
            if piece and piece.color == loser:
                adjacent_blocked += 1
    
    if adjacent_blocked >= 3:
        return ConstraintEvidence(
            constraint=AtomicConstraint.KING_CONFINED,
            confidence=1.0,
            primary_square=king_sq,
            description="Smothered mate - king surrounded by own pieces",
        )
    
    return None


# =============================================================================
# MAIN PATTERN ANALYSIS FUNCTION
# =============================================================================

def analyze_tactical_patterns(
    board: chess.Board,
    best_move: chess.Move,
    engine: Optional[chess.engine.SimpleEngine] = None,
    eval_before: Optional[int] = None,
    eval_after: Optional[int] = None,
) -> PatternAttribution:
    """
    Main entry point for tactical pattern analysis.
    
    Analyzes a position and the best move, attributing the tactical theme
    to composable atomic constraints.
    
    Args:
        board: Position before the best move
        best_move: The correct tactical move
        engine: Optional Stockfish engine for verification
        eval_before: Eval before move (centipawns)
        eval_after: Eval after move (centipawns)
    
    Returns:
        PatternAttribution with full analysis
    """
    attribution = PatternAttribution()
    
    # Engine verification
    if eval_before is not None and eval_after is not None:
        attribution.is_engine_verified = True
        attribution.engine_eval_before = eval_before
        attribution.engine_eval_after = eval_after
        attribution.eval_swing = abs(eval_after - eval_before)
    
    # Make the move to analyze resulting position
    board_after = board.copy()
    board_after.push(best_move)
    
    attacker = board.turn
    defender = not attacker
    
    # -------------------------------------------------------------------------
    # STEP 1: Check for immediate outcomes
    # -------------------------------------------------------------------------
    
    if board_after.is_checkmate():
        attribution.primary_outcome = TacticalOutcome.CHECKMATE
        
        # Check for specific mate patterns
        back_rank = detect_back_rank_mate(board, best_move)
        if back_rank:
            attribution.composite_pattern = CompositePattern.BACK_RANK_MATE
            attribution.primary_constraints.append(back_rank)
        
        smothered = detect_smothered_mate(board, best_move)
        if smothered:
            attribution.composite_pattern = CompositePattern.SMOTHERED_MATE
            attribution.primary_constraints.append(smothered)
    
    elif board_after.is_stalemate():
        attribution.primary_outcome = TacticalOutcome.STALEMATE_TRAP
    
    # -------------------------------------------------------------------------
    # STEP 2: Detect atomic constraints before the move
    # -------------------------------------------------------------------------
    
    # King constraints
    king_check = detect_king_in_check(board_after)
    if king_check:
        attribution.primary_constraints.append(king_check)
    
    king_confined = detect_king_confined(board_after, defender)
    if king_confined:
        attribution.secondary_constraints.append(king_confined)
    
    king_cutoff = detect_king_cutoff(board_after, defender)
    if king_cutoff:
        attribution.secondary_constraints.append(king_cutoff)
    
    # Defender constraints
    pinned = detect_pinned_pieces(board_after, defender)
    for p in pinned:
        attribution.secondary_constraints.append(p)
    
    overloaded = detect_overloaded_pieces(board_after, defender)
    for o in overloaded:
        attribution.secondary_constraints.append(o)
    
    # Attack geometry
    double_attack = detect_double_attack(board, board_after, best_move)
    if double_attack:
        attribution.primary_constraints.append(double_attack)
        if not attribution.composite_pattern:
            attribution.composite_pattern = CompositePattern.FORK
    
    discovered = detect_discovered_attack(board, board_after, best_move)
    if discovered:
        attribution.primary_constraints.append(discovered)
        # Check for discovered check
        if board_after.is_check():
            moving_piece = board_after.piece_at(best_move.to_square)
            if moving_piece:
                # Is the check from a different piece?
                king_sq = board_after.king(defender)
                if king_sq:
                    direct_attackers = board_after.attackers(attacker, king_sq)
                    if best_move.to_square not in direct_attackers:
                        attribution.composite_pattern = CompositePattern.DISCOVERED_CHECK
    
    # Mobility constraints
    trapped = detect_piece_trapped(board_after, defender)
    for t in trapped:
        attribution.secondary_constraints.append(t)
    
    interpose = detect_interposition_impossible(board_after)
    if interpose:
        attribution.primary_constraints.append(interpose)
        # Double check detection
        king_sq = board_after.king(defender)
        if king_sq:
            attackers = board_after.attackers(attacker, king_sq)
            if len(list(attackers)) >= 2:
                attribution.composite_pattern = CompositePattern.DOUBLE_CHECK
    
    # -------------------------------------------------------------------------
    # STEP 3: Determine primary outcome if not already set
    # -------------------------------------------------------------------------
    
    if attribution.primary_outcome is None:
        # Check for material win
        if board.is_capture(best_move):
            captured = board.piece_at(best_move.to_square)
            if captured:
                moving = board.piece_at(best_move.from_square)
                if moving:
                    cap_val = PIECE_VALUES.get(captured.piece_type, 0)
                    mov_val = PIECE_VALUES.get(moving.piece_type, 0)
                    if cap_val >= mov_val or cap_val >= 300:
                        attribution.primary_outcome = TacticalOutcome.MATERIAL_WIN
        
        # Check for promotion
        if best_move.promotion:
            attribution.primary_outcome = TacticalOutcome.PROMOTION_UNSTOPPABLE
    
    # -------------------------------------------------------------------------
    # STEP 4: Generate human-readable summary
    # -------------------------------------------------------------------------
    
    attribution.pattern_summary = attribution.get_primary_pattern_name()
    
    why_parts = []
    if attribution.primary_constraints:
        why_parts.append(attribution.primary_constraints[0].description)
    if attribution.secondary_constraints:
        why_parts.append(attribution.secondary_constraints[0].description)
    
    attribution.why_it_works = "; ".join(why_parts) if why_parts else "Strong tactical move"
    
    # -------------------------------------------------------------------------
    # STEP 5: Count opponent alternatives (for difficulty assessment)
    # -------------------------------------------------------------------------
    
    reasonable_alternatives = 0
    for move in board_after.legal_moves:
        reasonable_alternatives += 1
    attribution.opponent_alternatives = reasonable_alternatives
    
    return attribution


# =============================================================================
# BATCH ANALYSIS FUNCTIONS
# =============================================================================

def get_all_constraints_for_position(
    board: chess.Board,
    perspective: chess.Color
) -> List[ConstraintEvidence]:
    """
    Get all detected constraints for a position from one side's perspective.
    
    Useful for understanding the full tactical picture.
    """
    constraints = []
    
    # King constraints
    if perspective == board.turn and board.is_check():
        check = detect_king_in_check(board)
        if check:
            constraints.append(check)
    
    confined = detect_king_confined(board, perspective)
    if confined:
        constraints.append(confined)
    
    cutoff = detect_king_cutoff(board, perspective)
    if cutoff:
        constraints.append(cutoff)
    
    # Defender constraints
    pinned = detect_pinned_pieces(board, perspective)
    constraints.extend(pinned)
    
    overloaded = detect_overloaded_pieces(board, perspective)
    constraints.extend(overloaded)
    
    # Mobility
    trapped = detect_piece_trapped(board, perspective)
    constraints.extend(trapped)
    
    if board.is_check() and perspective == board.turn:
        interpose = detect_interposition_impossible(board)
        if interpose:
            constraints.append(interpose)
    
    return constraints


def explain_why_move_works(
    board: chess.Board,
    move: chess.Move,
    engine: Optional[chess.engine.SimpleEngine] = None,
) -> str:
    """
    Generate a concise explanation of why a tactical move works.
    
    Uses constraint-based reasoning to explain the key features.
    """
    attribution = analyze_tactical_patterns(board, move, engine)
    
    parts = []
    
    if attribution.composite_pattern:
        parts.append(attribution.composite_pattern.value.replace("_", " ").title())
    
    if attribution.primary_outcome:
        outcome = attribution.primary_outcome.value.replace("_", " ")
        parts.append(f"leads to {outcome}")
    
    if attribution.primary_constraints:
        constraint_desc = attribution.primary_constraints[0].description
        parts.append(f"because {constraint_desc.lower()}")
    
    return " - ".join(parts) if parts else "Strong move"
