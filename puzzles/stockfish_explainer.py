"""
Stockfish-Based Move Explanation Engine

This module generates SHORT, ACCURATE, HUMAN-TONED explanations for why
Stockfish's best move is best.

CORE PRINCIPLE: Stockfish determines what's best. We explain WHY in human terms.

We NEVER:
- Invent best moves (that's Stockfish's job)
- Mention centipawns, depth, or evaluation numbers
- List multiple unrelated reasons
- Use engine jargon

We ALWAYS:
- Use causal language ("because", "threatens", "prevents")
- Focus on ONE main idea (the highest priority factor)
- Frame explanations as a strong human player would

PRIORITY HIERARCHY (highest to lowest - stop at first applicable):
1. Forced checkmate or avoiding immediate mate
2. Forced tactical sequence winning/losing material
3. Preventing a critical tactical threat
4. King safety (attack or defense)
5. Only move / forced defensive resource
6. Initiative and tempo dominance
7. Material sacrifice for concrete compensation
8. Transition into winning/drawn endgame
9. Prophylactic prevention of opponent plans
10. Piece activity and coordination
11. Pawn structure improvements
12. Space and positional edge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set
from enum import IntEnum
import os

import chess
import chess.engine


# =============================================================================
# PRIORITY LEVELS (lower number = higher priority)
# =============================================================================

class Priority(IntEnum):
    CHECKMATE = 1
    FORCED_TACTICS = 2
    PREVENT_THREAT = 3
    KING_SAFETY = 4
    ONLY_MOVE = 5
    INITIATIVE = 6
    SACRIFICE_COMPENSATION = 7
    ENDGAME_TRANSITION = 8
    PROPHYLAXIS = 9
    PIECE_ACTIVITY = 10
    PAWN_STRUCTURE = 11
    POSITIONAL = 12
    UNKNOWN = 99


# =============================================================================
# PIECE VALUES (human terms: Q=9, R=5, B/N=3, P=1)
# =============================================================================

PIECE_POINTS = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}

# =============================================================================
# STOCKFISH INTERFACE
# =============================================================================

def _get_stockfish_path() -> str:
    env_path = os.getenv("STOCKFISH_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path
    for path in ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish",
                 "/usr/bin/stockfish", "/usr/games/stockfish"]:
        if os.path.exists(path):
            return path
    return "stockfish"


def _open_engine() -> Optional[chess.engine.SimpleEngine]:
    try:
        return chess.engine.SimpleEngine.popen_uci(_get_stockfish_path())
    except Exception:
        return None


# =============================================================================
# POSITION CLASSIFICATION
# =============================================================================

@dataclass
class PositionType:
    is_tactical: bool = False      # Checks, captures, threats available
    is_defensive: bool = False     # Side to move is worse/under attack
    is_endgame: bool = False       # Reduced material
    is_strategic: bool = False     # No immediate tactics


def classify_position(board: chess.Board) -> PositionType:
    """Classify position to determine which factors matter."""
    pos = PositionType()
    
    # Count material
    total_material = sum(
        len(board.pieces(pt, c)) * PIECE_POINTS[pt]
        for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
        for c in [chess.WHITE, chess.BLACK]
    )
    pos.is_endgame = total_material <= 26  # Roughly Q + R + minor each side
    
    # Check for tactical indicators
    pos.is_tactical = (
        board.is_check() or
        _has_immediate_captures(board) or
        _has_hanging_pieces(board, board.turn) or
        _has_hanging_pieces(board, not board.turn)
    )
    
    # If not tactical, it's strategic
    if not pos.is_tactical:
        pos.is_strategic = True
    
    return pos


def _has_immediate_captures(board: chess.Board) -> bool:
    """Check if there are captures available."""
    for move in board.legal_moves:
        if board.is_capture(move):
            captured = board.piece_at(move.to_square)
            if captured and captured.piece_type != chess.PAWN:
                return True
    return False


def _has_hanging_pieces(board: chess.Board, color: chess.Color) -> bool:
    """Check if a side has hanging (undefended attacked) pieces."""
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == color and piece.piece_type != chess.PAWN:
            if board.is_attacked_by(not color, sq) and not board.is_attacked_by(color, sq):
                return True
    return False


# =============================================================================
# EXPLANATION RESULT
# =============================================================================

@dataclass
class MoveExplanation:
    priority: Priority
    explanation: str
    

# =============================================================================
# PRIORITY 1: CHECKMATE DETECTION
# =============================================================================

def check_checkmate(board: chess.Board, move: chess.Move, 
                    engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """Check if move delivers or prevents checkmate."""
    board_after = board.copy()
    board_after.push(move)
    
    # Direct checkmate
    if board_after.is_checkmate():
        return MoveExplanation(Priority.CHECKMATE, "Checkmate!")
    
    # Check for forced mate (use engine)
    if engine:
        try:
            info = engine.analyse(board_after, chess.engine.Limit(depth=18))
            score = info.get("score")
            if score:
                mate = score.pov(board.turn).mate()
                if mate is not None and mate > 0 and mate <= 5:
                    if mate == 1:
                        return MoveExplanation(Priority.CHECKMATE, 
                            "This creates an unstoppable checkmate threat.")
                    return MoveExplanation(Priority.CHECKMATE,
                        f"This forces checkmate in {mate} moves.")
        except Exception:
            pass
    
    # Check if NOT playing this move allows opponent mate
    if engine:
        try:
            # Analyze position if we DON'T play the best move
            info_before = engine.analyse(board, chess.engine.Limit(depth=14))
            score = info_before.get("score")
            if score:
                mate = score.pov(not board.turn).mate()
                # If opponent has a mating attack that this move stops
                if mate is not None and mate > 0 and mate <= 3:
                    return MoveExplanation(Priority.CHECKMATE,
                        "This is the only move that prevents checkmate.")
        except Exception:
            pass
    
    return None


# =============================================================================
# PRIORITY 2: FORCED TACTICAL SEQUENCE (WINNING MATERIAL)
# =============================================================================

def check_forced_tactics(board: chess.Board, move: chess.Move,
                         engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """Check if move wins material through forced tactics."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    board_after = board.copy()
    board_after.push(move)
    gives_check = board.gives_check(move)
    
    # Immediate capture analysis
    captured = board.piece_at(move.to_square)
    if not captured and board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, not board.turn)
    
    if captured:
        captured_name = PIECE_NAMES[captured.piece_type]
        captured_value = PIECE_POINTS[captured.piece_type]
        moving_value = PIECE_POINTS[moving_piece.piece_type]
        
        # Check if capture is "free" (piece was undefended)
        was_defended = board.is_attacked_by(not board.turn, move.to_square)
        
        if not was_defended:
            if captured.piece_type == chess.QUEEN:
                return MoveExplanation(Priority.FORCED_TACTICS,
                    "Wins the queen, which is undefended.")
            elif captured_value >= 3:
                return MoveExplanation(Priority.FORCED_TACTICS,
                    f"Wins the {captured_name}, which is undefended.")
        
        # Check if capture wins exchange
        if was_defended and captured_value > moving_value:
            # Use engine to verify net material gain after exchanges
            if engine:
                try:
                    material_gain = _calculate_material_gain(board, move, engine)
                    if material_gain >= 2.5:
                        return MoveExplanation(Priority.FORCED_TACTICS,
                            f"Wins the {captured_name}. The opponent cannot adequately defend.")
                    elif material_gain >= 1.5:
                        return MoveExplanation(Priority.FORCED_TACTICS,
                            f"Wins material by capturing the {captured_name}.")
                except Exception:
                    pass
    
    # Fork detection
    fork_result = _check_fork(board, move)
    if fork_result:
        return fork_result
    
    # Pin/Skewer detection  
    pin_result = _check_pin_skewer(board, move)
    if pin_result:
        return pin_result
    
    # Discovered attack
    discovery_result = _check_discovered_attack(board, move, gives_check)
    if discovery_result:
        return discovery_result
    
    # Trapped piece
    trap_result = _check_trapped_piece(board, move)
    if trap_result:
        return trap_result
    
    return None


