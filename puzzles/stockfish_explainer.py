"""
Stockfish-Based Move Explanation Engine (v2 - Dominance Model)

CORE DESIGN PRINCIPLES:
=======================

1. DOMINANCE, NOT DETECTION
   - Priority hierarchy is a DOMINANCE model, not detection order
   - A lower-priority factor is IGNORED, even if true, when higher-priority applies
   - Choose the highest applicable priority and STOP - hard invariant

2. SINGLE CAUSAL EXPLANATION
   - Every explanation identifies ONE main reason
   - Never combine multiple factors ("prevents mate AND wins a pawn" is WRONG)
   - Example: Move prevents mate and also wins a pawn → "This is the only move 
     that stops checkmate." (The pawn is irrelevant)

3. CONCRETE COLLAPSE, NOT EVAL GAPS
   - "Only move" means alternatives allow concrete tactical/material/positional failure
   - Not just "eval drops" - something specific must break

4. CAUSALITY, NOT PATTERNS
   - Tactics must explain WHY opponent cannot respond
   - "Forks the king and rook" is incomplete
   - "This check forks the king and rook, and the rook cannot escape" is correct

5. USER MISTAKE MODELING
   - Explanations are CORRECTIVE, not neutral
   - Final step: "What did the human likely overlook?"

PRIORITY HIERARCHY (Dominance Order):
=====================================
1. CHECKMATE - Forced mate or preventing immediate mate
2. FORCED_TACTICS - Material win with unstoppable execution  
3. PREVENT_THREAT - Stopping an irreversible loss
4. KING_SAFETY_URGENT - Critical king danger (not general improvement)
5. ONLY_MOVE - Structural collapse of all alternatives
6. INITIATIVE - Tempo and pressure when concrete
7. SACRIFICE_COMPENSATION - Material for concrete compensation
8. ENDGAME_TRANSITION - Forced winning/drawing transition
9. PROPHYLAXIS - Preventing specific opponent plans
10. PIECE_ACTIVITY - Piece coordination
11. PAWN_STRUCTURE - Structural improvements
12. POSITIONAL - General positional edge

WHAT WE NEVER DO:
=================
- Invent best moves (Stockfish's job)
- Mention centipawns, depth, or engine jargon
- List multiple reasons
- Say "only move" when nothing concrete is at stake
- Explain tactics without stating why they're unstoppable
- Mix high and low priority explanations
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Set
from enum import IntEnum
import os

import chess
import chess.engine


# =============================================================================
# PRIORITY LEVELS (lower = higher priority = dominates)
# =============================================================================

class Priority(IntEnum):
    CHECKMATE = 1
    FORCED_TACTICS = 2
    PREVENT_THREAT = 3
    KING_SAFETY_URGENT = 4
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
# PIECE VALUES (human terms)
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
# CPL THRESHOLD FOR VIABLE MOVES
# =============================================================================

VIABLE_CPL_THRESHOLD = 50  # 50 centipawns = 0.5 pawns


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
# EXPLANATION RESULT
# =============================================================================

@dataclass
class MoveExplanation:
    priority: Priority
    explanation: str
    user_likely_missed: Optional[str] = None  # What the human probably overlooked


# =============================================================================
# POSITION CONTEXT
# =============================================================================

@dataclass
class PositionContext:
    """Rich context about the position for explanation generation."""
    is_endgame: bool = False
    total_material: int = 0
    our_material: int = 0
    their_material: int = 0
    we_are_better: bool = False
    we_are_worse: bool = False
    eval_cp: Optional[int] = None
    in_check: bool = False
    

def _build_context(board: chess.Board, engine: Optional[chess.engine.SimpleEngine]) -> PositionContext:
    """Build rich position context."""
    ctx = PositionContext()
    
    # Material counts
    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
        for color in [chess.WHITE, chess.BLACK]:
            val = len(board.pieces(pt, color)) * PIECE_POINTS[pt]
            ctx.total_material += val
            if color == board.turn:
                ctx.our_material += val
            else:
                ctx.their_material += val
    
    ctx.is_endgame = ctx.total_material <= 26
    ctx.in_check = board.is_check()
    
    # Engine eval for context
    if engine:
        try:
            info = engine.analyse(board, chess.engine.Limit(depth=12))
            score = info.get("score")
            if score:
                ctx.eval_cp = score.pov(board.turn).score(mate_score=10000)
                if ctx.eval_cp is not None:
                    ctx.we_are_better = ctx.eval_cp > 100
                    ctx.we_are_worse = ctx.eval_cp < -100
        except Exception:
            pass
    
    return ctx


# =============================================================================
# PRIORITY 1: CHECKMATE (Absolute Dominance)
# =============================================================================

def _check_checkmate(board: chess.Board, move: chess.Move,
                     engine: Optional[chess.engine.SimpleEngine]) -> Optional[MoveExplanation]:
    """
    Check for checkmate delivery or prevention.
    
    This is the HIGHEST priority - if this applies, nothing else matters.
    """
    board_after = board.copy()
    board_after.push(move)
    
    # Immediate checkmate
    if board_after.is_checkmate():
        return MoveExplanation(
            Priority.CHECKMATE,
            "Checkmate!",
            "The mating pattern was available."
        )
    
    if not engine:
        return None
    
    try:
        # Check for forced mate sequence
        info = engine.analyse(board_after, chess.engine.Limit(depth=18))
        score = info.get("score")
        if score:
            mate = score.pov(board.turn).mate()
            if mate is not None and mate > 0 and mate <= 5:
                if mate == 1:
                    return MoveExplanation(
                        Priority.CHECKMATE,
                        "This creates an unstoppable checkmate threat.",
                        "The mating net was forming."
                    )
                return MoveExplanation(
                    Priority.CHECKMATE,
                    f"This forces checkmate in {mate} moves. The opponent has no defense.",
                    "The forced mating sequence was available."
                )
        
        # Check if we're PREVENTING mate against us
        # Analyze what happens if we DON'T play this move
        info_before = engine.analyse(board, chess.engine.Limit(depth=14), multipv=3)
        if isinstance(info_before, list):
            for alt_info in info_before:
                alt_score = alt_info.get("score")
                if alt_score:
                    opp_mate = alt_score.pov(not board.turn).mate()
                    if opp_mate is not None and opp_mate > 0 and opp_mate <= 3:
                        return MoveExplanation(
                            Priority.CHECKMATE,
                            "This is the only move that prevents checkmate.",
                            "There was an immediate mating threat."
                        )
        
    except Exception:
        pass
    
    return None


# =============================================================================
# PRIORITY 2: FORCED TACTICS (Material Win with Unstoppable Execution)
# =============================================================================

def _check_forced_tactics(board: chess.Board, move: chess.Move,
                          engine: Optional[chess.engine.SimpleEngine],
                          ctx: PositionContext) -> Optional[MoveExplanation]:
    """
    Check for material-winning tactics.
    
    KEY PRINCIPLE: Every tactic explanation must state WHY it cannot be stopped.
    """
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
        
        # Undefended capture - explain WHY it's free
        was_defended = board.is_attacked_by(not board.turn, move.to_square)
        
        if not was_defended:
            if captured.piece_type == chess.QUEEN:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    "Wins the queen, which has no defender.",
                    f"The {captured_name} was left unprotected."
                )
            elif captured_value >= 3:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Wins the {captured_name}. It has no defender and cannot escape.",
                    f"The {captured_name} was hanging."
                )
        
        # Capture where we win the exchange - verify with engine
        if was_defended and captured_value > moving_value and engine:
            try:
                net_gain = _calculate_material_outcome(board, move, engine)
                if net_gain >= 2:  # At least 2 points net
                    return MoveExplanation(
                        Priority.FORCED_TACTICS,
                        f"Wins material. After all captures, you come out ahead by {net_gain} points.",
                        "The piece was overloaded or couldn't recapture profitably."
                    )
            except Exception:
                pass
    
    # Check for fork
    fork_result = _check_fork_with_causality(board, move, gives_check)
    if fork_result:
        return fork_result
    
    # Check for pin/skewer
    pin_result = _check_pin_skewer_with_causality(board, move)
    if pin_result:
        return pin_result
    
    # Check for discovered attack
    disc_result = _check_discovered_attack_with_causality(board, move, gives_check)
    if disc_result:
        return disc_result
    
    # Check for trapped piece
    trap_result = _check_trapped_piece_with_causality(board, move)
    if trap_result:
        return trap_result
    
    return None


def _calculate_material_outcome(board: chess.Board, move: chess.Move,
                                engine: chess.engine.SimpleEngine) -> int:
    """Calculate net material gain after best play resolves."""
    try:
        moving_color = board.turn
        
        # Material before
        mat_before = {c: sum(len(board.pieces(pt, c)) * PIECE_POINTS[pt]
                            for pt in PIECE_POINTS if pt != chess.KING)
                      for c in [chess.WHITE, chess.BLACK]}
        
        # Simulate 4 moves of best play
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
        return int(our_change - their_change)
        
    except Exception:
        return 0


def _check_fork_with_causality(board: chess.Board, move: chess.Move,
                               gives_check: bool) -> Optional[MoveExplanation]:
    """Check for fork and explain WHY it wins material."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    moving_name = PIECE_NAMES[moving_piece.piece_type]
    moving_value = PIECE_POINTS[moving_piece.piece_type]
    
    # Find pieces attacked by the moved piece
    attacked_pieces = []
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != moving_piece.color:
            attackers = board_after.attackers(moving_piece.color, sq)
            if move.to_square in attackers:
                is_defended = board_after.is_attacked_by(not moving_piece.color, sq)
                value = PIECE_POINTS[piece.piece_type]
                attacked_pieces.append({
                    'piece': piece,
                    'square': sq,
                    'defended': is_defended,
                    'value': value,
                    'name': PIECE_NAMES[piece.piece_type]
                })
    
    if len(attacked_pieces) < 2:
        return None
    
    # Sort by value descending
    attacked_pieces.sort(key=lambda x: -x['value'])
    
    has_king = any(p['piece'].piece_type == chess.KING for p in attacked_pieces)
    
    if has_king:
        # King must move - what's the second piece?
        for target in attacked_pieces:
            if target['piece'].piece_type != chess.KING:
                # Can they save this piece while dealing with check?
                can_save = _can_save_piece_while_handling_check(
                    board_after, target['square'], target['piece']
                )
                
                if not can_save:
                    names = "king and " + target['name']
                    if gives_check:
                        return MoveExplanation(
                            Priority.FORCED_TACTICS,
                            f"This check forks the {names}. The king must move, leaving the {target['name']} to be captured.",
                            f"The {moving_name} attacks two pieces at once."
                        )
                    return MoveExplanation(
                        Priority.FORCED_TACTICS,
                        f"Forks the {names}. The king must move, and the {target['name']} cannot escape.",
                        f"The {moving_name} threatens two pieces simultaneously."
                    )
    else:
        # No king - find the valuable piece that can't escape
        for target in attacked_pieces:
            if not target['defended'] or target['value'] > moving_value:
                # Can opponent save both?
                other = [p for p in attacked_pieces if p != target][0]
                names = f"{target['name']} and {other['name']}"
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Forks the {names}. The opponent cannot save both pieces.",
                    "Two valuable pieces were on the same attacking line."
                )
    
    return None


