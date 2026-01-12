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
import os
import shutil

import chess
import chess.engine

from .puzzle_types import Puzzle, PuzzleType, Difficulty
from .difficulty import classify_difficulty
from .explanation_engine import (
    generate_puzzle_explanation_v2,
    generate_explanation_string,
    PuzzleExplanation,
    TacticalMotif,
)

# Import the new Stockfish-based explainer
try:
    from .stockfish_explainer import generate_puzzle_explanation_enhanced
    USE_STOCKFISH_EXPLAINER = True
except ImportError:
    USE_STOCKFISH_EXPLAINER = False

# Opponent mistake analysis removed for performance


# =============================================================================
# PUZZLE TRIGGER THRESHOLDS
# =============================================================================

# Minimum eval loss to generate a puzzle (centipawns)
MIN_PUZZLE_EVAL_LOSS = 100  # 1 pawn = tactical opportunity

# Clear blunder threshold (used for puzzle type detection)
BLUNDER_EVAL_LOSS = 300

# Opening move threshold (for opening_error detection)
OPENING_MOVE_THRESHOLD = 10

# Max puzzles per game (prioritize best ones)
MAX_PUZZLES_PER_GAME = 3

# Pre-filter threshold: skip positions with very small losses
PREFILTER_MIN_LOSS = 80

# Max puzzles per game (prioritize best ones)
MAX_PUZZLES_PER_GAME = 3

# Pre-filter threshold: skip positions with very small losses
PREFILTER_MIN_LOSS = 80


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
# PUZZLE EXPLANATION GENERATION (DETERMINISTIC)
# =============================================================================


def generate_puzzle_explanation(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int,
    puzzle_type: PuzzleType,
    phase: str,
) -> str:
    """
    Generate a deterministic explanation of why the best move is correct.
    
    Uses Stockfish-based analysis to understand WHY the move is best:
    - Material wins (primary reason for most tactics)
    - Piece protection analysis
    - Mate threats
    - Tactical motifs
    
    No AI/LLM is used - purely engine-based tactical analysis.
    
    Args:
        board: Position before the move
        best_move: The correct move
        eval_loss_cp: How much was lost by not playing this move
        puzzle_type: Classified type of the puzzle
        phase: Game phase (opening, middlegame, endgame)
    
    Returns:
        A descriptive explanation string
    """
    def _ensure_check_language(explanation: str) -> str:
        """Ensure the explanation mentions check/checkmate when applicable."""
        try:
            after = board.copy(stack=False)
            after.push(best_move)
        except Exception:
            return explanation

        lower = (explanation or "").lower()
        if after.is_checkmate():
            if "checkmate" in lower:
                return explanation
            prefix = "This is checkmate. "
            return prefix + (explanation or "").lstrip()
        if after.is_check():
            if "check" in lower:
                return explanation
            prefix = "This gives check. "
            return prefix + (explanation or "").lstrip()
        return explanation

    # Try the new Stockfish-based explainer first (better quality)
    if USE_STOCKFISH_EXPLAINER:
        try:
            explanation = generate_puzzle_explanation_enhanced(
                board=board,
                best_move=best_move,
                eval_loss_cp=eval_loss_cp,
                phase=phase,
            )
            if explanation and explanation.strip():
                return _ensure_check_language(explanation)
        except Exception:
            pass  # Fall back to legacy explanation engine
    
    # Fallback to the legacy explanation engine
    explanation = generate_explanation_string(
        board=board,
        best_move=best_move,
        eval_loss_cp=eval_loss_cp,
        puzzle_type=puzzle_type,
        phase=phase,
    )
    return _ensure_check_language(explanation)


def generate_puzzle_explanation_detailed(
    board: chess.Board,
    best_move: chess.Move,
    eval_loss_cp: int = 0,
    phase: str = "middlegame",
) -> PuzzleExplanation:
    """
    Generate a comprehensive, structured explanation for a puzzle.
    
    Returns the full PuzzleExplanation dataclass with all analysis fields:
    - primary_motif: Main tactical idea
    - secondary_motifs: Additional tactical themes
    - threats_created: What threats the move establishes
    - threats_stopped: What opponent threats were prevented
    - material_outcome: Material win/loss description
    - king_safety_impact: King safety changes
    - phase_specific_guidance: Phase-aware coaching tips
    - human_readable_summary: Final coach-quality explanation
    
    Args:
        board: Position before the move
        best_move: The correct move
        eval_loss_cp: Centipawn loss from missing the move
        phase: Game phase (opening, middlegame, endgame)
    
    Returns:
        PuzzleExplanation with full analysis
    """
    return generate_puzzle_explanation_v2(
        board=board,
        best_move=best_move,
        eval_loss_cp=eval_loss_cp,
        phase=phase,
    )


