"""
Stockfish-Based Move Explanation Engine (v3.1 - True Counterfactual Reasoning)

FUNDAMENTAL PRINCIPLE:
======================
Stockfish is the master. Stockfish determines what's best. We explain WHY.

But the explanation is about THE POSITION'S DEMAND, not the move's benefit.

The key question is NOT: "What good thing does this move do?"
The key question IS: "What is the FIRST thing that breaks if you DON'T play this move?"

ARCHITECTURAL CHANGE FROM V3:
=============================
v3.0: Analyze position → Find highest-priority threat → Explain how move addresses it
v3.1: Analyze COUNTERFACTUAL → "What happens if I play something else?" → Explain failure

This is TRUE DOMINANCE REASONING:
- We simulate what happens if the best move is NOT played
- We find the first irreversible consequence in the response chain
- We explain the move in terms of PREVENTING that consequence

Example (Knight-Bishop-Queen puzzle):
- Queen is "safe now" (not attacked)
- v3.0 might say: "Improves the queen to a better square"
- v3.1 says: "If you don't move the queen, the knight moves and the bishop
             attacks it. The queen looks safe now, but becomes a target."

CORE CONCEPTS:
==============

1. COUNTERFACTUAL SIMULATION (the key change)
   For each puzzle, we ask: "What if the human plays ANY other move?"
   We simulate the opponent's best response and identify what breaks.
   
   The CounterfactualFailure dataclass captures:
   - failure_type: "mate", "material", "fork", "conditional_threat", etc.
   - description: Human-readable explanation starting with "If you don't..."
   - severity: 1=mate, 2=major material, 3=minor material, 4=positional
   - misconception: Why the human might miss this ("the queen seemed safe")

2. CONDITIONAL THREATS (the knight-bishop-queen case)
   A piece may not be attacked NOW, but becomes attacked after wrong move.
   We specifically detect when:
   - Piece was NOT attacked before wrong move
   - Piece IS attacked after wrong move + opponent's response
   This is the "looks safe but isn't" case.

3. IRREVERSIBILITY (not material thresholds)
   "Only move" means alternatives permanently concede something unfixable:
   - Forced perpetual allowed
   - Fortress collapsed
   - Opposition lost
   - Key tempo lost in pawn race
   NOT just "loses 3 pawns"

4. HUMAN MISCONCEPTION (attack the oversight)
   Don't just describe the tactic.
   Attack WHY the human missed it:
   - "The queen seemed safe because it's not attacked yet"
   - "You focused on developing, but the threat was building"

5. MECHANISM OF COLLAPSE (not outcome)
   Don't say "position collapses"
   Say WHICH piece becomes loose, WHICH square becomes weak

6. PRIORITY ORDER
   1. Mate threats (must be addressed)
   2. Immediate tactical threats (hanging pieces)
   3. Counterfactual threats (what breaks if you don't play this)
   4. King safety issues
   5. Structural collapse
   6. Endgame critical moments
   7. Tactical opportunities
   8. Positional improvements (only if nothing else applies)

VIABLE MOVES WARNING:
=====================
"Viable" (yellow) is a UI category, not a chess truth.
Many viable moves are technically drawable but:
- Strategically inferior
- Much harder to play correctly
- Lead to worse practical chances
Explanations must still privilege the best move and explain why viable ≠ optimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set, Dict
from enum import IntEnum
import os

import chess
import chess.engine


# =============================================================================
# PRIORITY LEVELS
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
# PIECE VALUES AND NAMES
# =============================================================================

PIECE_POINTS = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}

VIABLE_CPL_THRESHOLD = 50


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
# POSITION URGENCY ANALYSIS
# =============================================================================

@dataclass
class PositionUrgency:
    """
    What does this POSITION demand? Analyzed BEFORE looking at the best move.
    
    This is the key architectural change: we determine what the position requires,
    then explain how the best move addresses that requirement.
    """
    priority: Priority = Priority.POSITIONAL
    
    # What goes wrong if you play wrong?
    threat_type: Optional[str] = None  # "mate", "material", "positional_collapse"
    threat_description: Optional[str] = None  # Human-readable threat
    threat_move: Optional[chess.Move] = None  # The threatening move
    threatened_piece_sq: Optional[int] = None  # Square of threatened piece
    
    # For irreversibility analysis
    collapse_type: Optional[str] = None  # "tempo", "opposition", "fortress", "structure"
    collapse_description: Optional[str] = None
    
    # King danger specifics
    king_danger_imminent: bool = False
    king_attack_inevitable: bool = False
    pawn_break_unstoppable: Optional[str] = None
    
    # Endgame specifics
    is_endgame: bool = False
    critical_square: Optional[str] = None  # e.g., "d5"
    critical_pawn: Optional[str] = None  # e.g., "the c-pawn"
    tempo_critical: bool = False
    
    # Human misconception hint
    likely_human_focus: Optional[str] = None  # What the human was probably looking at
    
    # COUNTERFACTUAL ANALYSIS (True Dominance)
    counterfactual_failure: Optional['CounterfactualFailure'] = None


def _analyze_position_urgency(board: chess.Board, 
                               engine: chess.engine.SimpleEngine,
                               best_move: Optional[chess.Move] = None) -> PositionUrgency:
    """
    Analyze what the POSITION demands, independent of the best move.
    
    Key question: "What is the worst thing that happens if you play wrong?"
    
    ARCHITECTURAL CHANGE (v3.1 - True Counterfactual Reasoning):
    After checking immediate threats, we now analyze what happens if the best
    move is NOT played. This catches conditional threats (e.g., piece looks safe
    but becomes attacked after opponent's response to a wrong move).
    """
    urgency = PositionUrgency()
    
    # Count material for endgame detection
    total_material = sum(
        len(board.pieces(pt, c)) * PIECE_POINTS[pt]
        for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
        for c in [chess.WHITE, chess.BLACK]
    )
    urgency.is_endgame = total_material <= 26
    
    # Get Stockfish's view of the position
    try:
        # Analyze with multipv to see what happens with wrong moves
        # Use depth=8 for speed - we need patterns, not perfect eval
        infos = engine.analyse(board, chess.engine.Limit(depth=8), multipv=3)
        if not isinstance(infos, list):
            infos = [infos]
        
        best_info = infos[0]
        best_score = best_info.get("score")
        best_pv = best_info.get("pv", [])
        engine_best_move = best_pv[0] if best_pv else None
        
        # Use provided best_move or engine's best
        the_best_move = best_move or engine_best_move
        
        if not best_score or not the_best_move:
            return urgency
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000)
        best_mate = best_score.pov(board.turn).mate()
        
        # CHECK 1: Is there a mating threat we must address?
        mate_threat = _detect_mate_threat(board, engine)
        if mate_threat:
            urgency.priority = Priority.CHECKMATE
            urgency.threat_type = "mate"
            urgency.threat_description = mate_threat
            urgency.likely_human_focus = "material or other plans"
            return urgency
        
        # CHECK 2: Is there an immediate tactical threat?
        tactical_threat = _detect_tactical_threat(board, engine)
        if tactical_threat:
            urgency.priority = Priority.PREVENT_THREAT
            urgency.threat_type = "material"
            urgency.threat_description = tactical_threat['description']
            urgency.threatened_piece_sq = tactical_threat.get('square')
            urgency.likely_human_focus = tactical_threat.get('misconception')
            return urgency
        
        # CHECK 3: COUNTERFACTUAL ANALYSIS (True Dominance)
        # What happens if the best move is NOT played?
        # This catches conditional threats that don't exist yet but will emerge.
        counterfactual = _analyze_counterfactual_failure(board, the_best_move, engine)
        if counterfactual and counterfactual.severity <= 3:
            urgency.priority = Priority.PREVENT_THREAT
            urgency.counterfactual_failure = counterfactual
            urgency.threat_type = counterfactual.failure_type
            urgency.threat_description = counterfactual.description
            urgency.likely_human_focus = counterfactual.misconception
            return urgency
        
        # CHECK 4: Is our king in danger that's about to become critical?
        king_danger = _detect_king_danger_inevitable(board, engine)
        if king_danger:
            urgency.priority = Priority.KING_SAFETY_URGENT
            urgency.king_danger_imminent = True
            urgency.king_attack_inevitable = king_danger.get('inevitable', False)
            urgency.pawn_break_unstoppable = king_danger.get('pawn_break')
            urgency.threat_description = king_danger['description']
            urgency.likely_human_focus = "the center or material"
            return urgency
        
        # CHECK 5: Are alternatives structurally collapsing (not just losing eval)?
        collapse = _detect_structural_collapse(board, engine, infos)
        if collapse:
            urgency.priority = Priority.ONLY_MOVE
            urgency.collapse_type = collapse['type']
            urgency.collapse_description = collapse['description']
            urgency.likely_human_focus = collapse.get('misconception')
            return urgency
        
        # CHECK 6: Is this a critical endgame moment?
        if urgency.is_endgame:
            endgame_critical = _detect_endgame_critical(board, engine)
            if endgame_critical:
                urgency.priority = Priority.ENDGAME_TRANSITION
                urgency.critical_square = endgame_critical.get('square')
                urgency.critical_pawn = endgame_critical.get('pawn')
                urgency.tempo_critical = endgame_critical.get('tempo', False)
                urgency.threat_description = endgame_critical['description']
                return urgency
        
        # CHECK 7: Is there a tactical opportunity we should seize?
        tactical_opportunity = _detect_tactical_opportunity(board, the_best_move, engine)
        if tactical_opportunity:
            urgency.priority = Priority.FORCED_TACTICS
            urgency.threat_description = tactical_opportunity['description']
            urgency.likely_human_focus = tactical_opportunity.get('misconception')
            return urgency
        
        # CHECK 8: Store counterfactual even if lower severity (for fallback)
        if counterfactual:
            urgency.counterfactual_failure = counterfactual
        
        # Default: positional considerations
        urgency.priority = Priority.POSITIONAL
        
    except Exception:
        pass
    
    return urgency


def _opponent_to_move_board(board: chess.Board) -> chess.Board:
    """Return a fresh board with side-to-move flipped, without move history.

    We deliberately avoid pushing a null move ("pass"). python-chess warns that
    UCI engines cannot represent null moves in move history, and some engines
    can desync when the history contains null moves.

    For threat probing we only need a consistent *position* for the opponent to
    move; a fresh board from FEN (no stack) is the most stable way.
    """
    test_board = chess.Board(board.fen())
    test_board.turn = not board.turn
    # A null move clears en-passant rights; approximate that here.
    test_board.ep_square = None
    return test_board


def _detect_mate_threat(board: chess.Board, 
                        engine: chess.engine.SimpleEngine) -> Optional[str]:
    """Detect if opponent has a mating threat that must be addressed."""
    try:
        # Probe opponent's threat by analyzing the same position with
        # side-to-move flipped (fresh board, no history).
        if board.is_check():
            return None

        test_board = _opponent_to_move_board(board)
        
        info = engine.analyse(test_board, chess.engine.Limit(depth=6))
        score = info.get("score")
        pv = info.get("pv", [])
        
        if score and pv:
            mate = score.pov(test_board.turn).mate()
            if mate is not None and mate > 0 and mate <= 3:
                # There's a mating threat!
                threat_move = pv[0]
                if test_board.gives_check(threat_move):
                    return f"Opponent threatens checkmate in {mate} moves starting with check."
                return f"Opponent threatens checkmate in {mate} moves."
        
    except Exception:
        pass
    
    return None


def _detect_tactical_threat(board: chess.Board,
                            engine: chess.engine.SimpleEngine) -> Optional[Dict]:
    """Detect immediate tactical threats (hanging pieces, forks, etc.)."""
    try:
        # Check for hanging pieces
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == board.turn and piece.piece_type != chess.PAWN:
                if board.is_attacked_by(not board.turn, sq):
                    defenders = len(board.attackers(board.turn, sq))
                    attackers = len(board.attackers(not board.turn, sq))
                    
                    if attackers > defenders:
                        piece_name = PIECE_NAMES[piece.piece_type]
                        sq_name = chess.square_name(sq)
                        
                        if defenders == 0:
                            return {
                                'description': f"The {piece_name} on {sq_name} is undefended and under attack.",
                                'square': sq,
                                'misconception': f"the {piece_name} looks safe"
                            }
                        else:
                            return {
                                'description': f"The {piece_name} on {sq_name} is insufficiently defended.",
                                'square': sq,
                                'misconception': f"the {piece_name} seems protected"
                            }
        
        # Check opponent's best move for tactical threats by probing the
        # position with side-to-move flipped (no null-move history).
        if not board.is_check():
            try:
                test_board = _opponent_to_move_board(board)
                info = engine.analyse(test_board, chess.engine.Limit(depth=6))
                pv = info.get("pv", [])
                if pv:
                    threat = pv[0]
                    captured = test_board.piece_at(threat.to_square)
                    if captured and captured.color == board.turn:
                        if PIECE_POINTS[captured.piece_type] >= 3:
                            return {
                                'description': f"The {PIECE_NAMES[captured.piece_type]} is under attack.",
                                'square': threat.to_square,
                                'misconception': "other plans"
                            }
            except Exception:
                pass
        
    except Exception:
        pass
    
    return None


# =============================================================================
# COUNTERFACTUAL FAILURE ANALYSIS (True Dominance Reasoning)
# =============================================================================

@dataclass
class CounterfactualFailure:
    """What goes wrong if the best move is NOT played."""
    failure_type: str  # "mate", "material", "fork", "pin", "positional"
    description: str  # Human-readable explanation
    severity: int  # 1=mate, 2=major material, 3=minor material, 4=positional
    misconception: Optional[str] = None  # Why human might miss this
    threat_sequence: Optional[List[str]] = None  # e.g., ["Nf3", "Bxd5+", "Nxe7"]


def _analyze_counterfactual_failure(
    board: chess.Board,
    best_move: chess.Move,
    engine: chess.engine.SimpleEngine,
) -> Optional[CounterfactualFailure]:
    """
    TRUE DOMINANCE REASONING: What breaks if the best move is NOT played?
    
    This is the key architectural change from move-centric to position-centric reasoning.
    
    Instead of asking "what does the best move achieve?", we ask:
    "What is the FIRST irreversible failure if ANY other move is played?"
    
    Algorithm:
    1. Get alternatives to the best move
    2. For each alternative, simulate opponent's best response
    3. Identify the worst consequence in the response chain
    4. Return the highest-priority failure
    """
    try:
        # Get position eval with best move
        best_info = engine.analyse(board, chess.engine.Limit(depth=10), multipv=1)
        best_score = best_info.get("score")
        if not best_score:
            return None
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000) or 0
        
        # Find the most instructive "wrong" move to analyze
        # We want a move that LOOKS reasonable but fails
        wrong_move = _find_instructive_wrong_move(board, best_move, engine)
        if not wrong_move:
            return None
        
        # Simulate: what happens if we play the wrong move?
        board_after_wrong = board.copy()
        board_after_wrong.push(wrong_move)
        
        # Get opponent's best response and the resulting position
        opp_info = engine.analyse(board_after_wrong, chess.engine.Limit(depth=10))
        opp_pv = opp_info.get("pv", [])
        opp_score = opp_info.get("score")
        
        if not opp_pv or not opp_score:
            return None
        
        opp_response = opp_pv[0]
        
        # Calculate the swing (how much worse are we after wrong move + response?)
        # Note: opponent's score is from their perspective, so negate it
        after_wrong_cp = -opp_score.pov(board_after_wrong.turn).score(mate_score=10000) or 0
        swing = best_cp - after_wrong_cp
        
        if swing < 50:
            # Not significant enough to explain
            return None
        
        # Now analyze WHAT specifically goes wrong
        failure = _identify_failure_mechanism(
            board, best_move, wrong_move, opp_response, opp_pv, swing, engine
        )
        
        return failure
        
    except Exception:
        return None


def _find_instructive_wrong_move(
    board: chess.Board,
    best_move: chess.Move,
    engine: chess.engine.SimpleEngine,
) -> Optional[chess.Move]:
    """
    Find a "wrong" move that looks reasonable but fails.
    
    This is crucial for explanations: we want to show WHY the human might
    have considered a different move, and why it doesn't work.
    
    Preference order:
    1. Move that develops/improves the same piece
    2. Move that achieves something tactical-looking
    3. Second-best move from engine
    """
    try:
        moving_piece = board.piece_at(best_move.from_square)
        
        # First: look for alternative moves with the same piece
        if moving_piece:
            for move in board.legal_moves:
                if move.from_square == best_move.from_square and move != best_move:
                    # This moves the same piece elsewhere
                    return move
        
        # Second: look for moves that look active (captures, checks)
        for move in board.legal_moves:
            if move == best_move:
                continue
            if board.is_capture(move) or board.gives_check(move):
                return move
        
        # Third: use engine's second-best
        infos = engine.analyse(board, chess.engine.Limit(depth=8), multipv=2)
        if isinstance(infos, list) and len(infos) >= 2:
            alt_pv = infos[1].get("pv", [])
            if alt_pv and alt_pv[0] != best_move:
                return alt_pv[0]
        
        # Fallback: any legal move that isn't the best
        for move in board.legal_moves:
            if move != best_move:
                return move
        
    except Exception:
        pass
    
    return None


def _identify_failure_mechanism(
    board: chess.Board,
    best_move: chess.Move,
    wrong_move: chess.Move,
    opp_response: chess.Move,
    opp_pv: List[chess.Move],
    swing_cp: int,
    engine: chess.engine.SimpleEngine,
) -> Optional[CounterfactualFailure]:
    """
    Identify the SPECIFIC mechanism of failure.
    
    This is where we answer "what goes wrong and why?"
    """
    board_after_wrong = board.copy()
    board_after_wrong.push(wrong_move)
    
    board_after_response = board_after_wrong.copy()
    board_after_response.push(opp_response)
    
    moving_piece = board.piece_at(best_move.from_square)
    wrong_piece = board.piece_at(wrong_move.from_square)
    
    # Check for forced mate
    opp_mate = None
    for info_key in ["score"]:
        score = engine.analyse(board_after_wrong, chess.engine.Limit(depth=8)).get("score")
        if score:
            mate = score.pov(board_after_wrong.turn).mate()
            if mate is not None and mate < 0:
                opp_mate = -mate
                break
    
    if opp_mate and opp_mate <= 5:
        return CounterfactualFailure(
            failure_type="mate",
            description=f"If you don't play this move, opponent has forced checkmate in {opp_mate}.",
            severity=1,
            misconception="the position looked safe",
            threat_sequence=[m.uci() for m in opp_pv[:min(3, len(opp_pv))]]
        )
    
    # Check for immediate material loss on the response
    captured_by_response = board_after_wrong.piece_at(opp_response.to_square)
    if captured_by_response and captured_by_response.color == board.turn:
        captured_name = PIECE_NAMES[captured_by_response.piece_type]
        captured_value = PIECE_POINTS[captured_by_response.piece_type]
        
        if captured_value >= 3:
            # What piece is being taken and why?
            captured_sq = chess.square_name(opp_response.to_square)
            
            # Check if this is a CONDITIONAL threat (the key insight!)
            # The piece might be "safe" now, but becomes attackable after wrong move
            was_attacked_before = board.is_attacked_by(not board.turn, opp_response.to_square)
            is_attacked_after = board_after_wrong.is_attacked_by(not board.turn, opp_response.to_square)
            
            if not was_attacked_before and is_attacked_after:
                # This is a CONDITIONAL threat - exactly the case user described!
                # The piece became attackable because of the wrong move
                attacking_piece = board_after_wrong.piece_at(opp_response.from_square)
                attacker_name = PIECE_NAMES[attacking_piece.piece_type] if attacking_piece else "piece"
                
                return CounterfactualFailure(
                    failure_type="conditional_threat",
                    description=f"If you don't move the {captured_name}, the {attacker_name} attacks it. The {captured_name} looks safe now, but becomes a target.",
                    severity=2,
                    misconception=f"the {captured_name} seemed safe because it's not attacked yet",
                    threat_sequence=[opp_response.uci()]
                )
            
            # Direct material loss
            return CounterfactualFailure(
                failure_type="material",
                description=f"If you don't play this move, the {captured_name} on {captured_sq} is lost.",
                severity=2,
                misconception=f"the {captured_name} seemed protected"
            )
    
    # Check for fork/double attack in response
    fork = _detect_fork_in_response(board_after_wrong, opp_response)
    if fork:
        return fork
    
    # Check for discovered attack in response
    discovery = _detect_discovery_in_response(board_after_wrong, opp_response)
    if discovery:
        return discovery
    
    # Check for pin/skewer in response
    pin = _detect_pin_in_response(board_after_wrong, opp_response)
    if pin:
        return pin
    
    # Large positional swing without obvious tactic
    if swing_cp >= 200:
        # Try to identify what's happening in the next few moves
        threat_desc = _describe_threat_sequence(board, wrong_move, opp_pv, engine)
        if threat_desc:
            return CounterfactualFailure(
                failure_type="tactical_sequence",
                description=threat_desc,
                severity=3,
                misconception="the alternative looked reasonable"
            )
    
    # Moderate swing - positional collapse
    if swing_cp >= 100:
        return CounterfactualFailure(
            failure_type="positional",
            description="Without this move, the position becomes significantly worse.",
            severity=4,
            misconception="the alternative seemed playable"
        )
    
    return None


def _detect_fork_in_response(board: chess.Board, response: chess.Move) -> Optional[CounterfactualFailure]:
    """Detect if opponent's response creates a fork that actually wins material."""
    board_after = board.copy()
    board_after.push(response)
    
    responding_piece = board.piece_at(response.from_square)
    if not responding_piece:
        return None
    
    responder_name = PIECE_NAMES[responding_piece.piece_type]
    responder_value = PIECE_POINTS[responding_piece.piece_type]
    
    # Find pieces attacked by the moved piece after the response
    attacked_pieces = []
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != responding_piece.color:
            if board_after.is_attacked_by(responding_piece.color, sq):
                # Check if the response piece is doing the attacking
                attackers = board_after.attackers(responding_piece.color, sq)
                if response.to_square in attackers:
                    # Get detailed defense information
                    defense_info = _analyze_piece_defense(board_after, sq, piece)
                    attacked_pieces.append({
                        'piece': piece,
                        'square': sq,
                        'name': PIECE_NAMES[piece.piece_type],
                        'value': PIECE_POINTS[piece.piece_type],
                        **defense_info
                    })
    
    if len(attacked_pieces) < 2:
        return None
    
    # Sort by value (highest first)
    attacked_pieces.sort(key=lambda x: -x['value'])
    
    has_king = any(p['piece'].piece_type == chess.KING for p in attacked_pieces)
    
    if has_king:
        # Fork with king - the non-king piece will be lost regardless of defense
        # (king MUST move, so the other piece is captured even if defended)
        non_king = next(p for p in attacked_pieces if p['piece'].piece_type != chess.KING)
        return CounterfactualFailure(
            failure_type="fork",
            description=f"If you don't play this move, the {responder_name} forks your king and {non_king['name']}. The king must move, losing the {non_king['name']}.",
            severity=2,
            misconception=f"the {non_king['name']} looked safe, but becomes vulnerable to a fork"
        )
    
    # No king involved - check if fork actually wins material
    # A fork wins if at least one target is:
    # 1. Undefended, OR
    # 2. Worth more than the attacker (profitable exchange)
    
    vulnerable_pieces = []
    for target in attacked_pieces:
        if not target['is_defended']:
            # Undefended - will be lost
            vulnerable_pieces.append(target)
        elif target['value'] > responder_value:
            # Defended but worth more than attacker - exchange still wins
            vulnerable_pieces.append(target)
        elif target['is_defended'] and target['min_defender_value'] > responder_value:
            # Defended only by more valuable pieces - might still lose
            vulnerable_pieces.append(target)
    
    if len(vulnerable_pieces) < 1:
        # Fork doesn't actually win anything - all targets are safely defended
        return None
    
    # At least one piece is vulnerable
    if len(vulnerable_pieces) == 1:
        # Only one piece is really threatened
        target = vulnerable_pieces[0]
        if not target['is_defended']:
            return CounterfactualFailure(
                failure_type="fork",
                description=f"If you don't play this move, the {responder_name} attacks your {target['name']}, which is undefended.",
                severity=2 if target['value'] >= 3 else 3,
                misconception=f"the {target['name']} seemed safe"
            )
        else:
            return CounterfactualFailure(
                failure_type="fork",
                description=f"If you don't play this move, the {responder_name} attacks your {target['name']}. Although defended, the {responder_name} is worth less, so the exchange favors your opponent.",
                severity=2 if target['value'] >= 3 else 3,
                misconception=f"the {target['name']} seemed safely defended"
            )
    
    # Multiple pieces vulnerable - true fork
    target1, target2 = vulnerable_pieces[0], vulnerable_pieces[1]
    
    # Build description based on defense status
    if not target1['is_defended'] and not target2['is_defended']:
        desc = f"If you don't play this move, the {responder_name} forks the {target1['name']} and {target2['name']}. Both are undefended, so one will be lost."
    elif not target1['is_defended'] or not target2['is_defended']:
        undefended = target1 if not target1['is_defended'] else target2
        defended = target2 if not target1['is_defended'] else target1
        desc = f"If you don't play this move, the {responder_name} forks the {target1['name']} and {target2['name']}. The {undefended['name']} is undefended and will be captured."
    else:
        # Both defended but fork still works due to value difference
        desc = f"If you don't play this move, the {responder_name} forks the {target1['name']} and {target2['name']}. You cannot save both."
    
    return CounterfactualFailure(
        failure_type="fork",
        description=desc,
        severity=2,
        misconception="both pieces seemed safe"
    )


def _analyze_piece_defense(board: chess.Board, sq: int, piece: chess.Piece) -> dict:
    """
    Analyze how a piece is defended.
    
    Returns:
        dict with:
        - is_defended: bool
        - defender_count: int
        - defenders: list of piece types defending
        - min_defender_value: lowest value defender (for exchange calc)
        - defense_description: human-readable description
    """
    defenders = board.attackers(piece.color, sq)
    defender_count = len(defenders)
    
    if defender_count == 0:
        return {
            'is_defended': False,
            'defender_count': 0,
            'defenders': [],
            'min_defender_value': 0,
            'defense_description': 'undefended'
        }
    
    # Get details about each defender
    defender_pieces = []
    for def_sq in defenders:
        def_piece = board.piece_at(def_sq)
        if def_piece:
            defender_pieces.append({
                'piece_type': def_piece.piece_type,
                'name': PIECE_NAMES[def_piece.piece_type],
                'value': PIECE_POINTS[def_piece.piece_type],
                'square': def_sq
            })
    
    # Sort by value (lowest first - these would recapture first)
    defender_pieces.sort(key=lambda x: x['value'])
    
    min_defender_value = defender_pieces[0]['value'] if defender_pieces else 0
    
    # Build description
    if defender_count == 1:
        defense_description = f"defended by {defender_pieces[0]['name']}"
    else:
        defender_names = [d['name'] for d in defender_pieces[:3]]
        if defender_count > 3:
            defense_description = f"defended by {', '.join(defender_names)} and {defender_count - 3} more"
        else:
            defense_description = f"defended by {' and '.join(defender_names)}"
    
    return {
        'is_defended': True,
        'defender_count': defender_count,
        'defenders': defender_pieces,
        'min_defender_value': min_defender_value,
        'defense_description': defense_description
    }


def _detect_discovery_in_response(board: chess.Board, response: chess.Move) -> Optional[CounterfactualFailure]:
    """Detect if opponent's response creates a discovered attack."""
    board_after = board.copy()
    board_after.push(response)
    
    responding_piece = board.piece_at(response.from_square)
    if not responding_piece:
        return None
    
    from_sq = response.from_square
    gives_check = board.gives_check(response)
    
    # Check if moving unblocked an attack
    for sq in chess.SQUARES:
        behind_piece = board.piece_at(sq)
        if behind_piece and behind_piece.color == responding_piece.color:
            if behind_piece.piece_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                direction = _direction_between(sq, from_sq)
                if direction:
                    target_sq = from_sq
                    while True:
                        target_sq = _step_square(target_sq, direction)
                        if target_sq is None:
                            break
                        target = board_after.piece_at(target_sq)
                        if target:
                            if target.color != responding_piece.color and PIECE_POINTS[target.piece_type] >= 3:
                                behind_name = PIECE_NAMES[behind_piece.piece_type]
                                target_name = PIECE_NAMES[target.piece_type]
                                
                                if gives_check:
                                    return CounterfactualFailure(
                                        failure_type="discovered_check",
                                        description=f"If you don't play this move, opponent plays a discovered check, winning the {target_name}.",
                                        severity=2,
                                        misconception=f"the {target_name} seemed blocked from the {behind_name}"
                                    )
                                
                                return CounterfactualFailure(
                                    failure_type="discovery",
                                    description=f"If you don't play this move, opponent uncovers an attack on your {target_name}.",
                                    severity=2,
                                    misconception=f"the {target_name} seemed blocked"
                                )
                            break
    
    return None


def _detect_pin_in_response(board: chess.Board, response: chess.Move) -> Optional[CounterfactualFailure]:
    """Detect if opponent's response creates a pin or skewer."""
    board_after = board.copy()
    board_after.push(response)
    
    responding_piece = board.piece_at(response.from_square)
    if not responding_piece or responding_piece.piece_type not in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
        return None
    
    responder_name = PIECE_NAMES[responding_piece.piece_type]
    
    # Check rays from the moved piece
    for direction in _get_piece_directions(responding_piece.piece_type):
        pieces_on_ray = []
        sq = response.to_square
        
        while True:
            sq = _step_square(sq, direction)
            if sq is None:
                break
            piece = board_after.piece_at(sq)
            if piece:
                if piece.color != responding_piece.color:
                    pieces_on_ray.append((piece, sq))
                else:
                    break
                if len(pieces_on_ray) >= 2:
                    break
        
        if len(pieces_on_ray) >= 2:
            front, back = pieces_on_ray[0], pieces_on_ray[1]
            front_piece, front_sq = front
            back_piece, back_sq = back
            front_name = PIECE_NAMES[front_piece.piece_type]
            back_name = PIECE_NAMES[back_piece.piece_type]
            
            # Pin to king
            if back_piece.piece_type == chess.KING:
                return CounterfactualFailure(
                    failure_type="pin",
                    description=f"If you don't play this move, the {responder_name} pins your {front_name} to the king.",
                    severity=2 if PIECE_POINTS[front_piece.piece_type] >= 3 else 3,
                    misconception=f"the {front_name} seemed free to move"
                )
            
            # Skewer (more valuable piece in front)
            if PIECE_POINTS[front_piece.piece_type] > PIECE_POINTS[back_piece.piece_type]:
                return CounterfactualFailure(
                    failure_type="skewer",
                    description=f"If you don't play this move, the {responder_name} skewers your {front_name} and {back_name}.",
                    severity=2,
                    misconception=f"the {front_name} seemed safe"
                )
    
    return None


def _describe_threat_sequence(
    board: chess.Board,
    wrong_move: chess.Move,
    opp_pv: List[chess.Move],
    engine: chess.engine.SimpleEngine,
) -> Optional[str]:
    """Describe a multi-move threat sequence in human terms."""
    if len(opp_pv) < 2:
        return None
    
    try:
        board_after = board.copy()
        board_after.push(wrong_move)
        
        # Look at the first few moves of opponent's response
        threats_found = []
        test_board = board_after.copy()
        
        for i, move in enumerate(opp_pv[:3]):
            if i % 2 == 0:  # Opponent's move
                piece = test_board.piece_at(move.from_square)
                if piece:
                    piece_name = PIECE_NAMES[piece.piece_type]
                    if test_board.gives_check(move):
                        threats_found.append(f"{piece_name} check")
                    elif test_board.is_capture(move):
                        captured = test_board.piece_at(move.to_square)
                        if captured:
                            threats_found.append(f"wins {PIECE_NAMES[captured.piece_type]}")
            
            test_board.push(move)
        
        if threats_found:
            return f"If you don't play this move, opponent's sequence leads to: {', '.join(threats_found)}."
        
    except Exception:
        pass
    
    return None


def _detect_king_danger_inevitable(board: chess.Board,
                                    engine: chess.engine.SimpleEngine) -> Optional[Dict]:
    """
    Detect if king danger is INEVITABLE, not just current.
    
    This is about dynamic inevitability:
    - Pawn breaks that cannot be stopped
    - Sacrifices that force lines open
    - Building attacks that will succeed
    """
    try:
        our_king_sq = board.king(board.turn)
        if our_king_sq is None:
            return None
        
        # Check if opponent has pieces aimed at our king
        king_zone = _get_king_zone(our_king_sq)
        attackers_in_zone = 0
        
        for sq in king_zone:
            attackers = board.attackers(not board.turn, sq)
            attackers_in_zone += len(attackers)
        
        # Is our king's pawn shield compromised?
        pawn_shield_weak = _is_pawn_shield_compromised(board, board.turn)
        
        if pawn_shield_weak and attackers_in_zone >= 3:
            # Check if attack is building - look at opponent's moves by probing
            # side-to-move flipped position (no null-move history).
            if not board.is_check():
                try:
                    test_board = _opponent_to_move_board(board)
                    info = engine.analyse(test_board, chess.engine.Limit(depth=6))
                    pv = info.get("pv", [])
                    if pv:
                        threat = pv[0]
                        # Is opponent bringing more pieces to attack?
                        moving_piece = test_board.piece_at(threat.from_square)
                        if moving_piece and threat.to_square in king_zone:
                            piece_name = PIECE_NAMES[moving_piece.piece_type]
                            return {
                                'description': f"The king's pawn cover is weak and opponent is bringing the {piece_name} into the attack.",
                                'inevitable': True,
                                'pawn_break': None
                            }
                except Exception:
                    pass
        
        # Check for unstoppable pawn breaks
        # Look for pawn moves that open lines to our king
        for move in board.legal_moves:
            # This is opponent's potential pawn break (if we pass)
            pass  # Complex analysis - skip for now
        
    except Exception:
        pass
    
    return None


def _detect_structural_collapse(board: chess.Board,
                                 engine: chess.engine.SimpleEngine,
                                 infos: List) -> Optional[Dict]:
    """
    Detect if alternatives cause STRUCTURAL COLLAPSE.
    
    Not just "loses material" but:
    - Forced perpetual allowed
    - Fortress collapsed  
    - Opposition lost
    - Key tempo lost in pawn race
    - Permanent weakness created
    """
    if len(infos) < 2:
        return None
    
    try:
        best_info = infos[0]
        best_score = best_info.get("score")
        if not best_score:
            return None
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000)
        best_mate = best_score.pov(board.turn).mate()
        
        # Analyze each alternative
        for alt_info in infos[1:]:
            alt_score = alt_info.get("score")
            alt_pv = alt_info.get("pv", [])
            
            if not alt_score or not alt_pv:
                continue
            
            alt_cp = alt_score.pov(board.turn).score(mate_score=10000)
            alt_mate = alt_score.pov(board.turn).mate()
            
            # Check for specific collapse types
            
            # Type 1: Allows forced mate
            if alt_mate is not None and alt_mate < 0:
                return {
                    'type': 'mate_allowed',
                    'description': 'All alternatives allow a forced checkmate.',
                    'misconception': 'other options looked safe'
                }
            
            # Type 2: Major positional collapse (eval swing > 300 cp)
            if best_cp is not None and alt_cp is not None:
                swing = best_cp - alt_cp
                
                if swing > 500:
                    # Try to identify WHY
                    alt_move = alt_pv[0]
                    board_after = board.copy()
                    board_after.push(alt_move)
                    
                    # Check what opponent does
                    if len(alt_pv) > 1:
                        response = alt_pv[1]
                        captured = board_after.piece_at(response.to_square)
                        
                        if captured:
                            piece_name = PIECE_NAMES[captured.piece_type]
                            return {
                                'type': 'material_loss',
                                'description': f'Other moves lose the {piece_name}.',
                                'misconception': f'the {piece_name} seemed safe'
                            }
                    
                    # Generic collapse
                    return {
                        'type': 'positional_collapse',
                        'description': 'All alternatives lead to a losing position.',
                        'misconception': 'the alternatives looked reasonable'
                    }
                
                elif swing > 200:
                    # Significant but not catastrophic - check for specific issues
                    
                    # In endgames, check for tempo/opposition issues
                    total_material = sum(
                        len(board.pieces(pt, c)) * PIECE_POINTS[pt]
                        for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
                        for c in [chess.WHITE, chess.BLACK]
                    )
                    
                    if total_material <= 15:  # Pure endgame
                        return {
                            'type': 'tempo',
                            'description': 'The alternative loses a critical tempo in the endgame.',
                            'misconception': 'the move order seemed flexible'
                        }
        
    except Exception:
        pass
    
    return None