def _can_save_piece_while_handling_check(board: chess.Board, piece_sq: int,
                                         piece: chess.Piece) -> bool:
    """Check if opponent can save the piece while getting out of check."""
    if not board.is_check():
        return False
    
    for move in board.legal_moves:
        board_test = board.copy()
        board_test.push(move)
        
        # Did they save the piece?
        saved_piece = board_test.piece_at(piece_sq)
        if saved_piece and saved_piece.color == piece.color:
            continue  # Piece still there but check might still be an issue
        
        # Did they move the piece to safety?
        if move.from_square == piece_sq:
            # Check if new square is safe
            if not board_test.is_attacked_by(not piece.color, move.to_square):
                return True
    
    return False


def _check_pin_skewer_with_causality(board: chess.Board, 
                                      move: chess.Move) -> Optional[MoveExplanation]:
    """Check for pin/skewer and explain why it wins material."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece or moving_piece.piece_type not in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
        return None
    
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
            front_piece, front_sq = front
            back_piece, back_sq = back
            front_value = PIECE_POINTS[front_piece.piece_type]
            back_value = PIECE_POINTS[back_piece.piece_type]
            front_name = PIECE_NAMES[front_piece.piece_type]
            back_name = PIECE_NAMES[back_piece.piece_type]
            
            # Pin: front piece cannot move because it exposes more valuable piece
            if front_piece.piece_type != chess.KING and back_piece.piece_type == chess.KING:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Pins the {front_name} to the king. It cannot move without exposing the king to check.",
                    f"The {front_name} was blocking the attack on the king."
                )
            
            if front_piece.piece_type != chess.KING and back_value > front_value:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Pins the {front_name} to the {back_name}. Moving the {front_name} would lose the {back_name}.",
                    f"The {front_name} was shielding a more valuable piece."
                )
            
            # Skewer: front piece must move, exposing piece behind
            if front_piece.piece_type == chess.KING:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Skewers the king and {back_name}. The king must move, and the {back_name} will be captured.",
                    "The king was in line with a valuable piece."
                )
            
            if front_value >= back_value:
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Skewers the {front_name} and {back_name}. Moving the {front_name} exposes the {back_name}.",
                    "Two pieces were on the same diagonal/file."
                )
    
    return None


def _check_discovered_attack_with_causality(board: chess.Board, move: chess.Move,
                                            gives_check: bool) -> Optional[MoveExplanation]:
    """Check for discovered attack and explain the threat."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    from_sq = move.from_square
    
    # Check if moving unblocked an attack from a piece behind
    for sq in chess.SQUARES:
        behind_piece = board.piece_at(sq)
        if behind_piece and behind_piece.color == moving_piece.color:
            if behind_piece.piece_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                direction = _direction_between(sq, from_sq)
                if direction:
                    # Find what's now attacked
                    target_sq = from_sq
                    while True:
                        target_sq = _step_square(target_sq, direction)
                        if target_sq is None:
                            break
                        target = board_after.piece_at(target_sq)
                        if target:
                            if target.color != moving_piece.color:
                                target_name = PIECE_NAMES[target.piece_type]
                                behind_name = PIECE_NAMES[behind_piece.piece_type]
                                
                                if target.piece_type == chess.KING and gives_check:
                                    # The check IS the discovered attack
                                    captured = board.piece_at(move.to_square)
                                    if captured and PIECE_POINTS[captured.piece_type] >= 3:
                                        cap_name = PIECE_NAMES[captured.piece_type]
                                        return MoveExplanation(
                                            Priority.FORCED_TACTICS,
                                            f"Discovered check while capturing the {cap_name}. The king must respond, so the {cap_name} is won.",
                                            f"The {PIECE_NAMES[moving_piece.piece_type]} was blocking the {behind_name}'s attack."
                                        )
                                
                                if PIECE_POINTS[target.piece_type] >= 3:
                                    return MoveExplanation(
                                        Priority.FORCED_TACTICS,
                                        f"Discovered attack on the {target_name} by the {behind_name}. The {target_name} cannot escape the newly opened line.",
                                        f"Moving the {PIECE_NAMES[moving_piece.piece_type]} unleashed a hidden attack."
                                    )
                            break
    
    return None