def _calculate_material_gain(board: chess.Board, move: chess.Move,
                             engine: chess.engine.SimpleEngine) -> float:
    """Use engine to calculate material gain after best play resolves."""
    try:
        moving_color = board.turn
        
        # Material before
        mat_before = {c: sum(len(board.pieces(pt, c)) * PIECE_POINTS[pt] 
                            for pt in PIECE_POINTS if pt != chess.KING)
                      for c in [chess.WHITE, chess.BLACK]}
        
        # Play the move and let engine respond a few times
        test_board = board.copy()
        test_board.push(move)
        
        for _ in range(4):
            if test_board.is_game_over():
                break
            result = engine.play(test_board, chess.engine.Limit(depth=10))
            if result.move:
                test_board.push(result.move)
            else:
                break
        
        # Material after
        mat_after = {c: sum(len(test_board.pieces(pt, c)) * PIECE_POINTS[pt]
                           for pt in PIECE_POINTS if pt != chess.KING)
                     for c in [chess.WHITE, chess.BLACK]}
        
        # Our gain minus their gain
        our_change = mat_after[moving_color] - mat_before[moving_color]
        their_change = mat_after[not moving_color] - mat_before[not moving_color]
        return our_change - their_change
        
    except Exception:
        return 0.0


def _check_fork(board: chess.Board, move: chess.Move) -> Optional[MoveExplanation]:
    """Check if move creates a winning fork."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    moving_value = PIECE_POINTS[moving_piece.piece_type]
    gives_check = board.gives_check(move)
    
    # Find pieces attacked by the piece that moved
    attacked_valuable = []
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != moving_piece.color:
            if board_after.is_attacked_by(moving_piece.color, sq):
                # Check if attack comes from the moved piece
                attackers = board_after.attackers(moving_piece.color, sq)
                if move.to_square in attackers:
                    value = PIECE_POINTS[piece.piece_type]
                    is_defended = board_after.is_attacked_by(not moving_piece.color, sq)
                    if piece.piece_type == chess.KING or value >= 3:
                        attacked_valuable.append((piece, sq, is_defended, value))
    
    if len(attacked_valuable) >= 2:
        # Check if this fork actually wins material
        has_king = any(p.piece_type == chess.KING for p, _, _, _ in attacked_valuable)
        
        if has_king:
            # King must move - what else do we win?
            for piece, sq, is_defended, value in attacked_valuable:
                if piece.piece_type != chess.KING:
                    if not is_defended or moving_value < value:
                        piece_names = [PIECE_NAMES[p.piece_type] for p, _, _, _ in attacked_valuable[:2]]
                        if gives_check:
                            return MoveExplanation(Priority.FORCED_TACTICS,
                                f"This check forks the {' and '.join(piece_names)}, winning material.")
                        return MoveExplanation(Priority.FORCED_TACTICS,
                            f"Forks the {' and '.join(piece_names)}, winning material.")
        else:
            # No king - check if we win something
            for piece, sq, is_defended, value in attacked_valuable:
                if not is_defended or moving_value < value:
                    piece_names = [PIECE_NAMES[p.piece_type] for p, _, _, _ in attacked_valuable[:2]]
                    return MoveExplanation(Priority.FORCED_TACTICS,
                        f"Forks the {' and '.join(piece_names)}. The opponent cannot save both.")
    
    return None


def _check_pin_skewer(board: chess.Board, move: chess.Move) -> Optional[MoveExplanation]:
    """Check if move creates a pin or skewer."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece or moving_piece.piece_type not in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
        return None
    
    # Check rays from the moved piece
    for direction in _get_piece_directions(moving_piece.piece_type):
        pieces_on_ray = []
        sq = move.to_square
        
        while True:
            sq = _step_square(sq, direction)
            if sq is None:
                break
            piece = board_after.piece_at(sq)
            if piece:
                if piece.color != moving_piece.color:
                    pieces_on_ray.append((piece, sq))
                else:
                    break
                if len(pieces_on_ray) >= 2:
                    break
        
        if len(pieces_on_ray) >= 2:
            front, back = pieces_on_ray[0], pieces_on_ray[1]
            front_value = PIECE_POINTS[front[0].piece_type]
            back_value = PIECE_POINTS[back[0].piece_type]
            
            # Pin: less valuable piece in front of more valuable (or king)
            if front[0].piece_type != chess.KING and (back[0].piece_type == chess.KING or back_value > front_value):
                pinned_name = PIECE_NAMES[front[0].piece_type]
                if back[0].piece_type == chess.KING:
                    return MoveExplanation(Priority.FORCED_TACTICS,
                        f"Pins the {pinned_name} to the king. It cannot move.")
                return MoveExplanation(Priority.FORCED_TACTICS,
                    f"Pins the {pinned_name}, restricting its movement.")
            
            # Skewer: more valuable piece must move, exposing piece behind
            if front_value >= back_value or front[0].piece_type == chess.KING:
                front_name = PIECE_NAMES[front[0].piece_type]
                back_name = PIECE_NAMES[back[0].piece_type]
                if front[0].piece_type == chess.KING:
                    return MoveExplanation(Priority.FORCED_TACTICS,
                        f"Skewers the king, winning the {back_name} behind it.")
                return MoveExplanation(Priority.FORCED_TACTICS,
                    f"Skewers the {front_name} and {back_name}.")
    
    return None