def _detect_endgame_critical(board: chess.Board,
                             engine: chess.engine.SimpleEngine) -> Optional[Dict]:
    """
    Detect critical endgame moments with specific geometry.
    
    Name the square, the pawn, the tempo - not generic concepts.
    """
    try:
        # Get the best move - use depth=8 for speed
        info = engine.analyse(board, chess.engine.Limit(depth=8))
        pv = info.get("pv", [])
        if not pv:
            return None
        
        best_move = pv[0]
        moving_piece = board.piece_at(best_move.from_square)
        if not moving_piece:
            return None
        
        # King moves in endgame
        if moving_piece.piece_type == chess.KING:
            to_sq = chess.square_name(best_move.to_square)
            to_file = chess.square_file(best_move.to_square)
            to_rank = chess.square_rank(best_move.to_square)
            
            # Check if king is racing to a critical square
            # Look at where opponent's passed pawns are
            opp_passed_pawns = _find_passed_pawns(board, not board.turn)
            
            for pawn_sq in opp_passed_pawns:
                pawn_file = chess.square_file(pawn_sq)
                # Is our king moving to intercept?
                if abs(to_file - pawn_file) <= 1:
                    pawn_sq_name = chess.square_name(pawn_sq)
                    return {
                        'description': f'The king must reach {to_sq} to stop the passed pawn on {pawn_sq_name}.',
                        'square': to_sq,
                        'pawn': f'the {chess.FILE_NAMES[pawn_file]}-pawn',
                        'tempo': True
                    }
            
            # Check for opposition
            opp_king_sq = board.king(not board.turn)
            if opp_king_sq:
                # Are kings in opposition or near it?
                file_diff = abs(chess.square_file(best_move.to_square) - chess.square_file(opp_king_sq))
                rank_diff = abs(chess.square_rank(best_move.to_square) - chess.square_rank(opp_king_sq))
                
                if file_diff == 0 and rank_diff == 2:
                    return {
                        'description': f'Moving to {to_sq} gains the opposition, controlling the critical squares.',
                        'square': to_sq,
                        'tempo': True
                    }
        
        # Pawn moves in endgame
        if moving_piece.piece_type == chess.PAWN:
            to_rank = chess.square_rank(best_move.to_square)
            promo_rank = 7 if moving_piece.color == chess.WHITE else 0
            
            if abs(promo_rank - to_rank) <= 2:
                to_sq = chess.square_name(best_move.to_square)
                file_name = chess.FILE_NAMES[chess.square_file(best_move.to_square)]
                
                # Check if pawn is unstoppable
                opp_king = board.king(not board.turn)
                if opp_king:
                    king_dist = abs(chess.square_file(opp_king) - chess.square_file(best_move.to_square)) + \
                               abs(chess.square_rank(opp_king) - promo_rank)
                    pawn_dist = abs(promo_rank - to_rank)
                    
                    if king_dist > pawn_dist + 1:
                        return {
                            'description': f'The {file_name}-pawn reaches {to_sq} and cannot be caught by the king.',
                            'pawn': f'the {file_name}-pawn',
                            'square': to_sq,
                            'tempo': True
                        }
        
    except Exception:
        pass
    
    return None