def _check_trapped_piece_with_causality(board: chess.Board, 
                                         move: chess.Move) -> Optional[MoveExplanation]:
    """Check if move traps an opponent piece with no escape."""
    board_after = board.copy()
    board_after.push(move)
    
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color == board_after.turn and piece.piece_type != chess.PAWN:
            if not board_after.is_attacked_by(not board_after.turn, sq):
                continue  # Not attacked
            
            # Count escape squares
            escape_squares = 0
            for m in board_after.legal_moves:
                if m.from_square == sq:
                    test = board_after.copy()
                    test.push(m)
                    if not test.is_attacked_by(not piece.color, m.to_square):
                        escape_squares += 1
            
            if escape_squares == 0 and PIECE_POINTS[piece.piece_type] >= 3:
                piece_name = PIECE_NAMES[piece.piece_type]
                return MoveExplanation(
                    Priority.FORCED_TACTICS,
                    f"Traps the {piece_name}. Every escape square is covered.",
                    f"The {piece_name} ran out of safe squares."
                )
    
    return None


# =============================================================================
# PRIORITY 3: PREVENTING IRREVERSIBLE LOSS
# =============================================================================

def _check_prevent_threat(board: chess.Board, move: chess.Move,
                          engine: Optional[chess.engine.SimpleEngine],
                          ctx: PositionContext) -> Optional[MoveExplanation]:
    """
    Check if move prevents a critical threat.
    
    KEY PRINCIPLE: Threats must be ranked by IRREVERSIBILITY, not just existence.
    "Without this move, the rook is lost with no compensation."
    """
    if not engine:
        return None
    
    try:
        # What's our eval after the move?
        board_after = board.copy()
        board_after.push(move)
        
        info_after = engine.analyse(board_after, chess.engine.Limit(depth=12))
        score_after = info_after.get("score")
        if not score_after:
            return None
        eval_after = score_after.pov(board.turn).score(mate_score=10000)
        
        # What if we made a "neutral" move? Find a significantly worse alternative.
        info_alternatives = engine.analyse(board, chess.engine.Limit(depth=12), multipv=5)
        if not isinstance(info_alternatives, list):
            return None
        
        worst_reasonable = None
        for alt in info_alternatives[1:]:  # Skip the best move
            alt_pv = alt.get("pv", [])
            if not alt_pv:
                continue
            alt_score = alt.get("score")
            if alt_score:
                alt_eval = alt_score.pov(board.turn).score(mate_score=10000)
                if alt_eval is not None and eval_after is not None:
                    loss = eval_after - alt_eval
                    if loss > 150:  # >1.5 pawns worse
                        # What did we lose?
                        alt_board = board.copy()
                        alt_board.push(alt_pv[0])
                        
                        # Check what opponent threatens now
                        threat_info = engine.analyse(alt_board, chess.engine.Limit(depth=10))
                        threat_pv = threat_info.get("pv", [])
                        if threat_pv:
                            threat_move = threat_pv[0]
                            threatened = alt_board.piece_at(threat_move.to_square)
                            if threatened and PIECE_POINTS[threatened.piece_type] >= 3:
                                threat_name = PIECE_NAMES[threatened.piece_type]
                                return MoveExplanation(
                                    Priority.PREVENT_THREAT,
                                    f"Without this move, the {threat_name} is lost with no compensation.",
                                    f"The {threat_name} was in danger."
                                )
                        
                        # Generic threat prevention
                        return MoveExplanation(
                            Priority.PREVENT_THREAT,
                            "This move is necessary to prevent a significant material or positional loss.",
                            "There was a critical threat that had to be addressed."
                        )
        
    except Exception:
        pass
    
    return None


