"""
Opponent Mistake Analysis for Puzzles

Analyzes what the opponent did wrong in the position that created
the puzzle opportunity. This helps players understand why the
tactical opportunity exists.

Example flow:
1. Opponent plays a move that creates a weakness
2. Player should exploit it but makes a mistake
3. Puzzle is generated from that position
4. This module explains what the opponent did wrong to create
   the opportunity in the first place.

All analysis is deterministic using Stockfish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List
import os
import shutil

import chess
import chess.engine


# Piece names for human-readable output
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

PIECE_POINTS = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


@dataclass
class OpponentMistake:
    """Analysis of what the opponent did wrong."""
    
    # The move the opponent played (UCI notation)
    opponent_move_uci: str
    
    # The move the opponent played (SAN notation)
    opponent_move_san: str
    
    # What the opponent should have played instead (SAN)
    best_move_san: Optional[str]
    
    # Centipawn loss from opponent's mistake (positive = bad for opponent)
    cp_loss: int
    
    # Human-readable explanation of why it was wrong
    explanation: str
    
    # What the correct move would have accomplished
    best_move_explanation: Optional[str]
    
    def to_dict(self) -> dict:
        return {
            "opponent_move_uci": self.opponent_move_uci,
            "opponent_move_san": self.opponent_move_san,
            "best_move_san": self.best_move_san,
            "cp_loss": self.cp_loss,
            "explanation": self.explanation,
            "best_move_explanation": self.best_move_explanation,
        }


def _resolve_stockfish_cmd() -> str | None:
    """Return a usable Stockfish command/path, or None if not found."""
    env_path = (os.getenv("STOCKFISH_PATH") or "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    for p in (
        "/opt/homebrew/bin/stockfish",  # macOS (Homebrew on Apple Silicon)
        "/usr/local/bin/stockfish",     # macOS (Homebrew on Intel)
        "/usr/bin/stockfish",           # Linux
        "/usr/games/stockfish",         # Debian/Ubuntu
    ):
        if os.path.exists(p):
            return p

    found = shutil.which("stockfish")
    return found


def _open_engine() -> Optional[chess.engine.SimpleEngine]:
    """Open Stockfish engine."""
    cmd = _resolve_stockfish_cmd()
    if not cmd:
        return None
    try:
        return chess.engine.SimpleEngine.popen_uci(cmd)
    except Exception:
        return None


def _score_to_cp(score: chess.engine.PovScore) -> int:
    """Convert score to centipawns (from POV of side to move)."""
    try:
        cp = score.score(mate_score=10000)
        return int(cp) if cp is not None else 0
    except Exception:
        return 0


def analyze_opponent_mistake(
    fen_before_opponent_move: str,
    opponent_move_uci: str,
    depth: int = 20,
) -> Optional[OpponentMistake]:
    """
    Analyze what the opponent did wrong to create the puzzle opportunity.
    
    Args:
        fen_before_opponent_move: FEN position BEFORE opponent's move
        opponent_move_uci: The move opponent played (UCI notation)
        depth: Stockfish analysis depth
    
    Returns:
        OpponentMistake analysis, or None if opponent's move was fine
    """
    engine = _open_engine()
    if not engine:
        return None
    
    try:
        board = chess.Board(fen_before_opponent_move)
        opponent_color = board.turn
        
        # Parse the opponent's move
        try:
            opponent_move = chess.Move.from_uci(opponent_move_uci)
            if opponent_move not in board.legal_moves:
                return None
            opponent_move_san = board.san(opponent_move)
        except Exception:
            return None
        
        # Get the best move for this position
        info = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
        if not isinstance(info, list):
            info = [info]
        
        if not info:
            return None
        
        best_info = info[0]
        best_pv = best_info.get("pv", [])
        best_score = best_info.get("score")
        
        if not best_pv or not best_score:
            return None
        
        best_move = best_pv[0]
        best_move_san = board.san(best_move)
        best_cp = _score_to_cp(best_score.pov(opponent_color))
        
        # If opponent played the best move, no mistake
        if opponent_move == best_move:
            return None
        
        # Find the score of opponent's actual move
        opponent_cp = None
        
        # Check if it's in multipv
        for pv_info in info:
            pv = pv_info.get("pv", [])
            if pv and pv[0] == opponent_move:
                score = pv_info.get("score")
                if score:
                    opponent_cp = _score_to_cp(score.pov(opponent_color))
                break
        
        # If not in multipv, analyze specifically
        if opponent_cp is None:
            board_after = board.copy()
            board_after.push(opponent_move)
            after_info = engine.analyse(board_after, chess.engine.Limit(depth=depth))
            after_score = after_info.get("score")
            if after_score:
                # Score is from player's perspective, negate for opponent
                opponent_cp = -_score_to_cp(after_score.pov(board_after.turn))
        
        if opponent_cp is None:
            return None
        
        # Calculate centipawn loss (positive = bad for opponent)
        cp_loss = best_cp - opponent_cp
        
        # Only report if it's a significant mistake (>= 50 centipawns)
        if cp_loss < 50:
            return None
        
        # Generate explanation
        explanation = _explain_opponent_mistake(
            board, opponent_move, best_move, cp_loss, engine, depth
        )
        
        # Generate best move explanation
        best_move_explanation = _explain_best_move(
            board, best_move, engine, depth
        )
        
        return OpponentMistake(
            opponent_move_uci=opponent_move_uci,
            opponent_move_san=opponent_move_san,
            best_move_san=best_move_san,
            cp_loss=cp_loss,
            explanation=explanation,
            best_move_explanation=best_move_explanation,
        )
        
    except Exception:
        return None
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def _explain_opponent_mistake(
    board: chess.Board,
    played_move: chess.Move,
    best_move: chess.Move,
    cp_loss: int,
    engine: chess.engine.SimpleEngine,
    depth: int,
) -> str:
    """Generate explanation of why opponent's move was wrong."""
    
    played_piece = board.piece_at(played_move.from_square)
    best_piece = board.piece_at(best_move.from_square)
    
    if not played_piece:
        return f"This move lost {cp_loss / 100:.1f} pawns of evaluation."
    
    played_name = PIECE_NAMES[played_piece.piece_type]
    played_to = chess.square_name(played_move.to_square)
    
    # Apply opponent's move and see what happens
    board_after = board.copy()
    board_after.push(played_move)
    
    # Get player's best response
    try:
        response_info = engine.analyse(board_after, chess.engine.Limit(depth=depth))
        response_pv = response_info.get("pv", [])
        
        if response_pv:
            response = response_pv[0]
            
            # Check for tactical consequences
            
            # 1. Does the response win material?
            if board_after.is_capture(response):
                captured = board_after.piece_at(response.to_square)
                if captured:
                    captured_name = PIECE_NAMES[captured.piece_type]
                    captured_sq = chess.square_name(response.to_square)
                    
                    # Check if the captured piece is the one that just moved
                    if response.to_square == played_move.to_square:
                        return f"Moving the {played_name} to {played_to} allowed it to be captured."
                    else:
                        return f"This move left the {captured_name} on {captured_sq} undefended."
            
            # 2. Does the response give check that wins material?
            if board_after.gives_check(response):
                # See if there's material win after check
                board_after_response = board_after.copy()
                board_after_response.push(response)
                
                # Get continuation
                cont_info = engine.analyse(board_after_response, chess.engine.Limit(depth=depth // 2))
                cont_pv = cont_info.get("pv", [])
                
                if cont_pv:
                    for cont_move in cont_pv[:3]:
                        if cont_move in board_after_response.legal_moves and board_after_response.is_capture(cont_move):
                            captured = board_after_response.piece_at(cont_move.to_square)
                            if captured:
                                captured_name = PIECE_NAMES[captured.piece_type]
                                return f"This move allowed a check that wins the {captured_name}."
                        if cont_move in board_after_response.legal_moves:
                            board_after_response.push(cont_move)
                
                return "This move allowed a forcing check sequence."
            
            # 3. Does it create a fork or double attack?
            board_after_response = board_after.copy()
            board_after_response.push(response)
            attacked_pieces = []
            
            # Check what pieces are now attacked
            response_piece = board_after.piece_at(response.from_square)
            if response_piece:
                for sq in chess.SQUARES:
                    piece = board_after_response.piece_at(sq)
                    if piece and piece.color == board.turn:  # Opponent's pieces
                        if board_after_response.is_attacked_by(not board.turn, sq):
                            if PIECE_POINTS[piece.piece_type] >= 3:
                                attacked_pieces.append(piece.piece_type)
                
                if len(attacked_pieces) >= 2:
                    return f"This move allowed a fork attacking multiple pieces."
            
            # 4. Does it allow a pin or skewer?
            moving_piece = board_after.piece_at(response.from_square)
            if moving_piece and moving_piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                return f"This move created a tactical opportunity."
    
    except Exception:
        pass
    
    # Generic explanations based on CPL severity
    if cp_loss >= 300:
        return f"This was a serious mistake that lost significant material or position."
    elif cp_loss >= 150:
        return f"This move created a tactical weakness that can be exploited."
    else:
        return f"This move was inaccurate and allowed a tactical opportunity."


def _explain_best_move(
    board: chess.Board,
    best_move: chess.Move,
    engine: chess.engine.SimpleEngine,
    depth: int,
) -> Optional[str]:
    """Explain what the best move would have accomplished."""
    
    best_piece = board.piece_at(best_move.from_square)
    if not best_piece:
        return None
    
    piece_name = PIECE_NAMES[best_piece.piece_type]
    to_sq = chess.square_name(best_move.to_square)
    
    # Check for captures
    if board.is_capture(best_move):
        captured = board.piece_at(best_move.to_square)
        if captured:
            captured_name = PIECE_NAMES[captured.piece_type]
            return f"Instead, capturing the {captured_name} was best."
    
    # Check for defending moves
    board_after = board.copy()
    board_after.push(best_move)
    
    # Did this defend something?
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == board.turn and piece.piece_type != chess.PAWN:
            was_defended = board.is_attacked_by(board.turn, sq)
            is_defended = board_after.is_attacked_by(board.turn, sq)
            
            if is_defended and not was_defended:
                defended_name = PIECE_NAMES[piece.piece_type]
                return f"The {piece_name} move to {to_sq} would have defended the {defended_name}."
    
    # Check for centralization/development
    if best_piece.piece_type in (chess.KNIGHT, chess.BISHOP):
        to_file = chess.square_file(best_move.to_square)
        to_rank = chess.square_rank(best_move.to_square)
        if to_file in (2, 3, 4, 5) and to_rank in (2, 3, 4, 5):
            return f"Better was to centralize the {piece_name}."
    
    # Check for castling
    if best_piece.piece_type == chess.KING:
        if abs(chess.square_file(best_move.from_square) - chess.square_file(best_move.to_square)) > 1:
            return "Castling would have been safer for the king."
    
    return f"The better move was {board.san(best_move)}."