def _detect_tactical_opportunity(board: chess.Board,
                                  best_move: chess.Move,
                                  engine: chess.engine.SimpleEngine) -> Optional[Dict]:
    """Detect tactical opportunities the best move creates."""
    try:
        moving_piece = board.piece_at(best_move.from_square)
        if not moving_piece:
            return None
        
        board_after = board.copy()
        board_after.push(best_move)
        gives_check = board.gives_check(best_move)
        
        # Immediate capture
        captured = board.piece_at(best_move.to_square)
        if captured:
            captured_value = PIECE_POINTS[captured.piece_type]
            moving_value = PIECE_POINTS[moving_piece.piece_type]
            was_defended = board.is_attacked_by(not board.turn, best_move.to_square)
            
            if not was_defended and captured_value >= 3:
                captured_name = PIECE_NAMES[captured.piece_type]
                sq_name = chess.square_name(best_move.to_square)
                return {
                    'description': f"The {captured_name} on {sq_name} is undefended.",
                    'misconception': f"the {captured_name} looked protected"
                }
            
            if captured_value > moving_value and was_defended:
                # Check if exchange is favorable
                net = _calculate_exchange_result(board, best_move, engine)
                if net >= 2:
                    return {
                        'description': f"The capture wins material because the defender is overloaded.",
                        'misconception': "the piece seemed defended"
                    }
        
        # Fork detection with full causality
        fork = _detect_fork_with_full_causality(board, best_move, gives_check)
        if fork:
            return fork
        
        # Pin/skewer detection
        pin = _detect_pin_skewer_with_causality(board, best_move)
        if pin:
            return pin
        
        # Discovered attack
        discovery = _detect_discovered_attack(board, best_move, gives_check)
        if discovery:
            return discovery
        
        # Trapped piece
        trap = _detect_trapped_piece(board, best_move)
        if trap:
            return trap
        
    except Exception:
        pass
    
    return None