# =============================================================================
# PRIORITY 4: KING SAFETY (URGENT ONLY)
# =============================================================================

def _check_king_safety_urgent(board: chess.Board, move: chess.Move,
                              engine: Optional[chess.engine.SimpleEngine],
                              ctx: PositionContext) -> Optional[MoveExplanation]:
    """
    Check for URGENT king safety - not general improvements.
    
    KEY PRINCIPLE: Distinguish urgent king danger from latent safety.
    "Castles to safety" in a quiet position is LOW priority, not Level 4.
    
    Urgent king safety requires:
    - Concrete lines opening toward king
    - Defenders being removed
    - Imminent tactical threats involving the king
    """
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    board_after = board.copy()
    board_after.push(move)
    gives_check = board.gives_check(move)
    
    opponent_king_sq = board.king(not board.turn)
    our_king_sq = board.king(board.turn)
    
    # ATTACKING: Increasing concrete pressure on exposed king
    if opponent_king_sq and engine:
        # Only report king attacks if there's REAL danger
        try:
            # Check if opponent's king is actually in danger
            attackers_before = _count_attackers_in_king_zone(board, opponent_king_sq, board.turn)
            attackers_after = _count_attackers_in_king_zone(board_after, board_after.king(not board.turn), board.turn)
            
            # Is the king's pawn shield compromised?
            king_exposed = _is_king_exposed(board, not board.turn)
            
            if king_exposed and attackers_after > attackers_before:
                if gives_check:
                    return MoveExplanation(
                        Priority.KING_SAFETY_URGENT,
                        "This check intensifies the attack on the exposed king. The defensive task becomes harder.",
                        "The king's weak pawn cover allowed the attack."
                    )
                
                piece_name = PIECE_NAMES[moving_piece.piece_type]
                if move.to_square in _get_king_zone(opponent_king_sq):
                    return MoveExplanation(
                        Priority.KING_SAFETY_URGENT,
                        f"Brings the {piece_name} into the attack on the weakened king.",
                        "The king's position was already compromised."
                    )
        except Exception:
            pass
    
    # DEFENDING: Urgent defense only when there's a real attack
    if our_king_sq and engine:
        try:
            # Check if WE are under attack
            our_king_exposed = _is_king_exposed(board, board.turn)
            attackers_on_us = _count_attackers_in_king_zone(board, our_king_sq, not board.turn)
            
            # Castling is ONLY urgent if we're under real pressure
            if moving_piece.piece_type == chess.KING:
                if abs(chess.square_file(move.from_square) - chess.square_file(move.to_square)) == 2:
                    if our_king_exposed or attackers_on_us >= 2:
                        return MoveExplanation(
                            Priority.KING_SAFETY_URGENT,
                            "Castles to escape the growing attack. The center was becoming too dangerous.",
                            "The king in the center was vulnerable to the building pressure."
                        )
                    # Otherwise, castling is positional - will be caught by lower priority
        except Exception:
            pass
    
    return None