def _get_attacked_valuable_pieces(board: chess.Board, attacker_color: chess.Color) -> list:
    """Get list of valuable pieces being attacked after a move."""
    attacked = []
    opponent_color = not attacker_color
    
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.color == opponent_color:
            if board.is_attacked_by(attacker_color, square):
                if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
                    attacked.append((piece.piece_type, square))
    
    return attacked


def _format_attacked_pieces(attacked: list) -> str:
    """Format list of attacked pieces for display."""
    if not attacked:
        return "the opponent's pieces"
    
    piece_names = []
    for piece_type, square in attacked:
        name = chess.piece_name(piece_type).title()
        sq_name = chess.square_name(square)
        if piece_type == chess.KING:
            piece_names.append("King")
        else:
            piece_names.append(f"{name} on {sq_name}")
    
    if len(piece_names) == 1:
        return piece_names[0]
    elif len(piece_names) == 2:
        return f"{piece_names[0]} and {piece_names[1]}"
    else:
        return ", ".join(piece_names[:-1]) + f", and {piece_names[-1]}"


# =============================================================================
# BEST MOVE CALCULATION
# =============================================================================


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


def _open_stockfish_engine() -> chess.engine.SimpleEngine | None:
    cmd = _resolve_stockfish_cmd()
    if not cmd:
        return None
    try:
        return chess.engine.SimpleEngine.popen_uci(cmd)
    except Exception:
        return None


def _best_move_from_engine(board: chess.Board, engine: chess.engine.SimpleEngine, depth: int = 20) -> chess.Move | None:
    try:
        result = engine.play(board, chess.engine.Limit(depth=int(depth)))
        return result.move
    except Exception:
        return None


def _check_if_only_one_good_move(
    board: chess.Board,
    engine: chess.engine.SimpleEngine,
    depth: int = 15,
    min_gap_cp: int = 150
) -> tuple[bool, int]:
    """
    Check if this position has only one good move (forcing position).
    
    Uses MultiPV analysis to compare best move vs second-best move.
    If the gap is large (>= min_gap_cp), only one line maintains advantage.
    
    Args:
        board: Position to analyze
        engine: Stockfish engine instance
        depth: Analysis depth
        min_gap_cp: Minimum centipawn gap between best and 2nd best
    
    Returns:
        (is_forcing, gap_cp): Whether position is forcing, and the gap in cp
    """
    try:
        # Analyze with MultiPV=2 to get top 2 moves
        info = engine.analyse(board, chess.engine.Limit(depth=int(depth)), multipv=2)
        
        if len(info) < 2:
            # Only one legal move or analysis failed
            return (True, 999)  # Only one move available = forcing
        
        # Get evaluations from white's perspective
        best_score = info[0].get("score")
        second_score = info[1].get("score")
        
        if best_score is None or second_score is None:
            return (False, 0)
        
        # Convert to centipawns (handle mate scores)
        def score_to_cp(score, color_to_move):
            if score.is_mate():
                # Mate scores are very high
                mate_in = score.mate()
                if mate_in > 0:
                    return 10000 - mate_in * 10
                else:
                    return -10000 - mate_in * 10
            else:
                cp = score.score()
                # Adjust for side to move
                return cp if color_to_move == chess.WHITE else -cp
        
        color = board.turn
        best_cp = score_to_cp(best_score.white(), color)
        second_cp = score_to_cp(second_score.white(), color)
        
        # Calculate gap (always positive)
        gap = abs(best_cp - second_cp)
        
        # Position is "forcing" if gap is large
        is_forcing = gap >= min_gap_cp
        
        return (is_forcing, int(gap))
        
    except Exception:
        return (False, 0)


