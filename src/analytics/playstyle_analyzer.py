# src/analytics/playstyle_analyzer.py
"""Module 7: Playstyle Analysis & Piece Performance.

Categorize players by playstyle and identify strongest/weakest pieces.

Playstyle Categories:
- Tactical: High rate of tactics, sacrifices, sharp positions
- Positional: Solid play, piece maneuvering, long-term planning
- Aggressive: King attacks, piece activity toward enemy camp
- Defensive: Solid defenses, counterattacking style

Piece Performance:
- Track CPL contribution by piece type
- Identify which pieces are involved in blunders/brilliant moves

Implementation uses:
- Move classification (captures, checks, piece movements)
- Board position analysis (piece activity zones)
- Material sacrifice patterns
- Pawn structure dynamics
- NO LLM inference
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Any

import chess

if TYPE_CHECKING:
    pass


@dataclass
class PiecePerformance:
    """Performance stats for a single piece type."""
    piece_name: str = ""
    moves: int = 0
    total_cp_loss: int = 0
    avg_cpl: float = 0.0
    blunders: int = 0
    mistakes: int = 0
    excellent_moves: int = 0  # moves with cp_loss == 0 or gain
    captures: int = 0
    checks: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "piece_name": self.piece_name,
            "moves": self.moves,
            "avg_cpl": round(self.avg_cpl, 1),
            "blunders": self.blunders,
            "mistakes": self.mistakes,
            "excellent_moves": self.excellent_moves,
            "captures": self.captures,
            "checks": self.checks,
        }


@dataclass
class PlaystyleProfile:
    """Player's playstyle categorization and piece analysis."""
    # Primary and secondary playstyle
    primary_style: str = ""  # tactical, positional, aggressive, defensive
    secondary_style: str = ""
    style_confidence: int = 0  # 0-100, how confident we are in classification
    
    # Style scores (0-100 each)
    tactical_score: int = 0
    positional_score: int = 0
    aggressive_score: int = 0
    defensive_score: int = 0
    
    # Style indicators
    style_indicators: list[str] = field(default_factory=list)
    
    # Piece performance
    piece_stats: dict[str, PiecePerformance] = field(default_factory=dict)
    strongest_piece: str = ""
    weakest_piece: str = ""
    strongest_piece_reason: str = ""
    weakest_piece_reason: str = ""
    
    # Move type distribution
    capture_rate_pct: int = 0
    check_rate_pct: int = 0
    castle_rate_pct: int = 0
    pawn_push_rate_pct: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_style": self.primary_style,
            "secondary_style": self.secondary_style,
            "style_confidence": self.style_confidence,
            "style_scores": {
                "tactical": self.tactical_score,
                "positional": self.positional_score,
                "aggressive": self.aggressive_score,
                "defensive": self.defensive_score,
            },
            "style_indicators": self.style_indicators[:6],
            "piece_performance": {k: v.to_dict() for k, v in self.piece_stats.items() if v.moves > 0},
            "strongest_piece": self.strongest_piece,
            "weakest_piece": self.weakest_piece,
            "strongest_piece_reason": self.strongest_piece_reason,
            "weakest_piece_reason": self.weakest_piece_reason,
            "move_distribution": {
                "capture_rate_pct": self.capture_rate_pct,
                "check_rate_pct": self.check_rate_pct,
                "castle_rate_pct": self.castle_rate_pct,
                "pawn_push_rate_pct": self.pawn_push_rate_pct,
            },
        }


# Thresholds
BLUNDER_CP = 300
MISTAKE_CP = 100
EXCELLENT_MOVE_THRESHOLD = 5  # cp_loss <= 5 is excellent


def _piece_type_name(piece_type: int) -> str:
    """Get human-readable piece name."""
    return {
        chess.PAWN: "Pawn",
        chess.KNIGHT: "Knight",
        chess.BISHOP: "Bishop",
        chess.ROOK: "Rook",
        chess.QUEEN: "Queen",
        chess.KING: "King",
    }.get(piece_type, "Unknown")