def _is_king_exposed(board: chess.Board, color: chess.Color) -> bool:
    """Check if king's pawn shield is compromised."""
    king_sq = board.king(color)
    if king_sq is None:
        return False
    
    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
    
    # Count pawns in front of king
    pawn_shield = 0
    forward = 1 if color == chess.WHITE else -1
    
    for df in [-1, 0, 1]:
        f = king_file + df
        if 0 <= f <= 7:
            for dr in [forward, forward * 2]:
                r = king_rank + dr
                if 0 <= r <= 7:
                    sq = chess.square(f, r)
                    piece = board.piece_at(sq)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        pawn_shield += 1
                        break
    
    return pawn_shield <= 1  # Exposed if only 0 or 1 pawns in shield


def _count_attackers_in_king_zone(board: chess.Board, king_sq: int, 
                                   attacker_color: chess.Color) -> int:
    """Count attacking pieces in the king zone."""
    if king_sq is None:
        return 0
    
    zone = _get_king_zone(king_sq)
    count = 0
    
    for sq in zone:
        attackers = board.attackers(attacker_color, sq)
        count += len(attackers)
    
    return count


def _get_king_zone(king_sq: int) -> Set[int]:
    """Get squares around the king."""
    zone = set()
    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
    
    for df in range(-2, 3):
        for dr in range(-2, 3):
            f, r = king_file + df, king_rank + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                zone.add(chess.square(f, r))
    return zone