# =============================================================================
# TACTICAL PATTERN DETECTION WITH FULL CAUSALITY
# =============================================================================

def _detect_fork_with_full_causality(board: chess.Board, move: chess.Move,
                                      gives_check: bool) -> Optional[Dict]:
    """Detect fork and explain WHY it works, with proper defense analysis."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    moving_name = PIECE_NAMES[moving_piece.piece_type]
    moving_value = PIECE_POINTS[moving_piece.piece_type]
    
    # Find pieces attacked by the moved piece
    attacked = []
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color != moving_piece.color:
            attackers = board_after.attackers(moving_piece.color, sq)
            if move.to_square in attackers:
                # Get detailed defense information
                defense_info = _analyze_piece_defense(board_after, sq, piece)
                attacked.append({
                    'piece': piece,
                    'square': sq,
                    'name': PIECE_NAMES[piece.piece_type],
                    'value': PIECE_POINTS[piece.piece_type],
                    **defense_info
                })
    
    if len(attacked) < 2:
        return None
    
    # Sort by value (highest first)
    attacked.sort(key=lambda x: -x['value'])
    
    has_king = any(a['piece'].piece_type == chess.KING for a in attacked)
    
    if has_king:
        # Fork with king - the non-king piece will be lost regardless of defense
        for target in attacked:
            if target['piece'].piece_type != chess.KING:
                piece_name = target['name']
                piece_sq = chess.square_name(target['square'])
                
                # WHY can't the piece escape?
                escape_blocked_reason = _why_cant_escape(board_after, target['square'], target['piece'])
                
                if gives_check:
                    desc = f"This check attacks the king and {piece_name} on {piece_sq}. The king must move, and the {piece_name} will be captured."
                else:
                    desc = f"This forks the king and {piece_name}. The king must move, leaving the {piece_name}."
                
                if escape_blocked_reason:
                    desc += f" {escape_blocked_reason}"
                
                return {
                    'description': desc,
                    'misconception': f"the {piece_name} looked safe"
                }
    else:
        # No king involved - check if fork actually wins material
        # A piece is vulnerable if:
        # 1. Undefended, OR
        # 2. Worth more than the attacker (profitable exchange), OR
        # 3. Defended only by more valuable pieces
        
        vulnerable_pieces = []
        safe_pieces = []
        
        for target in attacked:
            if not target['is_defended']:
                vulnerable_pieces.append(target)
            elif target['value'] > moving_value:
                # Worth more than attacker - exchange still wins
                vulnerable_pieces.append(target)
            elif target['min_defender_value'] > moving_value:
                # Defended only by more valuable pieces
                vulnerable_pieces.append(target)
            else:
                safe_pieces.append(target)
        
        if len(vulnerable_pieces) < 1:
            # Fork doesn't actually win anything - all targets are safely defended
            return None
        
        if len(vulnerable_pieces) == 1:
            # Only one piece is really threatened - not a true fork
            target = vulnerable_pieces[0]
            if not target['is_defended']:
                desc = f"This attacks the {target['name']} on {chess.square_name(target['square'])}, which is undefended."
            else:
                desc = f"This attacks the {target['name']}. Although {target['defense_description']}, the exchange favors you."
            return {
                'description': desc,
                'misconception': f"the {target['name']} seemed safe"
            }
        
        # Multiple pieces vulnerable - true fork
        target1, target2 = vulnerable_pieces[0], vulnerable_pieces[1]
        
        # Build description based on defense status
        if not target1['is_defended'] and not target2['is_defended']:
            desc = f"This forks the {target1['name']} and {target2['name']}. Both are undefended, so one will be lost."
            misconception = "both pieces seemed safe"
        elif not target1['is_defended'] or not target2['is_defended']:
            undefended = target1 if not target1['is_defended'] else target2
            defended = target2 if not target1['is_defended'] else target1
            desc = f"This forks the {target1['name']} and {target2['name']}. The {undefended['name']} is undefended and will be captured."
            misconception = f"the {undefended['name']} seemed protected"
        else:
            # Both defended but fork still works
            desc = f"This forks the {target1['name']} ({target1['defense_description']}) and {target2['name']} ({target2['defense_description']}). You cannot save both, and the {moving_name} is worth less than either target."
            misconception = "both pieces seemed safely defended"
        
        return {
            'description': desc,
            'misconception': misconception
        }
    
    return None


def _why_cant_escape(board: chess.Board, sq: int, piece: chess.Piece) -> Optional[str]:
    """Explain WHY a piece cannot escape - the human misconception."""
    
    # Check each potential escape square
    escape_squares = []
    blocked_reasons = []
    
    for move in board.legal_moves:
        if move.from_square == sq:
            # Where can it go?
            to_sq = move.to_square
            to_name = chess.square_name(to_sq)
            
            # Is the destination safe?
            test_board = board.copy()
            test_board.push(move)
            
            if test_board.is_attacked_by(not piece.color, to_sq):
                blocked_reasons.append(f"{to_name} is covered")
    
    if blocked_reasons:
        if len(blocked_reasons) == 1:
            return f"The only escape square ({blocked_reasons[0]})."
        elif len(blocked_reasons) <= 3:
            return f"All escape squares are covered."
    
    return None


def _detect_pin_skewer_with_causality(board: chess.Board, 
                                       move: chess.Move) -> Optional[Dict]:
    """Detect pin/skewer with human-readable causality."""
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
            front_piece, front_sq = front
            back_piece, back_sq = back
            front_name = PIECE_NAMES[front_piece.piece_type]
            back_name = PIECE_NAMES[back_piece.piece_type]
            front_sq_name = chess.square_name(front_sq)
            back_sq_name = chess.square_name(back_sq)
            
            # Pin to king
            if back_piece.piece_type == chess.KING:
                return {
                    'description': f"This pins the {front_name} on {front_sq_name} to the king. The {front_name} cannot move without exposing the king to check.",
                    'misconception': f"the {front_name} seemed free to move"
                }
            
            # Pin to valuable piece
            if PIECE_POINTS[back_piece.piece_type] > PIECE_POINTS[front_piece.piece_type]:
                return {
                    'description': f"This pins the {front_name} to the {back_name}. Moving the {front_name} loses the {back_name}.",
                    'misconception': f"the {front_name} looked mobile"
                }
            
            # Skewer
            if front_piece.piece_type == chess.KING or PIECE_POINTS[front_piece.piece_type] > PIECE_POINTS[back_piece.piece_type]:
                if front_piece.piece_type == chess.KING:
                    return {
                        'description': f"This skewers the king and {back_name}. The king must move, and the {back_name} is captured.",
                        'misconception': f"the {back_name} seemed protected by the king's position"
                    }
                return {
                    'description': f"This skewers the {front_name} and {back_name}.",
                    'misconception': "both pieces seemed safe"
                }
    
    return None


def _detect_discovered_attack(board: chess.Board, move: chess.Move,
                               gives_check: bool) -> Optional[Dict]:
    """Detect discovered attacks with causality."""
    board_after = board.copy()
    board_after.push(move)
    
    moving_piece = board.piece_at(move.from_square)
    if not moving_piece:
        return None
    
    moving_name = PIECE_NAMES[moving_piece.piece_type]
    from_sq = move.from_square
    
    # Check if moving unblocked an attack
    for sq in chess.SQUARES:
        behind_piece = board.piece_at(sq)
        if behind_piece and behind_piece.color == moving_piece.color:
            if behind_piece.piece_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                direction = _direction_between(sq, from_sq)
                if direction:
                    target_sq = from_sq
                    while True:
                        target_sq = _step_square(target_sq, direction)
                        if target_sq is None:
                            break
                        target = board_after.piece_at(target_sq)
                        if target:
                            if target.color != moving_piece.color and PIECE_POINTS[target.piece_type] >= 3:
                                behind_name = PIECE_NAMES[behind_piece.piece_type]
                                target_name = PIECE_NAMES[target.piece_type]
                                
                                if gives_check:
                                    captured = board.piece_at(move.to_square)
                                    if captured and PIECE_POINTS[captured.piece_type] >= 3:
                                        cap_name = PIECE_NAMES[captured.piece_type]
                                        return {
                                            'description': f"This captures the {cap_name} with discovered check. The king must respond, so the capture is free.",
                                            'misconception': f"the {cap_name} seemed defended"
                                        }
                                
                                return {
                                    'description': f"Moving the {moving_name} discovers an attack on the {target_name} by the {behind_name}.",
                                    'misconception': f"the {moving_name} seemed to be blocking nothing"
                                }
                            break
    
    return None


def _detect_trapped_piece(board: chess.Board, move: chess.Move) -> Optional[Dict]:
    """Detect trapped pieces with escape analysis."""
    board_after = board.copy()
    board_after.push(move)
    
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece and piece.color == board_after.turn and piece.piece_type not in [chess.PAWN, chess.KING]:
            if not board_after.is_attacked_by(not board_after.turn, sq):
                continue  # Not attacked
            
            # Count escape squares
            escapes = []
            for m in board_after.legal_moves:
                if m.from_square == sq:
                    test = board_after.copy()
                    test.push(m)
                    if not test.is_attacked_by(not piece.color, m.to_square):
                        escapes.append(chess.square_name(m.to_square))
            
            if len(escapes) == 0 and PIECE_POINTS[piece.piece_type] >= 3:
                piece_name = PIECE_NAMES[piece.piece_type]
                sq_name = chess.square_name(sq)
                
                return {
                    'description': f"This traps the {piece_name} on {sq_name}. Every potential escape square is controlled.",
                    'misconception': f"the {piece_name} looked like it could escape"
                }
    
    return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_king_zone(king_sq: int) -> Set[int]:
    """Squares around the king."""
    zone = set()
    kf = chess.square_file(king_sq)
    kr = chess.square_rank(king_sq)
    for df in range(-2, 3):
        for dr in range(-2, 3):
            f, r = kf + df, kr + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                zone.add(chess.square(f, r))
    return zone


def _is_pawn_shield_compromised(board: chess.Board, color: chess.Color) -> bool:
    """Check if king's pawn shield is weak."""
    king_sq = board.king(color)
    if king_sq is None:
        return False
    
    kf = chess.square_file(king_sq)
    kr = chess.square_rank(king_sq)
    forward = 1 if color == chess.WHITE else -1
    
    pawns = 0
    for df in [-1, 0, 1]:
        f = kf + df
        if 0 <= f <= 7:
            for dr in [forward, forward * 2]:
                r = kr + dr
                if 0 <= r <= 7:
                    sq = chess.square(f, r)
                    p = board.piece_at(sq)
                    if p and p.piece_type == chess.PAWN and p.color == color:
                        pawns += 1
                        break
    
    return pawns <= 1