def _check_discovered_attack(board: chess.Board, move: chess.Move, 
                             gives_check: bool) -> Optional[MoveExplanation]:
    """Check for discovered attacks."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    # Check if moving unblocked an attack
    from_sq = move.from_square
    
    for sq in chess.SQUARES:
        behind_piece = board.piece_at(sq)
        if behind_piece and behind_piece.color == moving_piece.color:
            if behind_piece.piece_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                # Check if from_square was between this piece and a target
                direction = _direction_between(sq, from_sq)
                if direction:
                    target_sq = from_sq
                    while True:
                        target_sq = _step_square(target_sq, direction)
                        if target_sq is None:
                            break
                        target = board_after.piece_at(target_sq)
                        if target:
                            if target.color != moving_piece.color:
                                if target.piece_type == chess.KING:
                                    if gives_check:
                                        # The check itself IS the discovered check
                                        captured = board.piece_at(move.to_square)
                                        if captured and PIECE_POINTS[captured.piece_type] >= 3:
                                            return MoveExplanation(Priority.FORCED_TACTICS,
                                                f"Discovered check while capturing the {PIECE_NAMES[captured.piece_type]}.")
                                elif PIECE_POINTS[target.piece_type] >= 3:
                                    behind_name = PIECE_NAMES[behind_piece.piece_type]
                                    target_name = PIECE_NAMES[target.piece_type]
                                    return MoveExplanation(Priority.FORCED_TACTICS,
                                        f"Discovered attack on the {target_name} by the {behind_name}.")
                            break
    
    return None


def _check_trapped_piece(board: chess.Board, move: chess.Move) -> Optional[MoveExplanation]:
    """Check if move traps an opponent piece."""
    board_after = board.copy()
    board_after.push(move)
    
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color == board_after.turn and piece.piece_type != chess.PAWN:
            if board_after.is_attacked_by(not board_after.turn, sq):
                # Check if piece has any safe escape
                has_escape = False
                for m in board_after.legal_moves:
                    if m.from_square == sq:
                        test = board_after.copy()
                        test.push(m)
                        if not test.is_attacked_by(not piece.color, m.to_square):
                            has_escape = True
                            break
                
                if not has_escape and PIECE_POINTS[piece.piece_type] >= 3:
                    piece_name = PIECE_NAMES[piece.piece_type]
                    return MoveExplanation(Priority.FORCED_TACTICS,
                        f"Traps the {piece_name}. It has no safe escape.")
    
    return None


# =============================================================================
# PRIORITY 3: PREVENTING A CRITICAL THREAT
# =============================================================================

def check_prevent_threat(board: chess.Board, move: chess.Move,
                         engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """Check if move prevents an immediate opponent threat."""
    
    # First, what threats does opponent have if we pass?
    # We simulate by checking opponent's best move in current position
    if not engine:
        return None
    
    try:
        # What would opponent do if it were their turn?
        flipped = board.copy()
        flipped.turn = not flipped.turn
        if not flipped.is_valid():
            return None
            
        # Find their top threat
        infos = engine.analyse(flipped, chess.engine.Limit(depth=12), multipv=1)
        if not infos:
            return None
        
        info = infos if not isinstance(infos, list) else infos[0]
        pv = info.get("pv", [])
        if not pv:
            return None
        
        threat_move = pv[0]
        
        # Does our move stop this threat?
        board_after = board.copy()
        board_after.push(move)
        
        # Is the threat move still possible?
        flipped_after = board_after.copy()
        flipped_after.turn = not flipped_after.turn
        
        if threat_move in flipped_after.legal_moves:
            # Threat still exists, this might not be the reason
            return None
        
        # We stopped the threat! What was it?
        threat_captured = flipped.piece_at(threat_move.to_square)
        threat_gives_check = flipped.gives_check(threat_move)
        
        if threat_gives_check:
            return MoveExplanation(Priority.PREVENT_THREAT,
                "Prevents a dangerous check that would have caused problems.")
        
        if threat_captured:
            threat_name = PIECE_NAMES[threat_captured.piece_type]
            if threat_captured.piece_type == chess.QUEEN:
                return MoveExplanation(Priority.PREVENT_THREAT,
                    f"Defends the queen, which was threatened.")
            elif PIECE_POINTS[threat_captured.piece_type] >= 3:
                return MoveExplanation(Priority.PREVENT_THREAT,
                    f"Defends the {threat_name}, which was under attack.")
        
    except Exception:
        pass
    
    return None


# =============================================================================
# PRIORITY 4: KING SAFETY
# =============================================================================

def check_king_safety(board: chess.Board, move: chess.Move,
                      engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """Check if move relates to king safety (attack or defense)."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    board_after = board.copy()
    board_after.push(move)
    gives_check = board.gives_check(move)
    
    opponent_king_sq = board.king(not board.turn)
    our_king_sq = board.king(board.turn)
    
    # ATTACKING: Does move increase pressure on opponent's king?
    if opponent_king_sq:
        # Moving piece toward king zone
        king_zone = _get_king_zone(opponent_king_sq)
        
        if gives_check:
            # Check with a threat
            captured = board.piece_at(move.to_square)
            if captured and PIECE_POINTS[captured.piece_type] >= 3:
                return None  # This is a tactical win, not just king safety
            
            # Count attackers near king after the check
            attackers_before = _count_attackers_near_king(board, opponent_king_sq, board.turn)
            attackers_after = _count_attackers_near_king(board_after, board_after.king(not board.turn), board.turn)
            
            if attackers_after > attackers_before:
                return MoveExplanation(Priority.KING_SAFETY,
                    "This check increases pressure on the king and limits its escape squares.")
        
        # Bringing piece into attack
        if move.to_square in king_zone and move.from_square not in king_zone:
            if moving_piece.piece_type in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                piece_name = PIECE_NAMES[moving_piece.piece_type]
                return MoveExplanation(Priority.KING_SAFETY,
                    f"Brings the {piece_name} into the attack on the king.")
    
    # DEFENDING: Does move improve our king's safety?
    if our_king_sq:
        # Castling
        if moving_piece.piece_type == chess.KING:
            if abs(chess.square_file(move.from_square) - chess.square_file(move.to_square)) == 2:
                return MoveExplanation(Priority.KING_SAFETY,
                    "Castles to safety, protecting the king and connecting the rooks.")
    
    return None