# =============================================================================
# PRIORITY 5: ONLY MOVE (Structural Collapse)
# =============================================================================

def _check_only_move(board: chess.Board, move: chess.Move,
                     engine: Optional[chess.engine.SimpleEngine],
                     ctx: PositionContext) -> Optional[MoveExplanation]:
    """
    Check if this is the only non-collapsing move.
    
    KEY PRINCIPLE: "Only move" means alternatives allow CONCRETE failure:
    - Mate
    - Lost material
    - Forced losing endgame
    - Permanent positional damage
    
    NOT just "eval drops" in a quiet position.
    """
    if not engine:
        return None
    
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=14), multipv=4)
        if not isinstance(infos, list):
            infos = [infos]
        
        if len(infos) < 2:
            return None
        
        # Get best move eval
        best_score = infos[0].get("score")
        if not best_score:
            return None
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000)
        best_mate = best_score.pov(board.turn).mate()
        
        # Check what happens with alternatives
        concrete_failures = []
        
        for alt in infos[1:]:
            alt_score = alt.get("score")
            if not alt_score:
                continue
            
            alt_cp = alt_score.pov(board.turn).score(mate_score=10000)
            alt_mate = alt_score.pov(board.turn).mate()
            
            # Check for concrete failures
            if alt_mate is not None and alt_mate < 0:
                concrete_failures.append("allows mate")
            elif best_cp is not None and alt_cp is not None:
                loss = best_cp - alt_cp
                if loss > 300:  # 3+ pawns = losing piece
                    concrete_failures.append("loses material")
                elif loss > 500:
                    concrete_failures.append("loses significant material")
        
        # Only report "only move" if there's concrete collapse
        if concrete_failures:
            if "allows mate" in concrete_failures:
                return MoveExplanation(
                    Priority.ONLY_MOVE,
                    "This is the only move that doesn't allow a forced loss. Other moves lead to mate.",
                    "The alternatives all had fatal flaws."
                )
            if "loses significant material" in concrete_failures:
                return MoveExplanation(
                    Priority.ONLY_MOVE,
                    "This is the only move that holds. The alternatives lose significant material.",
                    "Every other option had a concrete tactical problem."
                )
            if "loses material" in concrete_failures:
                return MoveExplanation(
                    Priority.ONLY_MOVE,
                    "This is the only move that doesn't lose material. The position required precision.",
                    "The alternatives all had tactical weaknesses."
                )
        
    except Exception:
        pass
    
    return None


# =============================================================================
# PRIORITY 6: INITIATIVE (Concrete Tempo)
# =============================================================================

def _check_initiative(board: chess.Board, move: chess.Move,
                      ctx: PositionContext) -> Optional[MoveExplanation]:
    """Check if move maintains initiative through concrete threats."""
    gives_check = board.gives_check(move)
    
    board_after = board.copy()
    board_after.push(move)
    
    # Count NEW threats created
    new_threats = []
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != board.turn and piece.piece_type != chess.PAWN:
            was_attacked = board.is_attacked_by(board.turn, sq)
            is_attacked = board_after.is_attacked_by(board.turn, sq)
            if is_attacked and not was_attacked:
                new_threats.append(PIECE_NAMES[piece.piece_type])
    
    if gives_check and len(new_threats) >= 1:
        return MoveExplanation(
            Priority.INITIATIVE,
            f"This check also threatens the {new_threats[0]}. The opponent must address both.",
            "The move creates multiple problems to solve."
        )
    
    if len(new_threats) >= 2:
        return MoveExplanation(
            Priority.INITIATIVE,
            f"Creates threats against the {new_threats[0]} and {new_threats[1]}. The opponent can't handle both.",
            "Multiple pieces came under attack at once."
        )
    
    return None


# =============================================================================
# PRIORITY 8: ENDGAME TRANSITION
# =============================================================================

