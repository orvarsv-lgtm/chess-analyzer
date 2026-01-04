"""
Puzzle Engine - Deterministic Puzzle Generation from Analyzed Games

Generates chess puzzles from engine-analyzed games by extracting positions
where significant mistakes (blunders/mistakes) were made.

All logic is deterministic - no AI/LLM, no randomness.
Puzzles are derived purely from engine evaluation data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Any
import hashlib

import chess

from .puzzle_types import Puzzle, PuzzleType, Difficulty
from .difficulty import classify_difficulty


# =============================================================================
# PUZZLE TRIGGER THRESHOLDS
# =============================================================================

# Minimum eval loss to generate a puzzle (centipawns)
MIN_PUZZLE_EVAL_LOSS = 100  # 1 pawn = tactical opportunity

# Clear blunder threshold (used for puzzle type detection)
BLUNDER_EVAL_LOSS = 300

# Opening move threshold (for opening_error detection)
OPENING_MOVE_THRESHOLD = 10


# =============================================================================
# PUZZLE TYPE CLASSIFICATION
# =============================================================================


def _classify_puzzle_type(
    board: chess.Board,
    best_move: chess.Move,
    played_move: chess.Move,
    eval_loss_cp: int,
    phase: str,
    move_number: int,
) -> PuzzleType:
    """
    Classify puzzle type based on position characteristics.
    
    Classification Rules (deterministic):
    
    1. OPENING_ERROR: Deviation before move 10
       - Early-game mistakes often stem from opening preparation gaps
    
    2. ENDGAME_TECHNIQUE: Error in endgame phase + significant eval loss
       - Endgame errors require different training approach
    
    3. MISSED_TACTIC: Default for middlegame/tactical positions
       - Includes: captures, forks, pins, discovered attacks
    
    Args:
        board: Position before the move
        best_move: The correct move that should have been played
        played_move: The move that was actually played (mistake)
        eval_loss_cp: Centipawn loss from the mistake
        phase: Game phase ("opening", "middlegame", "endgame")
        move_number: Move number in the game
    
    Returns:
        PuzzleType classification
    """
    # Opening error: deviation before move 10
    if move_number <= OPENING_MOVE_THRESHOLD and phase == "opening":
        return PuzzleType.OPENING_ERROR
    
    # Endgame technique: error in simplified position
    if phase == "endgame" and eval_loss_cp >= MIN_PUZZLE_EVAL_LOSS:
        # Additional check: low material count
        total_pieces = len(board.piece_map())
        if total_pieces <= 12:  # King + few pieces each side
            return PuzzleType.ENDGAME_TECHNIQUE
    
    # Check for tactical motifs in the best move
    # (capture, check, fork potential)
    is_capture = board.is_capture(best_move)
    is_check = board.gives_check(best_move)
    
    # Fork detection: after best move, are 2+ valuable pieces attacked?
    board_after = board.copy()
    board_after.push(best_move)
    is_fork = _is_fork_position(board_after)
    
    # Pin detection
    is_pin_related = _involves_pin(board, best_move)
    
    # Discovery detection
    is_discovery = _is_discovered_attack(board, best_move)
    
    # If any tactical motif detected -> missed tactic
    if is_capture or is_check or is_fork or is_pin_related or is_discovery:
        return PuzzleType.MISSED_TACTIC
    
    # Endgame phase but no clear tactic
    if phase == "endgame":
        return PuzzleType.ENDGAME_TECHNIQUE
    
    # Default: missed tactic (most common)
    return PuzzleType.MISSED_TACTIC


def _is_fork_position(board: chess.Board) -> bool:
    """Check if position has a fork (one piece attacks 2+ valuable pieces)."""
    attacker_color = not board.turn  # Side that just moved
    attacked_pieces = 0
    
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.color == board.turn:  # Opponent's pieces
            if board.is_attacked_by(attacker_color, square):
                # Count valuable pieces (not pawns)
                if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
                    attacked_pieces += 1
    
    return attacked_pieces >= 2


def _involves_pin(board: chess.Board, move: chess.Move) -> bool:
    """Check if move involves creating or exploiting a pin."""
    # Simplified detection: check if moving piece was on a ray to opponent king
    piece = board.piece_at(move.from_square)
    if not piece:
        return False
    
    # Get opponent king square
    opponent_color = not board.turn
    king_square = board.king(opponent_color)
    if king_square is None:
        return False
    
    # Check if move creates a battery/pin along king direction
    board_after = board.copy()
    board_after.push(move)
    
    # Check for pieces now aligned with king
    for attacker_square in chess.SQUARES:
        attacker = board_after.piece_at(attacker_square)
        if attacker and attacker.color == board.turn:
            if attacker.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Check if there's a line to king through another piece
                ray = chess.ray(attacker_square, king_square)
                if ray:
                    pinned_count = 0
                    for sq in chess.SquareSet(ray):
                        if sq == attacker_square or sq == king_square:
                            continue
                        if board_after.piece_at(sq):
                            pinned_count += 1
                    if pinned_count == 1:
                        return True
    
    return False


def _is_discovered_attack(board: chess.Board, move: chess.Move) -> bool:
    """Check if move creates a discovered attack."""
    piece = board.piece_at(move.from_square)
    if not piece:
        return False
    
    # After the piece moves, check if another piece now has a new attack line
    board_after = board.copy()
    board_after.push(move)
    
    # Get attacked squares before and after
    from_square = move.from_square
    
    # Check if moving away unblocked an attack on a valuable piece
    for behind_square in chess.SQUARES:
        blocker_piece = board.piece_at(behind_square)
        if blocker_piece and blocker_piece.color == board.turn:
            if blocker_piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                # Check ray through from_square
                if from_square in chess.SquareSet(chess.ray(behind_square, from_square)):
                    # Now check what's beyond
                    direction = _get_direction(behind_square, from_square)
                    target = from_square
                    while True:
                        target = _next_square_in_direction(target, direction)
                        if target is None:
                            break
                        target_piece = board_after.piece_at(target)
                        if target_piece:
                            # We found a piece that's now attacked
                            if target_piece.color != board.turn:
                                return True
                            break
    
    return False


def _get_direction(from_sq: int, to_sq: int) -> Optional[tuple]:
    """Get direction vector from one square to another."""
    from_file = chess.square_file(from_sq)
    from_rank = chess.square_rank(from_sq)
    to_file = chess.square_file(to_sq)
    to_rank = chess.square_rank(to_sq)
    
    df = to_file - from_file
    dr = to_rank - from_rank
    
    if df != 0:
        df = df // abs(df)
    if dr != 0:
        dr = dr // abs(dr)
    
    if df == 0 and dr == 0:
        return None
    return (df, dr)


def _next_square_in_direction(square: int, direction: Optional[tuple]) -> Optional[int]:
    """Get next square in direction, or None if off board."""
    if direction is None:
        return None
    
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    
    new_file = file + direction[0]
    new_rank = rank + direction[1]
    
    if 0 <= new_file <= 7 and 0 <= new_rank <= 7:
        return chess.square(new_file, new_rank)
    return None


# =============================================================================
# BEST MOVE CALCULATION
# =============================================================================


def _calculate_best_move_from_analysis(
    move_evals: List[dict],
    game_index: int,
    board: chess.Board,
) -> Optional[str]:
    """
    Calculate best move for a position from surrounding analysis data.
    
    This is tricky because we have evaluations AFTER moves, not BEFORE.
    We need to infer what the engine would have recommended.
    
    Strategy:
    - Look at the eval before and after the played move
    - If we had stored the PV (principal variation), use the first move
    - Otherwise, we can try to reconstruct from the game state
    
    For now, this requires that the analysis data includes the best move.
    If not available, we return None.
    """
    # This would require engine access to compute best move
    # In the current setup, we rely on pre-computed analysis
    return None


# =============================================================================
# PUZZLE GENERATOR CLASS
# =============================================================================


@dataclass
class PuzzleGenerator:
    """
    Generates puzzles from analyzed game data.
    
    The generator is deterministic - given the same input,
    it will always produce the same output puzzles.
    """
    
    # Minimum eval loss to create puzzle
    min_eval_loss: int = MIN_PUZZLE_EVAL_LOSS
    
    # Include only positions with legal best move
    require_legal_best_move: bool = True
    
    def generate_from_game(
        self,
        game_index: int,
        move_evals: List[dict],
        focus_color: Optional[str] = None,
    ) -> List[Puzzle]:
        """
        Generate puzzles from a single analyzed game.
        
        Args:
            game_index: Index of the game (for puzzle_id generation)
            move_evals: List of move evaluation dictionaries from engine analysis
                Expected keys: san, cp_loss, phase, move_num, eval_before, eval_after, fen_before
            focus_color: If specified, only generate puzzles for this player's moves
        
        Returns:
            List of Puzzle objects
        """
        puzzles: List[Puzzle] = []
        
        # Track board state as we replay the game
        board = chess.Board()
        
        for idx, move_eval in enumerate(move_evals):
            san = move_eval.get("san") or ""
            cp_loss = int(move_eval.get("cp_loss") or 0)
            phase = move_eval.get("phase") or "middlegame"
            move_num = int(move_eval.get("move_num") or ((idx // 2) + 1))
            eval_before = move_eval.get("eval_before")
            eval_after = move_eval.get("eval_after")
            
            # Skip if doesn't meet threshold
            if cp_loss < self.min_eval_loss:
                # Push move and continue
                try:
                    move = board.parse_san(san)
                    board.push(move)
                except Exception:
                    pass
                continue
            
            # Determine side to move from board state
            side_to_move = "white" if board.turn == chess.WHITE else "black"
            
            # Filter by focus color if specified
            if focus_color and side_to_move != focus_color:
                try:
                    move = board.parse_san(san)
                    board.push(move)
                except Exception:
                    pass
                continue
            
            # Get FEN before the move (puzzle position)
            fen_before = board.fen()
            
            # Try to parse the played move
            try:
                played_move = board.parse_san(san)
            except Exception:
                continue
            
            # Generate best move from position
            # Since we don't have engine access here, we need to rely on
            # pre-computed best moves in the analysis data, OR use a heuristic
            best_move_san = move_eval.get("best_move_san") or move_eval.get("best_move")
            best_move_uci = move_eval.get("best_move_uci")
            
            # If best move not in data, try to find it via simple heuristics
            if not best_move_san:
                best_move_san = self._find_best_move_heuristic(board, played_move)
            
            if not best_move_san:
                # Can't determine best move, skip this puzzle
                try:
                    board.push(played_move)
                except Exception:
                    pass
                continue
            
            # Verify best move is legal
            if self.require_legal_best_move:
                try:
                    best_move = board.parse_san(best_move_san)
                    if best_move not in board.legal_moves:
                        board.push(played_move)
                        continue
                except Exception:
                    board.push(played_move)
                    continue
            
            # Classify puzzle type
            try:
                best_move_obj = board.parse_san(best_move_san)
                puzzle_type = _classify_puzzle_type(
                    board=board,
                    best_move=best_move_obj,
                    played_move=played_move,
                    eval_loss_cp=cp_loss,
                    phase=phase,
                    move_number=move_num,
                )
            except Exception:
                puzzle_type = PuzzleType.MISSED_TACTIC
            
            # Classify difficulty
            difficulty = classify_difficulty(
                fen=fen_before,
                best_move_san=best_move_san,
                eval_loss_cp=cp_loss,
                phase=phase,
            )
            
            # Generate puzzle ID
            puzzle_id = f"{game_index}_{move_num}_{side_to_move}"
            
            # Create puzzle
            puzzle = Puzzle(
                puzzle_id=puzzle_id,
                fen=fen_before,
                side_to_move=side_to_move,
                best_move_san=best_move_san,
                played_move_san=san,
                eval_loss_cp=cp_loss,
                phase=phase,
                puzzle_type=puzzle_type,
                difficulty=difficulty,
                source_game_index=game_index,
                move_number=move_num,
                eval_before=eval_before if isinstance(eval_before, int) else None,
                eval_after=eval_after if isinstance(eval_after, int) else None,
                best_move_uci=best_move_uci,
            )
            
            puzzles.append(puzzle)
            
            # Push the played move to continue
            try:
                board.push(played_move)
            except Exception:
                pass
        
        return puzzles
    
    def _find_best_move_heuristic(
        self,
        board: chess.Board,
        played_move: chess.Move,
    ) -> Optional[str]:
        """
        Attempt to find best move using heuristics when not provided.
        
        This is a fallback - ideally the analysis data includes best moves.
        
        Heuristics (in order of priority):
        1. Captures of undefended pieces
        2. Checks that win material
        3. Moves that defend hanging pieces
        
        Note: This is imperfect. Real puzzles should use engine-computed best moves.
        """
        # This is a simplified heuristic
        # For production, the analysis data should include engine's best move
        
        # Check for obvious captures of valuable pieces
        best_capture = None
        best_capture_value = 0
        
        piece_values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
            chess.KING: 0,  # Can't capture king
        }
        
        for move in board.legal_moves:
            if move == played_move:
                continue
            
            if board.is_capture(move):
                captured_piece = board.piece_at(move.to_square)
                if captured_piece:
                    value = piece_values.get(captured_piece.piece_type, 0)
                    moving_piece = board.piece_at(move.from_square)
                    moving_value = piece_values.get(moving_piece.piece_type, 0) if moving_piece else 0
                    
                    # Check if capture is safe (SEE approximation)
                    board_copy = board.copy()
                    board_copy.push(move)
                    is_recapturable = board_copy.is_attacked_by(board_copy.turn, move.to_square)
                    
                    if not is_recapturable or value > moving_value:
                        net_value = value - (moving_value if is_recapturable else 0)
                        if net_value > best_capture_value:
                            best_capture_value = net_value
                            best_capture = move
        
        if best_capture and best_capture_value >= 2:  # At least minor piece value
            return board.san(best_capture)
        
        # Check for checks that are safe
        for move in board.legal_moves:
            if board.gives_check(move):
                board_copy = board.copy()
                board_copy.push(move)
                moving_piece = board.piece_at(move.from_square)
                if moving_piece:
                    is_safe = not board_copy.is_attacked_by(board_copy.turn, move.to_square)
                    if is_safe:
                        return board.san(move)
        
        # Can't determine best move with simple heuristics
        return None


# =============================================================================
# MAIN GENERATION FUNCTION
# =============================================================================


def generate_puzzles_from_games(
    analyzed_games: List[dict],
    focus_player: Optional[str] = None,
    min_eval_loss: int = MIN_PUZZLE_EVAL_LOSS,
) -> List[Puzzle]:
    """
    Generate puzzles from multiple analyzed games.
    
    Main entry point for puzzle generation.
    
    Args:
        analyzed_games: List of analyzed game dictionaries.
            Expected format (from streamlit aggregated games):
            {
                "index": int,
                "moves_table": [
                    {
                        "ply": int,
                        "mover": "white"|"black",
                        "move_san": str,
                        "score_cp": int,
                        "cp_loss": int,
                        "phase": str,
                    }, ...
                ],
                "focus_color": "white"|"black"|None,
            }
        focus_player: Username to filter puzzles for (optional)
        min_eval_loss: Minimum centipawn loss to create puzzle
    
    Returns:
        List of Puzzle objects, sorted by game index and move number
    """
    generator = PuzzleGenerator(min_eval_loss=min_eval_loss)
    all_puzzles: List[Puzzle] = []
    
    for game in analyzed_games:
        game_index = game.get("index", 0)
        moves_table = game.get("moves_table") or []
        focus_color = game.get("focus_color")
        
        # Convert moves_table format to move_evals format
        move_evals = _convert_moves_table_to_evals(moves_table, focus_color)
        
        # Generate puzzles for this game
        game_puzzles = generator.generate_from_game(
            game_index=game_index,
            move_evals=move_evals,
            focus_color=focus_color,
        )
        
        all_puzzles.extend(game_puzzles)
    
    # Sort by game index, then move number
    all_puzzles.sort(key=lambda p: (p.source_game_index, p.move_number))
    
    return all_puzzles


def _convert_moves_table_to_evals(
    moves_table: List[dict],
    focus_color: Optional[str],
) -> List[dict]:
    """
    Convert Streamlit moves_table format to move_evals format expected by generator.
    
    The moves_table has entries for ALL moves (both sides).
    We need to preserve move order for board reconstruction.
    """
    move_evals: List[dict] = []
    prev_score_cp: Optional[int] = None
    
    for row in moves_table:
        mover = row.get("mover")
        ply = row.get("ply", 1)
        move_san = row.get("move_san") or ""
        score_cp = row.get("score_cp")
        cp_loss = row.get("cp_loss", 0)
        phase = row.get("phase", "middlegame")
        
        # Calculate move number from ply
        move_num = (ply + 1) // 2
        
        # Only include the cp_loss if this is focus player's move
        # but we still need all moves for board reconstruction
        effective_cp_loss = 0
        if focus_color is None or mover == focus_color:
            effective_cp_loss = cp_loss
        
        move_evals.append({
            "san": move_san,
            "cp_loss": effective_cp_loss,
            "phase": phase,
            "move_num": move_num,
            "eval_before": prev_score_cp,
            "eval_after": score_cp,
            "mover": mover,
        })
        
        prev_score_cp = score_cp
    
    return move_evals


# =============================================================================
# PUZZLE FILTERING UTILITIES
# =============================================================================


def filter_puzzles_by_difficulty(
    puzzles: List[Puzzle],
    difficulty: Difficulty,
) -> List[Puzzle]:
    """Filter puzzles to only include specific difficulty."""
    return [p for p in puzzles if p.difficulty == difficulty]


def filter_puzzles_by_type(
    puzzles: List[Puzzle],
    puzzle_type: PuzzleType,
) -> List[Puzzle]:
    """Filter puzzles to only include specific type."""
    return [p for p in puzzles if p.puzzle_type == puzzle_type]


def filter_puzzles_by_phase(
    puzzles: List[Puzzle],
    phase: str,
) -> List[Puzzle]:
    """Filter puzzles to only include specific game phase."""
    return [p for p in puzzles if p.phase == phase]


def get_puzzle_stats(puzzles: List[Puzzle]) -> dict:
    """Get statistics about a collection of puzzles."""
    if not puzzles:
        return {
            "total": 0,
            "by_difficulty": {},
            "by_type": {},
            "by_phase": {},
            "avg_eval_loss": 0,
        }
    
    by_difficulty = {}
    by_type = {}
    by_phase = {}
    total_eval_loss = 0
    
    for p in puzzles:
        # Count by difficulty
        diff_key = p.difficulty.value
        by_difficulty[diff_key] = by_difficulty.get(diff_key, 0) + 1
        
        # Count by type
        type_key = p.puzzle_type.value
        by_type[type_key] = by_type.get(type_key, 0) + 1
        
        # Count by phase
        by_phase[p.phase] = by_phase.get(p.phase, 0) + 1
        
        total_eval_loss += p.eval_loss_cp
    
    return {
        "total": len(puzzles),
        "by_difficulty": by_difficulty,
        "by_type": by_type,
        "by_phase": by_phase,
        "avg_eval_loss": round(total_eval_loss / len(puzzles), 1),
    }