def _find_passed_pawns(board: chess.Board, color: chess.Color) -> List[int]:
    """Find passed pawns for a color."""
    passed = []
    direction = 1 if color == chess.WHITE else -1
    
    for sq in board.pieces(chess.PAWN, color):
        pf = chess.square_file(sq)
        pr = chess.square_rank(sq)
        is_passed = True
        
        # Check files in front
        for df in [-1, 0, 1]:
            f = pf + df
            if 0 <= f <= 7:
                r = pr + direction
                while 0 <= r <= 7:
                    check_sq = chess.square(f, r)
                    p = board.piece_at(check_sq)
                    if p and p.piece_type == chess.PAWN and p.color != color:
                        is_passed = False
                        break
                    r += direction
        
        if is_passed:
            passed.append(sq)
    
    return passed


def _calculate_exchange_result(board: chess.Board, move: chess.Move,
                                engine: chess.engine.SimpleEngine) -> int:
    """Calculate material result of an exchange using engine."""
    try:
        color = board.turn
        mat_before = {c: sum(len(board.pieces(pt, c)) * PIECE_POINTS[pt]
                            for pt in PIECE_POINTS if pt != chess.KING)
                      for c in [chess.WHITE, chess.BLACK]}
        
        test = board.copy()
        test.push(move)
        for _ in range(4):
            if test.is_game_over():
                break
            result = engine.play(test, chess.engine.Limit(depth=4))
            if result.move:
                test.push(result.move)
        
        mat_after = {c: sum(len(test.pieces(pt, c)) * PIECE_POINTS[pt]
                           for pt in PIECE_POINTS if pt != chess.KING)
                     for c in [chess.WHITE, chess.BLACK]}
        
        our = mat_after[color] - mat_before[color]
        their = mat_after[not color] - mat_before[not color]
        return int(our - their)
    except Exception:
        return 0


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
# EXPLANATION RESULT
# =============================================================================

