"""
Solution Line Computation for Multi-Move Puzzles

Determines when a puzzle requires a sequence of moves to complete,
rather than just a single move.

A move requires continuation when:
- It's a check that leads to checkmate
- It's a forcing sequence (checks/captures) that wins material
- The evaluation gain only comes from the full sequence

All computation is deterministic using python-chess.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
import chess
import chess.engine
import os
import shutil

# Try to import STOCKFISH_PATH, default to common location if not found
try:
    from src.engine_analysis import STOCKFISH_PATH
except ImportError:
    STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"


def _resolve_stockfish_cmd() -> str | None:
    """Return a usable Stockfish command/path, or None if not found."""
    env_path = (os.getenv("STOCKFISH_PATH") or "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    # Prefer configured default path if it exists.
    if STOCKFISH_PATH and os.path.exists(STOCKFISH_PATH):
        return STOCKFISH_PATH

    # Common locations across macOS + Linux.
    for p in (
        "/opt/homebrew/bin/stockfish",  # macOS (Homebrew on Apple Silicon)
        "/usr/local/bin/stockfish",     # macOS (Homebrew on Intel)
        "/usr/bin/stockfish",           # Linux
        "/usr/games/stockfish",         # Debian/Ubuntu
    ):
        if os.path.exists(p):
            return p

    # Finally, try PATH.
    found = shutil.which("stockfish")
    return found


def compute_solution_line(
    fen: str,
    first_move_uci: str,
    max_depth: int = 6,
    analysis_depth: int = 20,
) -> List[str]:
    """
    Compute the full solution line for a puzzle starting from first_move.
    
    Returns a list of UCI moves alternating: [player_move, opponent_response, player_move, ...]
    
    The line continues while:
    1. The position is not checkmate
    2. There's a clearly forcing continuation (check, significant capture)
    3. Opponent has a single reasonable response
    
    Args:
        fen: Starting position FEN
        first_move_uci: The first correct move (UCI notation)
        max_depth: Maximum total moves to include (default 6)
    
    Returns:
        List of UCI moves forming the complete solution
    """
    board = chess.Board(fen)
    solution = []
    player_color = board.turn
    
    # Apply first move
    try:
        first_move = chess.Move.from_uci(first_move_uci)
        if first_move not in board.legal_moves:
            return [first_move_uci]
    except Exception:
        return [first_move_uci]
    
    board.push(first_move)
    solution.append(first_move_uci)
    
    # Check if it's already checkmate
    if board.is_checkmate():
        return solution
    
    # If game is over (stalemate, etc.), stop
    if board.is_game_over():
        return solution
    
    # Normalize depth for determinism and safety
    try:
        analysis_depth = int(analysis_depth)
    except Exception:
        analysis_depth = 20
    if analysis_depth < 1:
        analysis_depth = 1

    # Initialize engine for analysis
    engine = None
    try:
        cmd = _resolve_stockfish_cmd()
        if not cmd:
            raise FileNotFoundError("stockfish not found")
        engine = chess.engine.SimpleEngine.popen_uci(cmd)
    except Exception:
        # If engine is required but fails, we can't compute the line reliably.
        # Fallback to single move to avoid crashing, but this indicates setup issue.
        print(
            "Warning: Stockfish not found (set STOCKFISH_PATH or install 'stockfish' in PATH). "
            "Puzzle continuation disabled."
        )
        return solution

    # If the first move already wins decisive material (after best defense), treat puzzle as complete.
    # This avoids awkward "cleanup" continuations after a straightforward win.
    # Increased threshold from 3 to 5 to allow more multi-move tactical puzzles through.
    def _material_points(b: chess.Board, color: chess.Color) -> int:
        values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
        }
        return sum(len(b.pieces(pt, color)) * v for pt, v in values.items())

    try:
        try:
            pov = not board.turn  # side that played first_move
            before_pts = _material_points(chess.Board(fen), pov)
            reply = engine.play(board, chess.engine.Limit(depth=analysis_depth)).move
            after = board.copy()
            if reply is not None and reply in after.legal_moves:
                after.push(reply)
            after_pts = _material_points(after, pov)
            # Only skip continuation if we won a rook or more (5+ points)
            # This allows puzzles that win a piece but have more forcing play
            if (after_pts - before_pts) >= 5:
                return solution
        except Exception:
            pass

        # Check if continuation is needed
        continuation = _find_forcing_continuation(
            board,
            player_color,
            max_depth - 1,
            engine,
            analysis_depth,
        )
        
        if continuation:
            solution.extend(continuation)
    finally:
        if engine:
            engine.quit()
    
    return solution


def _find_forcing_continuation(
    board: chess.Board,
    player_color: chess.Color,
    remaining_depth: int,
    engine: chess.engine.SimpleEngine,
    analysis_depth: int,
) -> List[str]:
    """
    Find the forcing continuation after a move.
    
    A continuation exists when:
    - Opponent has a single reasonable response AND
    - Player has a clearly best follow-up (check, capture, mate threat)
    """
    if remaining_depth <= 0:
        return []
    
    # It's opponent's turn - find their best response
    opponent_response = _find_best_opponent_response(board, engine, analysis_depth)
    
    if opponent_response is None:
        return []
    
    # Apply opponent's response
    board_after_response = board.copy()
    board_after_response.push(opponent_response)
    
    # Check if game is over
    if board_after_response.is_game_over():
        return [opponent_response.uci()]
    
    # Now it's player's turn again - find their forcing continuation
    player_continuation = _find_player_forcing_move(board_after_response, player_color, engine, analysis_depth)
    
    if player_continuation is None:
        # No clear continuation - puzzle ends here
        return []
    
    # Apply player's move
    board_after_player = board_after_response.copy()
    board_after_player.push(player_continuation)
    
    result = [opponent_response.uci(), player_continuation.uci()]
    
    # Check if checkmate
    if board_after_player.is_checkmate():
        return result
    
    # Recurse for more continuation
    further = _find_forcing_continuation(
        board_after_player,
        player_color,
        remaining_depth - 2,
        engine,
        analysis_depth,
    )
    result.extend(further)
    
    return result


def _find_best_opponent_response(
    board: chess.Board, 
    engine: chess.engine.SimpleEngine,
    analysis_depth: int,
) -> Optional[chess.Move]:
    """
    Find the opponent's best response to a forcing move using Stockfish.
    """
    legal_moves = list(board.legal_moves)
    
    if not legal_moves:
        return None
    
    # If only one legal move, that's the response
    if len(legal_moves) == 1:
        return legal_moves[0]
    
    try:
        # Use depth for determinism across runs/environments.
        result = engine.play(board, chess.engine.Limit(depth=int(analysis_depth)))
        return result.move
    except Exception:
        return None


def _find_player_forcing_move(
    board: chess.Board, 
    player_color: chess.Color,
    engine: chess.engine.SimpleEngine,
    analysis_depth: int,
) -> Optional[chess.Move]:
    """
    Find the player's forcing continuation move using Stockfish.
    
    Returns the best move if it is a check, capture, leads to mate,
    or is clearly the only good move in a winning position.
    """
    if board.turn != player_color:
        return None
    
    try:
        # Get best move with multipv to check if there are alternatives
        result = engine.analyse(board, chess.engine.Limit(depth=int(analysis_depth)), multipv=2)
        if not isinstance(result, list):
            result = [result]
        
        if not result or not result[0].get("pv"):
            return None
            
        best_move = result[0]["pv"][0]
        best_score = result[0].get("score")
        
        if not best_move:
            return None
            
        # Check if we should continue the line
        # We continue if the best move is forcing (check, capture, or mate)
        
        # Check for mate
        board_after = board.copy()
        board_after.push(best_move)
        if board_after.is_checkmate():
            return best_move
            
        # Check for check
        if board.gives_check(best_move):
            return best_move
            
        # Check for capture
        if board.is_capture(best_move):
            return best_move
        
        # For quiet moves, only continue if it's the ONLY good move
        # (big difference between best and second best)
        if len(result) >= 2 and result[1].get("score") and best_score:
            try:
                best_cp = best_score.pov(player_color).score(mate_score=10000) or 0
                second_cp = result[1]["score"].pov(player_color).score(mate_score=10000) or 0
                # If best move is much better than second (>= 150 cp difference), include it
                if (best_cp - second_cp) >= 150:
                    return best_move
            except Exception:
                pass
            
        # If it's a quiet move without big advantage, stop the puzzle line
        return None
        
    except Exception:
        return None


def _piece_value(piece_type: int) -> int:
    """Get piece value in centipawns."""
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }
    return values.get(piece_type, 0)



def _piece_value(piece_type: int) -> int:
    """Get piece value in centipawns."""
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }
    return values.get(piece_type, 0)


def is_multi_move_puzzle(fen: str, first_move_uci: str) -> bool:
    """
    Determine if a puzzle should be multi-move.
    
    Returns True if the first move is only strong because of a forced continuation.
    """
    solution = compute_solution_line(fen, first_move_uci)
    return len(solution) > 1


def get_solution_with_responses(solution_moves: List[str]) -> Tuple[List[str], List[str]]:
    """
    Split solution moves into player moves and opponent responses.
    
    Args:
        solution_moves: Full solution line [p1, o1, p2, o2, p3, ...]
    
    Returns:
        (player_moves, opponent_responses) where indices align:
        player_moves[i] is followed by opponent_responses[i] (if exists)
    """
    player_moves = solution_moves[::2]  # indices 0, 2, 4, ...
    opponent_responses = solution_moves[1::2]  # indices 1, 3, 5, ...
    return player_moves, opponent_responses