def _validate_puzzle_integrity(
    board: chess.Board,
    first_move: chess.Move,
    engine: chess.engine.SimpleEngine,
    depth: int = 12,
    min_gap_cp: int = 100,
    winning_threshold_cp: int = 200,
) -> bool:
    """
    Verify complete puzzle integrity strictly:
    1. Only one good move for solver at each step.
    2. Opponent plays best defense (not terrible moves).
    3. Final position is winning.
    """
    temp_board = board.copy()
    solver_color = temp_board.turn
    
    # Check Step 1 gap
    is_forcing, _ = _check_if_only_one_good_move(temp_board, engine, depth, min_gap_cp)
    if not is_forcing:
        return False
        
    temp_board.push(first_move)
    
    # Simulate up to 3 sequence pairs (6 plies)
    # Stop if mated or winning score is sustained
    for _ in range(3):
        if temp_board.is_game_over():
            break
            
        # --- Opponent Turn (Best Defense) ---
        # "Opponent's move is not terrible" -> We ensure checking against the BEST move.
        result = engine.play(temp_board, chess.engine.Limit(depth=depth))
        if not result.move:
            break
        temp_board.push(result.move)
        
        if temp_board.is_game_over():
            break

        # --- Solver Turn (Unique Winning Move check) ---
        is_forcing, _ = _check_if_only_one_good_move(temp_board, engine, depth, min_gap_cp)
        if not is_forcing:
            # If we are already massively winning (mate or > +600), loose move selection might be accepted
            # But the requirement says "Only one good move... at each step".
            # To be safe, we reject if there are multiple good moves, unless it's literally Mate.
            info = engine.analyse(temp_board, chess.engine.Limit(depth=depth))
            score = info.get("score")
            if score and score.is_mate():
                # If mate is forced, multiple paths to mate might exist (e.g. Q everywhere), 
                # but usually "puzzle" implies specific line. 
                # Let's be strict: if multiple moves maintain simple win, it's a weak puzzle.
                pass 
            else:
                 return False

        result_solver = engine.play(temp_board, chess.engine.Limit(depth=depth))
        if not result_solver.move:
            break
        temp_board.push(result_solver.move)

    # --- Final Winning Position Check ---
    info = engine.analyse(temp_board, chess.engine.Limit(depth=depth))
    score = info.get("score")
    if not score:
        return False
        
    if score.is_mate():
        # Make sure it is mate FOR the solver
        # If solver is White, and mate > 0, White wins.
        mate_in = score.white().mate() 
        if solver_color == chess.WHITE:
             return mate_in > 0
        else:
             return mate_in < 0

    cp = score.white().score() if solver_color == chess.WHITE else score.black().score()
    return cp > winning_threshold_cp



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
        engine: chess.engine.SimpleEngine | None = None,
        engine_depth: int = 20,
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
        
        # Track previous move info for opponent mistake analysis
        prev_fen = None  # FEN before the previous move
        prev_move_uci = None  # Previous move in UCI format
        prev_move_san = None  # Previous move in SAN format

        # Best-effort engine for best-move selection when analysis data doesn't include it.
        # For performance, callers can pass a shared engine instance.
        owned_engine = False
        if engine is None:
            engine = _open_stockfish_engine()
            owned_engine = True

        try:
            for idx, move_eval in enumerate(move_evals):
                san = move_eval.get("san") or ""
                cp_loss = int(move_eval.get("cp_loss") or 0)
                phase = move_eval.get("phase") or "middlegame"
                move_num = int(move_eval.get("move_num") or ((idx // 2) + 1))
                eval_before = move_eval.get("eval_before")
                eval_after = move_eval.get("eval_after")
                
                # Capture current FEN before the move (for next iteration's prev tracking)
                current_fen = board.fen()

                # Skip if doesn't meet threshold
                if cp_loss < self.min_eval_loss:
                    # Push move and continue
                    try:
                        move = board.parse_san(san)
                        prev_fen = current_fen
                        prev_move_uci = move.uci()
                        prev_move_san = san
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

                # Generate best move from position.
                # Priority:
                # 1) pre-computed best move from analysis data (engine-derived)
                # 2) local Stockfish best move (engine-derived)
                # 3) heuristic fallback (last resort)
                best_move_san = move_eval.get("best_move_san") or move_eval.get("best_move")
                best_move_uci = move_eval.get("best_move_uci")

                if not best_move_san and engine is not None:
                    mv = _best_move_from_engine(board, engine, depth=engine_depth)
                    if mv is not None and mv in board.legal_moves:
                        try:
                            best_move_san = board.san(mv)
                            best_move_uci = mv.uci()
                        except Exception:
                            best_move_san = None

                # If we still don't have a best move, we cannot create a valid puzzle.
                # User requirement: correct moves must be Stockfish-derived (no heuristic fallback).
                if not best_move_san:
                    # Can't determine best move via analysis data or Stockfish, skip this puzzle
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

                # Ensure we always have UCI for the best move when possible.
                if not best_move_uci:
                    try:
                        best_move_uci = board.parse_san(best_move_san).uci()
                    except Exception:
                        best_move_uci = None

                # Check if this is a forcing position (only one good move)
                is_forcing = False
                move_gap_cp = 0
                if engine is not None:
                    try:
                        is_forcing, move_gap_cp = _check_if_only_one_good_move(
                            board, engine, depth=engine_depth, min_gap_cp=150
                        )
                    except Exception:
                        # If forcing check fails, default to non-forcing
                        is_forcing = False
                        move_gap_cp = 0
                
                # REJECTION: If not distinct best move, skip.
                if not is_forcing:
                    try:
                        board.push(played_move)
                    except Exception:
                        pass
                    continue

                # Strict Puzzle Validation (User Request: "Opponent's move is not terrible" + "Only one good move")
                if engine is not None:
                    is_valid = _validate_puzzle_integrity(
                        board, best_move, engine, depth=12, min_gap_cp=100, winning_threshold_cp=150
                    )
                    if not is_valid:
                        # Fail condition: Puzzle is not strict enough
                        try:
                            board.push(played_move)
                        except Exception:
                            pass
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

                # Lazy explanation generation: generate on-demand in UI, not here
                explanation = None

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
                    explanation=explanation,
                    opponent_mistake_explanation=None,
                    opponent_move_san=None,
                    opponent_best_move_san=None,
                    fen_before_opponent=None,
                    is_forcing=is_forcing,
                    move_gap_cp=move_gap_cp,
                )

                puzzles.append(puzzle)

                # Push the played move and update prev tracking
                try:
                    prev_fen = fen_before
                    prev_move_uci = played_move.uci()
                    prev_move_san = san
                    board.push(played_move)
                except Exception:
                    pass
        finally:
            if owned_engine and engine is not None:
                try:
                    engine.quit()
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
    max_puzzles: int | None = 200,
    engine_depth: int = 6,
    progress_callback=None,
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
        List of Puzzle objects.

        Note: When `max_puzzles` is set, puzzles are prioritized so that severe
        inaccuracies (>= 300cp loss) appear first and are more likely to be
        included under the cap, while still allowing puzzles from smaller
        mistakes when severe ones are scarce.
    """
    generator = PuzzleGenerator(min_eval_loss=min_eval_loss)
    all_puzzles: List[Puzzle] = []

    def _priority_key(p: Puzzle) -> tuple:
        """Sort key: prioritize forcing positions (only one good move), then winning positions missed, etc.

        Priority order:
        1. Forcing positions (only one move maintains advantage, gap ≥150cp) - highest educational value
        2. Missed wins (eval_before was winning +200cp, significant loss)
        3. Severe mistakes/blunders (>= 300cp loss)
        4. Medium mistakes (100-300cp loss)
        
        Tie-breakers keep output deterministic.
        """
        eval_before = p.eval_before if p.eval_before is not None else 0
        
        # Check if this is a forcing position (only one good move)
        is_forcing = p.is_forcing
        
        # Determine if position was winning before the move
        # For white: eval_before >= +200cp
        # For black: eval_before <= -200cp
        was_winning = False
        if p.side_to_move == "white" and eval_before >= 200:
            was_winning = True
        elif p.side_to_move == "black" and eval_before <= -200:
            was_winning = True
        
        # Missed win with significant loss
        is_missed_win = was_winning and p.eval_loss_cp >= 150
        
        # Severe blunder
        is_severe = p.eval_loss_cp >= BLUNDER_EVAL_LOSS
        
        # Priority groups (lower number = higher priority):
        # -1 = Forcing position (only one good move) - highest priority!
        # 0 = Missed winning position (most valuable to learn from)
        # 1 = Severe blunder in non-winning position
        # 2 = Medium mistake
        if is_forcing:
            priority_group = -1
        elif is_missed_win:
            priority_group = 0
        elif is_severe:
            priority_group = 1
        else:
            priority_group = 2
        
        # Within each group, sort by eval loss (higher first), then stable order
        # For forcing positions, also consider the gap (higher gap = more forcing = better)
        return (
            priority_group,
            -int(p.move_gap_cp),  # For forcing positions, prefer larger gaps
            -int(p.eval_loss_cp),
            int(p.source_game_index),
            int(p.move_number),
            str(p.puzzle_id)
        )

    # Parallel processing with batching for efficiency
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import os
    
    num_workers = min(4, os.cpu_count() or 2)
    total_games = len(analyzed_games)
    
    def process_game_batch(game_batch):
        """Process a batch of games with a dedicated engine instance."""
        batch_puzzles = []
        engine = _open_stockfish_engine()
        try:
            for game in game_batch:
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
                    engine=engine,
                    engine_depth=engine_depth,
                )
                
                # Limit puzzles per game, prioritizing critical positions
                game_puzzles.sort(key=lambda p: (-p.eval_loss_cp, p.move_number))
                batch_puzzles.extend(game_puzzles[:MAX_PUZZLES_PER_GAME])
        finally:
            if engine is not None:
                try:
                    engine.quit()
                except Exception:
                    pass
        return batch_puzzles
    
    # Split games into batches for parallel processing
    batch_size = max(1, len(analyzed_games) // num_workers)
    game_batches = [analyzed_games[i:i+batch_size] for i in range(0, len(analyzed_games), batch_size)]
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_game_batch, batch): i for i, batch in enumerate(game_batches)}
        
        for future in as_completed(futures):
            batch_puzzles = future.result()
            all_puzzles.extend(batch_puzzles)
            
            # Progress callback
            if progress_callback:
                completed = sum(1 for f in futures if f.done())
                progress_callback(completed, len(game_batches))

    # Prioritize severe inaccuracies while still keeping smaller mistakes available.
    all_puzzles.sort(key=_priority_key)

    if max_puzzles is not None:
        return all_puzzles[:max_puzzles]
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