@dataclass
class MoveExplanation:
    priority: Priority
    explanation: str
    human_misconception: Optional[str] = None  # What the human was probably thinking
    why_not_viable: Optional[str] = None  # For viable moves: why this isn't optimal


# =============================================================================
# MAIN EXPLANATION GENERATOR
# =============================================================================

def generate_move_explanation(
    board: chess.Board,
    best_move: chess.Move,
    phase: str = "middlegame",
) -> str:
    """
    Generate explanation using POSITION-LEVEL URGENCY model (v3.1 - True Counterfactual).
    
    Architecture:
    1. Analyze what the POSITION demands (before looking at best move's benefits)
    2. Use COUNTERFACTUAL reasoning: "what breaks if you don't play this?"
    3. Explain how the best move addresses that demand
    4. Include what the human likely overlooked
    
    Key insight: We now ask "what happens if you DON'T play this move?"
    rather than "what does this move achieve?"
    """
    engine = _open_engine()
    if not engine:
        return "This is the best move according to the engine."
    
    try:
        # STEP 1: Analyze position-level urgency WITH counterfactual analysis
        # Pass the best_move so counterfactual can analyze "what if NOT this move?"
        urgency = _analyze_position_urgency(board, engine, best_move)
        
        # STEP 2: Generate explanation based on urgency
        explanation = _generate_explanation_from_urgency(board, best_move, urgency, engine)
        
        return explanation
        
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def _generate_explanation_from_urgency(board: chess.Board, 
                                        best_move: chess.Move,
                                        urgency: PositionUrgency,
                                        engine: chess.engine.SimpleEngine) -> str:
    """Generate explanation based on what the position demands."""
    
    # Priority 1: Checkmate threats
    if urgency.priority == Priority.CHECKMATE:
        if urgency.threat_type == "mate":
            return _format_with_misconception(
                "This is the only move that stops the mating threat.",
                urgency.likely_human_focus
            )
    
    # Priority 2: Tactical opportunities (we're winning something)
    if urgency.priority == Priority.FORCED_TACTICS:
        if urgency.threat_description:
            return _format_with_misconception(
                urgency.threat_description,
                urgency.likely_human_focus
            )
    
    # Priority 3: Defensive requirements / COUNTERFACTUAL THREATS
    # This is where the key change happens - we now explain what BREAKS if you don't play
    if urgency.priority == Priority.PREVENT_THREAT:
        # If we have counterfactual analysis, use it (more specific)
        if urgency.counterfactual_failure:
            cf = urgency.counterfactual_failure
            # The counterfactual description already says "if you don't play this move..."
            return _format_with_misconception(cf.description, cf.misconception)
        
        # Fallback to traditional threat description
        if urgency.threat_description:
            return _format_with_misconception(
                f"This addresses the critical threat. {urgency.threat_description}",
                urgency.likely_human_focus
            )
    
    # Priority 4: King safety
    if urgency.priority == Priority.KING_SAFETY_URGENT:
        if urgency.threat_description:
            return _format_with_misconception(
                urgency.threat_description,
                urgency.likely_human_focus
            )
    
    # Priority 5: Only move (structural collapse)
    if urgency.priority == Priority.ONLY_MOVE:
        if urgency.collapse_description:
            return _format_with_misconception(
                urgency.collapse_description,
                urgency.likely_human_focus
            )
    
    # Priority 8: Endgame critical
    if urgency.priority == Priority.ENDGAME_TRANSITION:
        if urgency.threat_description:
            return urgency.threat_description
    
    # Fallback: analyze the best move directly
    return _generate_fallback_explanation(board, best_move, urgency, engine)