def _check_endgame(board: chess.Board, move: chess.Move,
                   engine: Optional[chess.engine.SimpleEngine],
                   ctx: PositionContext) -> Optional[MoveExplanation]:
    """
    Check for endgame-specific explanations.
    
    KEY PRINCIPLE: Explain WHY the result is decided, not what piece moved.
    """
    if not ctx.is_endgame:
        return None
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    board_after = board.copy()
    board_after.push(move)
    
    # King activation - but explain the consequence
    if moving_piece.piece_type == chess.KING:
        to_file = chess.square_file(move.to_square)
        to_rank = chess.square_rank(move.to_square)
        
        # Check if king is moving toward action (opponent's pawns/pieces)
        if engine:
            try:
                # Is this leading to a winning endgame?
                info = engine.analyse(board_after, chess.engine.Limit(depth=16))
                score = info.get("score")
                if score:
                    cp = score.pov(board.turn).score(mate_score=10000)
                    if cp and cp > 200:
                        return MoveExplanation(
                            Priority.ENDGAME_TRANSITION,
                            "Brings the king into the action. The centralized king will decide the endgame.",
                            "In endgames, the king's activity often determines the outcome."
                        )
            except Exception:
                pass
        
        # Central king
        if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
            return MoveExplanation(
                Priority.ENDGAME_TRANSITION,
                "Centralizes the king. In the endgame, an active king is often worth more than a piece.",
                "The king was too passive."
            )
    
    # Passed pawn advancement
    if moving_piece.piece_type == chess.PAWN:
        to_rank = chess.square_rank(move.to_square)
        to_file = chess.square_file(move.to_square)
        
        # Check if this is a passed pawn
        is_passed = _is_passed_pawn(board, move.from_square)
        
        if is_passed:
            promo_rank = 7 if moving_piece.color == chess.WHITE else 0
            distance = abs(promo_rank - to_rank)
            
            if distance <= 2:
                return MoveExplanation(
                    Priority.ENDGAME_TRANSITION,
                    "Advances the passed pawn. It's too close to promotion to be stopped.",
                    "The passed pawn is unstoppable."
                )
            
            return MoveExplanation(
                Priority.ENDGAME_TRANSITION,
                "Pushes the passed pawn. The opponent must divert resources to stop it.",
                "Passed pawns create winning threats in endgames."
            )
    
    return None


def _is_passed_pawn(board: chess.Board, pawn_sq: int) -> bool:
    """Check if a pawn is passed (no opponent pawns can block or capture it)."""
    piece = board.piece_at(pawn_sq)
    if not piece or piece.piece_type != chess.PAWN:
        return False
    
    pawn_file = chess.square_file(pawn_sq)
    pawn_rank = chess.square_rank(pawn_sq)
    direction = 1 if piece.color == chess.WHITE else -1
    
    # Check files in front (same file and adjacent)
    for df in [-1, 0, 1]:
        f = pawn_file + df
        if f < 0 or f > 7:
            continue
        
        # Check all squares in front
        r = pawn_rank + direction
        while 0 <= r <= 7:
            sq = chess.square(f, r)
            blocker = board.piece_at(sq)
            if blocker and blocker.piece_type == chess.PAWN and blocker.color != piece.color:
                return False
            r += direction
    
    return True


# =============================================================================
# PRIORITY 12: POSITIONAL (Fallback)
# =============================================================================

def _check_positional(board: chess.Board, move: chess.Move,
                      ctx: PositionContext) -> MoveExplanation:
    """Fallback positional explanation."""
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return MoveExplanation(
            Priority.POSITIONAL,
            "Improves the position.",
            None
        )
    
    piece_name = PIECE_NAMES[moving_piece.piece_type]
    
    # Castling (non-urgent)
    if moving_piece.piece_type == chess.KING:
        if abs(chess.square_file(move.from_square) - chess.square_file(move.to_square)) == 2:
            return MoveExplanation(
                Priority.POSITIONAL,
                "Castles. This connects the rooks and places the king on a safer square.",
                "Castling is generally a good idea when no immediate tactics exist."
            )
    
    # Development
    from_rank = chess.square_rank(move.from_square)
    is_back_rank = (moving_piece.color == chess.WHITE and from_rank == 0) or \
                   (moving_piece.color == chess.BLACK and from_rank == 7)
    
    if is_back_rank and moving_piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
        return MoveExplanation(
            Priority.PIECE_ACTIVITY,
            f"Develops the {piece_name}. Getting pieces into play is essential.",
            "The piece was still on its starting square."
        )
    
    # Central control
    to_file = chess.square_file(move.to_square)
    to_rank = chess.square_rank(move.to_square)
    
    if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
        return MoveExplanation(
            Priority.POSITIONAL,
            f"The {piece_name} improves to a central square, increasing its influence.",
            "Central pieces control more squares."
        )
    
    return MoveExplanation(
        Priority.POSITIONAL,
        f"Repositions the {piece_name} to a better square.",
        None
    )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _get_piece_directions(piece_type: chess.PieceType) -> List[Tuple[int, int]]:
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
    f = chess.square_file(sq) + direction[0]
    r = chess.square_rank(sq) + direction[1]
    if 0 <= f <= 7 and 0 <= r <= 7:
        return chess.square(f, r)
    return None


