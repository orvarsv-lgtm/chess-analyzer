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


def compute_solution_line(
    fen: str,
    first_move_uci: str,
    max_depth: int = 6,
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
    
    # Check if continuation is needed
    continuation = _find_forcing_continuation(board, player_color, max_depth - 1)
    
    if continuation:
        solution.extend(continuation)
    
    return solution


def _find_forcing_continuation(
    board: chess.Board,
    player_color: chess.Color,
    remaining_depth: int,
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
    opponent_response = _find_best_opponent_response(board)
    
    if opponent_response is None:
        return []
    
    # Apply opponent's response
    board_after_response = board.copy()
    board_after_response.push(opponent_response)
    
    # Check if game is over
    if board_after_response.is_game_over():
        return [opponent_response.uci()]
    
    # Now it's player's turn again - find their forcing continuation
    player_continuation = _find_player_forcing_move(board_after_response, player_color)
    
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
    further = _find_forcing_continuation(board_after_player, player_color, remaining_depth - 2)
    result.extend(further)
    
    return result


def _find_best_opponent_response(board: chess.Board) -> Optional[chess.Move]:
    """
    Find the opponent's best response to a forcing move.
    
    In a puzzle context, opponent plays the "best defense" which is usually:
    - The only legal move (if in check with one escape)
    - The most stubborn defense (delays mate longest)
    - A move that doesn't immediately lose more material
    """
    legal_moves = list(board.legal_moves)
    
    if not legal_moves:
        return None
    
    # If only one legal move, that's the response
    if len(legal_moves) == 1:
        return legal_moves[0]
    
    # If in check, find the best escape
    if board.is_check():
        return _find_best_check_escape(board, legal_moves)
    
    # Otherwise, find the most reasonable defense
    return _find_most_stubborn_defense(board, legal_moves)


def _find_best_check_escape(board: chess.Board, legal_moves: List[chess.Move]) -> Optional[chess.Move]:
    """Find the best way to escape check."""
    best_move = None
    best_score = -100000
    
    for move in legal_moves:
        score = _evaluate_defense_move(board, move)
        if score > best_score:
            best_score = score
            best_move = move
    
    return best_move


def _find_most_stubborn_defense(board: chess.Board, legal_moves: List[chess.Move]) -> Optional[chess.Move]:
    """Find the most stubborn defensive move."""
    # Score each move and return the best one
    best_move = None
    best_score = -100000
    
    for move in legal_moves:
        score = _evaluate_defense_move(board, move)
        if score > best_score:
            best_score = score
            best_move = move
    
    return best_move


def _evaluate_defense_move(board: chess.Board, move: chess.Move) -> int:
    """
    Evaluate a defensive move for the opponent.
    
    Higher score = better defense.
    """
    score = 0
    board_after = board.copy()
    board_after.push(move)
    
    # Immediate checkmate is worst
    if board_after.is_checkmate():
        return -10000
    
    # Being in check after is bad
    if board_after.is_check():
        score -= 500
    
    # King move when not necessary is usually bad
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.KING:
        score -= 50
    
    # Blocking with a valuable piece is bad
    if piece and piece.piece_type in (chess.QUEEN, chess.ROOK):
        score -= 100
    
    # Capturing the attacker is good
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured:
            score += _piece_value(captured.piece_type)
    
    return score


def _find_player_forcing_move(board: chess.Board, player_color: chess.Color) -> Optional[chess.Move]:
    """
    Find the player's forcing continuation move.
    
    A move is "forcing" if:
    - It's checkmate
    - It's check (with a clear follow-up)
    - It wins significant material with no good defense
    """
    if board.turn != player_color:
        return None
    
    legal_moves = list(board.legal_moves)
    
    # First, look for checkmate
    for move in legal_moves:
        board_after = board.copy()
        board_after.push(move)
        if board_after.is_checkmate():
            return move
    
    # Look for forcing checks that lead to mate or material
    best_check = None
    best_check_score = 0
    
    for move in legal_moves:
        if board.gives_check(move):
            score = _evaluate_forcing_move(board, move)
            if score > best_check_score:
                best_check_score = score
                best_check = move
    
    if best_check and best_check_score >= 300:  # At least minor piece equivalent
        return best_check
    
    # Look for winning captures
    best_capture = None
    best_capture_score = 0
    
    for move in legal_moves:
        if board.is_capture(move):
            score = _evaluate_forcing_move(board, move)
            if score > best_capture_score:
                best_capture_score = score
                best_capture = move
    
    if best_capture and best_capture_score >= 300:
        return best_capture
    
    return None


def _evaluate_forcing_move(board: chess.Board, move: chess.Move) -> int:
    """Evaluate how forcing/strong a move is."""
    score = 0
    board_after = board.copy()
    board_after.push(move)
    
    # Checkmate is best
    if board_after.is_checkmate():
        return 10000
    
    # Check is good
    if board.gives_check(move):
        score += 200
    
    # Capture value
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured:
            score += _piece_value(captured.piece_type)
    
    # Promotion is very good
    if move.promotion:
        score += 800
    
    # Check if opponent has limited responses
    num_responses = len(list(board_after.legal_moves))
    if num_responses <= 2:
        score += 100
    
    return score


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