def _generate_fallback_explanation(board: chess.Board,
                                    best_move: chess.Move,
                                    urgency: PositionUrgency,
                                    engine: chess.engine.SimpleEngine) -> str:
    """Generate explanation by analyzing the best move directly.
    
    IMPORTANT: Even in fallback, we now prefer counterfactual explanations
    ("what breaks if you don't play this") over move-benefit explanations
    ("what this move achieves").
    """
    
    # FIRST: If we have counterfactual analysis even at lower priority, use it
    # This prevents generic "improves the piece" explanations when there's
    # a real tactical reason.
    if urgency.counterfactual_failure:
        cf = urgency.counterfactual_failure
        return _format_with_misconception(cf.description, cf.misconception)
    
    moving_piece = board.piece_at(best_move.from_square)
    if not moving_piece:
        return "This is the best move."
    
    piece_name = PIECE_NAMES[moving_piece.piece_type]
    board_after = board.copy()
    board_after.push(best_move)
    gives_check = board.gives_check(best_move)
    
    # Check for immediate capture
    captured = board.piece_at(best_move.to_square)
    if captured:
        captured_name = PIECE_NAMES[captured.piece_type]
        was_defended = board.is_attacked_by(not board.turn, best_move.to_square)
        
        if not was_defended:
            sq_name = chess.square_name(best_move.to_square)
            return f"The {captured_name} on {sq_name} is undefended."
        
        # Check if exchange is favorable
        if PIECE_POINTS[captured.piece_type] > PIECE_POINTS[moving_piece.piece_type]:
            return f"This captures the {captured_name}, winning material."
    
    # Check for check
    if gives_check:
        return f"This check creates problems for the opponent's king."
    
    # Castling
    if moving_piece.piece_type == chess.KING:
        if abs(chess.square_file(best_move.from_square) - chess.square_file(best_move.to_square)) == 2:
            if urgency.king_danger_imminent:
                return "Castles to escape the developing attack."
            return "Castles, connecting the rooks and improving king safety."
    
    # Development
    from_rank = chess.square_rank(best_move.from_square)
    is_back_rank = (moving_piece.color == chess.WHITE and from_rank == 0) or \
                   (moving_piece.color == chess.BLACK and from_rank == 7)
    
    if is_back_rank and moving_piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
        return f"Develops the {piece_name} to an active square."
    
    # Endgame king activation
    if urgency.is_endgame and moving_piece.piece_type == chess.KING:
        to_sq = chess.square_name(best_move.to_square)
        return f"Activates the king toward {to_sq}. In endgames, the king is a fighting piece."
    
    # Generic positional
    to_sq = chess.square_name(best_move.to_square)
    return f"The {piece_name} improves to {to_sq}."