def _parse_san_piece_type(san: str) -> int:
    """Extract piece type from SAN notation."""
    if not san:
        return chess.PAWN
    
    # Handle castling
    if san.startswith("O-O"):
        return chess.KING
    
    # First character indicates piece (uppercase)
    first = san[0]
    if first == "N":
        return chess.KNIGHT
    elif first == "B":
        return chess.BISHOP
    elif first == "R":
        return chess.ROOK
    elif first == "Q":
        return chess.QUEEN
    elif first == "K":
        return chess.KING
    else:
        # Lowercase or file letter = pawn
        return chess.PAWN


def _is_capture(san: str) -> bool:
    """Check if move is a capture."""
    return "x" in san if san else False


def _is_check(san: str) -> bool:
    """Check if move gives check."""
    return "+" in san or "#" in san if san else False


def _is_castle(san: str) -> bool:
    """Check if move is castling."""
    return san.startswith("O-O") if san else False


def _is_pawn_push(san: str) -> bool:
    """Check if move is a pawn push (not capture)."""
    if not san or "x" in san:
        return False
    first = san[0]
    return first.islower() and first in "abcdefgh"


def _calculate_piece_activity_score(
    moves_by_piece: dict[int, int],
    total_moves: int,
) -> float:
    """Calculate how actively pieces are being used (0-1)."""
    if total_moves == 0:
        return 0.5
    
    # Weight by piece importance
    weights = {
        chess.KNIGHT: 1.2,
        chess.BISHOP: 1.2,
        chess.ROOK: 1.0,
        chess.QUEEN: 0.8,  # Queen moves are common but not always active
        chess.KING: 0.5,
    }
    
    active_moves = sum(
        moves_by_piece.get(pt, 0) * weights.get(pt, 1.0)
        for pt in weights
    )
    pawn_moves = moves_by_piece.get(chess.PAWN, 0)
    
    # Higher ratio of piece moves to pawn moves = more active
    piece_ratio = active_moves / (active_moves + pawn_moves + 1)
    return min(1.0, piece_ratio * 1.5)


def _calculate_aggression_score(
    captures: int,
    checks: int,
    total_moves: int,
    avg_cpl: float,
) -> int:
    """Calculate aggression score (0-100)."""
    if total_moves == 0:
        return 50
    
    capture_rate = captures / total_moves
    check_rate = checks / total_moves
    
    # Aggressive players have high capture/check rates
    base_score = (capture_rate * 150 + check_rate * 300)
    
    # But if CPL is high, it's reckless, not aggressive
    if avg_cpl > 80:
        base_score *= 0.7
    
    return min(100, max(0, int(base_score)))


def _calculate_tactical_score(
    blunders: int,
    mistakes: int,
    excellent_moves: int,
    total_moves: int,
    captures: int,
    checks: int,
) -> int:
    """Calculate tactical ability score (0-100).
    
    Tactical players: find tactics, make forcing moves, but also may blunder.
    """
    if total_moves == 0:
        return 50
    
    # Forcing moves ratio
    forcing_rate = (captures + checks) / total_moves
    
    # Accuracy in complications
    accuracy = excellent_moves / total_moves if total_moves else 0
    
    # Tactical score = forcing moves + accuracy
    base_score = (forcing_rate * 100 + accuracy * 60) / 1.6
    
    # Penalize excessive blunders (tactics requires accuracy)
    blunder_rate = blunders / total_moves
    if blunder_rate > 0.02:
        base_score *= 0.8
    
    return min(100, max(0, int(base_score)))


def _calculate_positional_score(
    pawn_moves: int,
    total_moves: int,
    avg_cpl: float,
    piece_distribution: dict[int, int],
) -> int:
    """Calculate positional play score (0-100).
    
    Positional players: pawn structure focus, steady piece improvement, low CPL.
    """
    if total_moves == 0:
        return 50
    
    # Low CPL indicates solid positional play
    cpl_score = max(0, 100 - avg_cpl) / 100 * 40
    
    # Balanced piece usage
    piece_counts = [v for k, v in piece_distribution.items() if k != chess.PAWN and v > 0]
    if piece_counts:
        variance = sum((x - sum(piece_counts)/len(piece_counts))**2 for x in piece_counts) / len(piece_counts)
        balance_score = max(0, 30 - variance)
    else:
        balance_score = 15
    
    # Pawn structure attention (moderate pawn moves)
    pawn_rate = pawn_moves / total_moves
    pawn_score = 30 if 0.15 < pawn_rate < 0.40 else 15
    
    return min(100, max(0, int(cpl_score + balance_score + pawn_score)))