def _direction_between(from_sq: int, to_sq: int) -> Optional[Tuple[int, int]]:
    df = chess.square_file(to_sq) - chess.square_file(from_sq)
    dr = chess.square_rank(to_sq) - chess.square_rank(from_sq)
    
    if df == 0 and dr == 0:
        return None
    
    is_straight = df == 0 or dr == 0
    is_diagonal = abs(df) == abs(dr)
    
    if not is_straight and not is_diagonal:
        return None
    
    if df != 0:
        df = df // abs(df)
    if dr != 0:
        dr = dr // abs(dr)
    
    return (df, dr)


# =============================================================================
# MAIN EXPLANATION GENERATOR (DOMINANCE MODEL)
# =============================================================================

def generate_move_explanation(
    board: chess.Board,
    best_move: chess.Move,
    phase: str = "middlegame",
) -> str:
    """
    Generate explanation using STRICT DOMINANCE MODEL.
    
    CRITICAL INVARIANT: Choose highest applicable priority and STOP.
    Lower-priority factors are IGNORED, even if true.
    """
    engine = _open_engine()
    
    try:
        ctx = _build_context(board, engine)
        
        # PRIORITY 1: Checkmate (dominates everything)
        result = _check_checkmate(board, best_move, engine)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 2: Forced tactics (dominates all below)
        result = _check_forced_tactics(board, best_move, engine, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 3: Preventing critical threat
        result = _check_prevent_threat(board, best_move, engine, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 4: URGENT king safety only
        result = _check_king_safety_urgent(board, best_move, engine, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 5: Only move (structural collapse)
        result = _check_only_move(board, best_move, engine, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 6: Initiative
        result = _check_initiative(board, best_move, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 8: Endgame
        result = _check_endgame(board, best_move, engine, ctx)
        if result:
            return _format_explanation(result)
        
        # PRIORITY 12: Positional (fallback)
        result = _check_positional(board, best_move, ctx)
        return _format_explanation(result)
        
    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass


def _format_explanation(result: MoveExplanation) -> str:
    """Format explanation, optionally including what user missed."""
    # For now, just return the main explanation
    # The user_likely_missed could be shown in a separate UI element
    return result.explanation


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
    Enhanced puzzle explanation using hierarchical dominance model.
    
    This is the main entry point that puzzle_engine.py calls.
    """
    return generate_move_explanation(board, best_move, phase)


def is_move_viable(board: chess.Board, move: chess.Move, 
                   depth: int = 14) -> Tuple[bool, int]:
    """
    Check if a move is viable (CPL < 50 compared to best).
    
    Returns: (is_viable, cpl)
    
    NOTE: Viable moves should show YELLOW in UI, not green "correct".
    """
    engine = _open_engine()
    if not engine:
        return True, 0
    
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=5)
        if not isinstance(infos, list):
            infos = [infos]
        
        if not infos:
            return True, 0
        
        best_info = infos[0]
        best_score = best_info.get("score")
        
        if not best_score:
            return True, 0
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000) or 0
        
        # Find our move in the multipv
        for info in infos:
            pv = info.get("pv", [])
            if pv and pv[0] == move:
                score = info.get("score")
                if score:
                    move_cp = score.pov(board.turn).score(mate_score=10000) or 0
                    cpl = best_cp - move_cp
                    return cpl <= VIABLE_CPL_THRESHOLD, max(0, cpl)
        
        # Move not in top 5 - analyze specifically
        board_after = board.copy()
        board_after.push(move)
        info = engine.analyse(board_after, chess.engine.Limit(depth=depth))
        score = info.get("score")
        if score:
            move_cp = -score.pov(board_after.turn).score(mate_score=10000) or 0
            cpl = best_cp - move_cp
            return cpl <= VIABLE_CPL_THRESHOLD, max(0, cpl)
        
        return False, 100
        
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def get_user_likely_missed(board: chess.Board, best_move: chess.Move) -> Optional[str]:
    """
    Get what the human likely overlooked.
    
    This can be shown separately in the UI to make explanations corrective.
    """
    engine = _open_engine()
    if not engine:
        return None
    
    try:
        ctx = _build_context(board, engine)
        
        # Go through priority checks and get the user_likely_missed field
        result = _check_checkmate(board, best_move, engine)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_forced_tactics(board, best_move, engine, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_prevent_threat(board, best_move, engine, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_king_safety_urgent(board, best_move, engine, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_only_move(board, best_move, engine, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_initiative(board, best_move, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        result = _check_endgame(board, best_move, engine, ctx)
        if result and result.user_likely_missed:
            return result.user_likely_missed
        
        return None
        
    finally:
        try:
            engine.quit()
        except Exception:
            pass