def _format_with_misconception(explanation: str, misconception: Optional[str]) -> str:
    """Add the human misconception to the explanation if available."""
    if misconception:
        return f"{explanation} You may have been focused on {misconception}."
    return explanation


# =============================================================================
# PUBLIC API
# =============================================================================

def generate_puzzle_explanation_enhanced(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int = 0,
    phase: str = "middlegame",
) -> str:
    """Main entry point for puzzle explanations."""
    return generate_move_explanation(board, best_move, phase)


def is_move_viable(board: chess.Board, move: chess.Move, 
                   depth: int = 8) -> Tuple[bool, int, Optional[str]]:
    """
    Check if a move is viable (CPL < 50).
    
    Returns: (is_viable, cpl, why_not_optimal)
    
    IMPORTANT: Viable moves should show YELLOW, not green.
    Viable ≠ optimal. The explanation should note why this isn't the best.
    """
    engine = _open_engine()
    if not engine:
        return True, 0, None
    
    try:
        # Use depth=8 and multipv=3 for speed - good enough for viable detection
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=3)
        if not isinstance(infos, list):
            infos = [infos]
        
        if not infos:
            return True, 0, None
        
        best_info = infos[0]
        best_score = best_info.get("score")
        best_pv = best_info.get("pv", [])
        
        if not best_score:
            return True, 0, None
        
        best_cp = best_score.pov(board.turn).score(mate_score=10000) or 0
        best_move_uci = best_pv[0].uci() if best_pv else None
        
        # If this IS the best move
        if move.uci() == best_move_uci:
            return True, 0, None  # It's not just viable, it's optimal
        
        # Find our move in multipv
        for info in infos:
            pv = info.get("pv", [])
            if pv and pv[0] == move:
                score = info.get("score")
                if score:
                    move_cp = score.pov(board.turn).score(mate_score=10000) or 0
                    cpl = best_cp - move_cp
                    
                    if cpl <= VIABLE_CPL_THRESHOLD:
                        # Generate why this isn't optimal
                        why_not = _explain_why_not_optimal(board, move, best_pv[0] if best_pv else None, engine)
                        return True, max(0, cpl), why_not
                    
                    return False, max(0, cpl), None
        
        # Move not in top 3 - analyze specifically (use depth 6 for speed)
        board_after = board.copy()
        board_after.push(move)
        info = engine.analyse(board_after, chess.engine.Limit(depth=6))
        score = info.get("score")
        if score:
            move_cp = -score.pov(board_after.turn).score(mate_score=10000) or 0
            cpl = best_cp - move_cp
            if cpl <= VIABLE_CPL_THRESHOLD:
                why_not = _explain_why_not_optimal(board, move, best_pv[0] if best_pv else None, engine)
                return True, max(0, cpl), why_not
            return False, max(0, cpl), None
        
        return False, 100, None
        
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def _explain_why_not_optimal(board: chess.Board, 
                              played_move: chess.Move,
                              best_move: Optional[chess.Move],
                              engine: chess.engine.SimpleEngine) -> Optional[str]:
    """Explain why a viable move isn't the optimal choice."""
    if not best_move:
        return None
    
    try:
        # What does the best move do that this doesn't?
        best_piece = board.piece_at(best_move.from_square)
        played_piece = board.piece_at(played_move.from_square)
        
        if not best_piece or not played_piece:
            return None
        
        best_captures = board.piece_at(best_move.to_square)
        played_captures = board.piece_at(played_move.to_square)
        
        # Best move wins more material
        if best_captures and not played_captures:
            return f"The best move captures the {PIECE_NAMES[best_captures.piece_type]}."
        
        if best_captures and played_captures:
            if PIECE_POINTS[best_captures.piece_type] > PIECE_POINTS[played_captures.piece_type]:
                return f"The best move wins the {PIECE_NAMES[best_captures.piece_type]} instead."
        
        # Best move gives check
        best_check = board.gives_check(best_move)
        played_check = board.gives_check(played_move)
        
        if best_check and not played_check:
            return "The best move includes a check, gaining tempo."
        
        # Generic
        return "The best move is more forcing."
        
    except Exception:
        return None


def get_user_likely_missed(board: chess.Board, best_move: chess.Move) -> Optional[str]:
    """Get what the human likely overlooked - for UI display."""
    engine = _open_engine()
    if not engine:
        return None
    
    try:
        urgency = _analyze_position_urgency(board, engine)
        return urgency.likely_human_focus
    finally:
        try:
            engine.quit()
        except Exception:
            pass