def _get_king_zone(king_sq: int) -> Set[int]:
    """Get squares in the king's zone (3x3 around king + nearby files)."""
    zone = set()
    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
    
    for df in range(-2, 3):
        for dr in range(-2, 3):
            f, r = king_file + df, king_rank + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                zone.add(chess.square(f, r))
    return zone


def _count_attackers_near_king(board: chess.Board, king_sq: int, 
                               attacker_color: chess.Color) -> int:
    """Count how many attacking pieces are near the king."""
    if king_sq is None:
        return 0
    zone = _get_king_zone(king_sq)
    count = 0
    for sq in zone:
        if board.is_attacked_by(attacker_color, sq):
            count += 1
    return count


# =============================================================================
# PRIORITY 5-12: LOWER PRIORITY EXPLANATIONS
# =============================================================================

def check_only_move(board: chess.Board, move: chess.Move,
                    engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """Check if this is effectively the only good move."""
    if not engine:
        return None
    
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=14), multipv=3)
        if not isinstance(infos, list):
            infos = [infos]
        
        if len(infos) < 2:
            return MoveExplanation(Priority.ONLY_MOVE,
                "This is the only move that maintains the position.")
        
        # Check if second-best is significantly worse
        best_score = infos[0].get("score")
        second_score = infos[1].get("score") if len(infos) > 1 else None
        
        if best_score and second_score:
            best_cp = best_score.pov(board.turn).score(mate_score=10000)
            second_cp = second_score.pov(board.turn).score(mate_score=10000)
            
            if best_cp is not None and second_cp is not None:
                if best_cp - second_cp > 150:  # >1.5 pawns difference
                    return MoveExplanation(Priority.ONLY_MOVE,
                        "This is the only move that doesn't lose the advantage.")
    except Exception:
        pass
    
    return None