def _calculate_defensive_score(
    avg_cpl: float,
    blunders: int,
    total_moves: int,
    castle_count: int,
    games_analyzed: int,
) -> int:
    """Calculate defensive solidity score (0-100).
    
    Defensive players: few blunders, castle regularly, steady play.
    """
    if total_moves == 0:
        return 50
    
    # Low blunder rate is defensive
    blunder_rate = blunders / total_moves
    blunder_score = max(0, 40 - blunder_rate * 1000)
    
    # Low CPL = solid defense
    cpl_score = max(0, 100 - avg_cpl) / 100 * 30
    
    # Castling habit
    castle_rate = castle_count / games_analyzed if games_analyzed else 0
    castle_score = min(30, castle_rate * 35)
    
    return min(100, max(0, int(blunder_score + cpl_score + castle_score)))


def analyze_playstyle(games_data: list[dict[str, Any]]) -> PlaystyleProfile:
    """Analyze player's playstyle and piece performance from games data.
    
    Args:
        games_data: List of game dicts with move_evals
        
    Returns:
        PlaystyleProfile with style classification and piece stats
    """
    profile = PlaystyleProfile()
    
    # Initialize piece stats
    for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
        name = _piece_type_name(pt)
        profile.piece_stats[name] = PiecePerformance(piece_name=name)
    
    # Aggregate stats
    total_moves = 0
    total_cp_loss = 0
    total_blunders = 0
    total_mistakes = 0
    total_excellent = 0
    total_captures = 0
    total_checks = 0
    total_castles = 0
    total_pawn_pushes = 0
    moves_by_piece: dict[int, int] = {}
    
    for game in games_data:
        move_evals = game.get("move_evals", []) or []
        
        for m in move_evals:
            san = str(m.get("san") or "")
            cp_loss = int(m.get("cp_loss") or 0)
            
            if not san:
                continue
            
            total_moves += 1
            total_cp_loss += min(cp_loss, 2000)
            
            # Classify move
            is_blunder = cp_loss >= BLUNDER_CP
            is_mistake = MISTAKE_CP <= cp_loss < BLUNDER_CP
            is_excellent = cp_loss <= EXCELLENT_MOVE_THRESHOLD
            is_cap = _is_capture(san)
            is_chk = _is_check(san)
            is_cast = _is_castle(san)
            is_pawn = _is_pawn_push(san)
            
            if is_blunder:
                total_blunders += 1
            if is_mistake:
                total_mistakes += 1
            if is_excellent:
                total_excellent += 1
            if is_cap:
                total_captures += 1
            if is_chk:
                total_checks += 1
            if is_cast:
                total_castles += 1
            if is_pawn:
                total_pawn_pushes += 1
            
            # Track by piece
            piece_type = _parse_san_piece_type(san)
            piece_name = _piece_type_name(piece_type)
            moves_by_piece[piece_type] = moves_by_piece.get(piece_type, 0) + 1
            
            ps = profile.piece_stats[piece_name]
            ps.moves += 1
            ps.total_cp_loss += min(cp_loss, 2000)
            if is_blunder:
                ps.blunders += 1
            if is_mistake:
                ps.mistakes += 1
            if is_excellent:
                ps.excellent_moves += 1
            if is_cap:
                ps.captures += 1
            if is_chk:
                ps.checks += 1
    
    # Calculate averages
    avg_cpl = total_cp_loss / total_moves if total_moves else 0
    
    for ps in profile.piece_stats.values():
        if ps.moves > 0:
            ps.avg_cpl = ps.total_cp_loss / ps.moves
    
    # Move distribution percentages
    if total_moves > 0:
        profile.capture_rate_pct = int(total_captures / total_moves * 100)
        profile.check_rate_pct = int(total_checks / total_moves * 100)
        profile.castle_rate_pct = int(total_castles / len(games_data) * 100) if games_data else 0
        profile.pawn_push_rate_pct = int(total_pawn_pushes / total_moves * 100)
    
    # Calculate style scores
    profile.tactical_score = _calculate_tactical_score(
        total_blunders, total_mistakes, total_excellent,
        total_moves, total_captures, total_checks
    )
    profile.positional_score = _calculate_positional_score(
        moves_by_piece.get(chess.PAWN, 0), total_moves, avg_cpl, moves_by_piece
    )
    profile.aggressive_score = _calculate_aggression_score(
        total_captures, total_checks, total_moves, avg_cpl
    )
    profile.defensive_score = _calculate_defensive_score(
        avg_cpl, total_blunders, total_moves, total_castles, len(games_data)
    )
    
    # Determine primary and secondary styles
    styles = [
        ("Tactical", profile.tactical_score),
        ("Positional", profile.positional_score),
        ("Aggressive", profile.aggressive_score),
        ("Defensive", profile.defensive_score),
    ]
    styles.sort(key=lambda x: x[1], reverse=True)
    
    profile.primary_style = styles[0][0]
    profile.secondary_style = styles[1][0]
    
    # Confidence based on score difference
    if styles[0][1] > 0:
        diff = styles[0][1] - styles[1][1]
        profile.style_confidence = min(100, max(30, 50 + diff))
    else:
        profile.style_confidence = 30
    
    # Generate style indicators
    indicators = []
    if profile.capture_rate_pct >= 15:
        indicators.append(f"High capture rate ({profile.capture_rate_pct}%)")
    if profile.check_rate_pct >= 5:
        indicators.append(f"Frequent checks ({profile.check_rate_pct}%)")
    if avg_cpl <= 40:
        indicators.append("Very accurate play")
    elif avg_cpl <= 60:
        indicators.append("Solid accuracy")
    if total_blunders / total_moves < 0.01 and total_moves > 50:
        indicators.append("Rarely blunders")
    if profile.pawn_push_rate_pct >= 25:
        indicators.append("Pawn-structure focused")
    if profile.castle_rate_pct >= 80:
        indicators.append("Always castles")
    profile.style_indicators = indicators[:6]
    
    # Determine strongest and weakest pieces (excluding King)
    piece_scores: list[tuple[str, float, int]] = []
    for name, ps in profile.piece_stats.items():
        if name == "King" or ps.moves < 5:  # Skip King and pieces with few moves
            continue
        
        # Score = accuracy (inverse CPL) + excellent move rate
        if ps.moves > 0:
            accuracy_score = max(0, 100 - ps.avg_cpl)
            excellent_rate = ps.excellent_moves / ps.moves * 50
            blunder_penalty = ps.blunders / ps.moves * 100
            score = accuracy_score + excellent_rate - blunder_penalty
            piece_scores.append((name, score, ps.moves))
    
    if piece_scores:
        piece_scores.sort(key=lambda x: x[1], reverse=True)
        
        strongest = piece_scores[0]
        weakest = piece_scores[-1]
        
        profile.strongest_piece = strongest[0]
        profile.weakest_piece = weakest[0]
        
        # Generate reasons
        strong_ps = profile.piece_stats[strongest[0]]
        weak_ps = profile.piece_stats[weakest[0]]
        
        profile.strongest_piece_reason = _generate_piece_reason(strong_ps, is_strong=True)
        profile.weakest_piece_reason = _generate_piece_reason(weak_ps, is_strong=False)
    
    return profile


def _generate_piece_reason(ps: PiecePerformance, is_strong: bool) -> str:
    """Generate human-readable reason for piece strength/weakness."""
    reasons = []
    
    if ps.moves == 0:
        return "Insufficient data"
    
    if is_strong:
        if ps.avg_cpl < 30:
            reasons.append(f"low avg CPL ({ps.avg_cpl:.0f})")
        excellent_rate = ps.excellent_moves / ps.moves * 100
        if excellent_rate > 60:
            reasons.append(f"{excellent_rate:.0f}% excellent moves")
        if ps.blunders == 0:
            reasons.append("no blunders")
        if ps.captures > ps.moves * 0.3:
            reasons.append("effective captures")
    else:
        if ps.avg_cpl > 60:
            reasons.append(f"high avg CPL ({ps.avg_cpl:.0f})")
        if ps.blunders > 0:
            blunder_rate = ps.blunders / ps.moves * 100
            reasons.append(f"{blunder_rate:.0f}% blunder rate")
        if ps.mistakes > ps.moves * 0.1:
            reasons.append("frequent mistakes")
    
    if not reasons:
        return "Based on overall move quality"
    
    return ", ".join(reasons[:3]).capitalize()