def check_initiative(board: chess.Board, move: chess.Move) -> Optional[MoveExplanation]:
    """Check if move maintains or seizes initiative."""
    gives_check = board.gives_check(move)
    
    board_after = board.copy()
    board_after.push(move)
    
    # Count threats created
    threats_created = 0
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != board.turn and piece.piece_type != chess.PAWN:
            was_attacked = board.is_attacked_by(board.turn, sq)
            is_attacked = board_after.is_attacked_by(board.turn, sq)
            if is_attacked and not was_attacked:
                threats_created += 1
    
    if gives_check and threats_created > 0:
        return MoveExplanation(Priority.INITIATIVE,
            "This check maintains the initiative and creates additional threats.")
    
    if threats_created >= 2:
        return MoveExplanation(Priority.INITIATIVE,
            "Creates multiple threats, keeping the pressure on.")
    
    return None


def check_endgame(board: chess.Board, move: chess.Move,
                  pos_type: PositionType) -> Optional[MoveExplanation]:
    """Check for endgame-specific explanations."""
    if not pos_type.is_endgame:
        return None
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    # King activity
    if moving_piece.piece_type == chess.KING:
        to_file = chess.square_file(move.to_square)
        to_rank = chess.square_rank(move.to_square)
        
        # Moving toward center or toward action
        if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
            return MoveExplanation(Priority.ENDGAME_TRANSITION,
                "Activates the king. In the endgame, the king becomes a fighting piece.")
    
    # Pawn promotion potential
    if moving_piece.piece_type == chess.PAWN:
        to_rank = chess.square_rank(move.to_square)
        if (moving_piece.color == chess.WHITE and to_rank >= 5) or \
           (moving_piece.color == chess.BLACK and to_rank <= 2):
            return MoveExplanation(Priority.ENDGAME_TRANSITION,
                "Advances the passed pawn, creating promotion threats.")
    
    return None


def check_positional(board: chess.Board, move: chess.Move) -> Optional[MoveExplanation]:
    """Fallback positional explanation."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return MoveExplanation(Priority.POSITIONAL, "Improves the position.")
    
    piece_name = PIECE_NAMES[moving_piece.piece_type]
    to_sq = chess.square_name(move.to_square)
    
    # Piece development
    from_rank = chess.square_rank(move.from_square)
    is_back_rank = (moving_piece.color == chess.WHITE and from_rank == 0) or \
                   (moving_piece.color == chess.BLACK and from_rank == 7)
    
    if is_back_rank and moving_piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
        return MoveExplanation(Priority.PIECE_ACTIVITY,
            f"Develops the {piece_name} to an active square.")
    
    # Central control
    to_file = chess.square_file(move.to_square)
    to_rank = chess.square_rank(move.to_square)
    if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
        return MoveExplanation(Priority.POSITIONAL,
            f"The {piece_name} moves to {to_sq}, controlling key central squares.")
    
    return MoveExplanation(Priority.POSITIONAL,
        f"The {piece_name} improves to {to_sq}.")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _get_piece_directions(piece_type: chess.PieceType) -> List[Tuple[int, int]]:
    """Get movement directions for sliding pieces."""
    diagonals = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    straights = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    
    if piece_type == chess.BISHOP:
        return diagonals
    elif piece_type == chess.ROOK:
        return straights
    elif piece_type == chess.QUEEN:
        return diagonals + straights
    return []


def _step_square(sq: int, direction: Tuple[int, int]) -> Optional[int]:
    """Step one square in a direction, or None if off board."""
    f = chess.square_file(sq) + direction[0]
    r = chess.square_rank(sq) + direction[1]
    if 0 <= f <= 7 and 0 <= r <= 7:
        return chess.square(f, r)
    return None


def _direction_between(from_sq: int, to_sq: int) -> Optional[Tuple[int, int]]:
    """Get the direction from one square toward another, if on same line."""
    df = chess.square_file(to_sq) - chess.square_file(from_sq)
    dr = chess.square_rank(to_sq) - chess.square_rank(from_sq)
    
    if df == 0 and dr == 0:
        return None
    
    # Check if on same line
    is_straight = df == 0 or dr == 0
    is_diagonal = abs(df) == abs(dr)
    
    if not is_straight and not is_diagonal:
        return None
    
    # Normalize
    if df != 0:
        df = df // abs(df)
    if dr != 0:
        dr = dr // abs(dr)
    
    return (df, dr)


# =============================================================================
# MAIN EXPLANATION GENERATOR
# =============================================================================

def generate_move_explanation(
    board: chess.Board,
    best_move: chess.Move,
    phase: str = "middlegame",
) -> str:
    """
    Generate a short, accurate, human-toned explanation for why a move is best.
    
    Uses strict priority hierarchy - stops at first applicable explanation.
    """
    engine = _open_engine()
    
    try:
        pos_type = classify_position(board)
        
        # PRIORITY 1: Checkmate
        result = check_checkmate(board, best_move, engine)
        if result:
            return result.explanation
        
        # PRIORITY 2: Forced tactics (winning material)
        result = check_forced_tactics(board, best_move, engine)
        if result:
            return result.explanation
        
        # PRIORITY 3: Preventing critical threat
        result = check_prevent_threat(board, best_move, engine)
        if result:
            return result.explanation
        
        # PRIORITY 4: King safety
        result = check_king_safety(board, best_move, engine)
        if result:
            return result.explanation
        
        # PRIORITY 5: Only move
        result = check_only_move(board, best_move, engine)
        if result:
            return result.explanation
        
        # PRIORITY 6: Initiative
        result = check_initiative(board, best_move)
        if result:
            return result.explanation
        
        # PRIORITY 8: Endgame
        result = check_endgame(board, best_move, pos_type)
        if result:
            return result.explanation
        
        # PRIORITY 12: Positional (fallback)
        result = check_positional(board, best_move)
        return result.explanation
        
    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass


# =============================================================================
# PUBLIC API
# =============================================================================

def generate_puzzle_explanation_enhanced(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int = 0,
    phase: str = "middlegame",
) -> str:
    """
    Enhanced puzzle explanation using hierarchical priority system.
    
    This is the main entry point that puzzle_engine.py calls.
    """
    return generate_move_explanation(board, best_move, phase)


# CPL threshold for viable moves
VIABLE_CPL_THRESHOLD = 30


def is_move_viable(board: chess.Board, move: chess.Move, depth: int = 14) -> Tuple[bool, int]:
    """
    Check if a move is viable (CPL < 30 compared to best).
    
    Returns: (is_viable, cpl)
    """
    engine = _open_engine()
    if not engine:
        return True, 0  # Assume viable if no engine
    
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=5)
        if not isinstance(infos, list):
            infos = [infos]
        
        if not infos:
            return True, 0
        
        # Find the best evaluation
        best_info = infos[0]
        best_pv = best_info.get("pv", [])
        best_score = best_info.get("score")
        
        if not best_score:
            return True, 0
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000) or 0
        
        # Find our move's evaluation
        for info in infos:
            pv = info.get("pv", [])
            if pv and pv[0] == move:
                score = info.get("score")
                if score:
                    move_cp = score.pov(board.turn).score(mate_score=10000) or 0
                    cpl = best_cp - move_cp
                    return cpl <= VIABLE_CPL_THRESHOLD, max(0, cpl)
        
        # Move not in top 5 - analyze it specifically
        board_after = board.copy()
        board_after.push(move)
        info = engine.analyse(board_after, chess.engine.Limit(depth=depth))
        score = info.get("score")
        if score:
            # Score is from opponent's perspective after our move
            move_cp = -score.pov(board_after.turn).score(mate_score=10000) or 0
            cpl = best_cp - move_cp
            return cpl <= VIABLE_CPL_THRESHOLD, max(0, cpl)
        
        return False, 100
        
    finally:
        try:
            engine.quit()
        except Exception:
            pass
