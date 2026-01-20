from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import concurrent.futures

import chess
import chess.engine
import os
import streamlit as st

from puzzles.puzzle_store import PuzzleDefinition
from puzzles.solution_line import compute_solution_line
from puzzles.global_puzzle_store import record_puzzle_rating, get_user_rated_keys
from ui.chessboard_component import render_chessboard

# Stockfish path (shared with the main analyzer when available)
try:
    from src.engine_analysis import STOCKFISH_PATH
except Exception:
    STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"


# Piece values and names for explanations
PIECE_POINTS = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}


@dataclass
class PuzzleProgress:
    current_index: int = 0
    solved: int = 0
    last_result: Optional[str] = None  # "correct" | "viable" | "incorrect" | "continue" | None
    last_uci: Optional[str] = None
    current_fen: Optional[str] = None  # tracks accepted position
    active_puzzle_index: Optional[int] = None
    # Multi-move puzzle tracking
    solution_move_index: int = 0  # Which player move we're on (0, 2, 4, ...)
    opponent_just_moved: bool = False  # True if we just auto-played opponent's move
    opponent_last_uci: Optional[str] = None  # Track opponent's last move for highlighting
    # Dynamic solution line (allows alternate-but-viable moves)
    active_solution_moves: Optional[List[str]] = None

    # Reveal-answer UI state
    reveal_answer: bool = False
    reveal_puzzle_index: Optional[int] = None
    reveal_solution_move_index: Optional[int] = None

    # UI nonce to force-remount the chessboard component when needed
    # (prevents stale component outputs being processed as moves on rerun).
    board_nonce: int = 0


_STATE_KEY = "puzzle_progress_v2"
_SOLUTION_CACHE_KEY = "puzzle_solution_line_cache_v2"
_SOLUTION_FUTURES_KEY = "puzzle_solution_line_futures_v1"
_SOLUTION_EXECUTOR_KEY = "puzzle_solution_line_executor_v1"
_PERSISTENT_ENGINE_KEY = "puzzle_persistent_stockfish_engine"

# Keep puzzle analysis depth moderate for speed vs accuracy
PUZZLE_SOLUTION_ANALYSIS_DEPTH = 15

# Use a lower depth for interactive move classification (much faster)
PUZZLE_CLASSIFICATION_DEPTH = 12


def _get_persistent_engine() -> Optional[chess.engine.SimpleEngine]:
    """Get or create a persistent Stockfish engine for fast puzzle analysis."""
    if _PERSISTENT_ENGINE_KEY not in st.session_state:
        st.session_state[_PERSISTENT_ENGINE_KEY] = None
    
    engine = st.session_state[_PERSISTENT_ENGINE_KEY]
    
    # Check if engine is still alive
    if engine is not None:
        try:
            # Quick ping to see if engine is responsive
            engine.ping()
            return engine
        except Exception:
            # Engine died, clean up
            try:
                engine.quit()
            except Exception:
                pass
            st.session_state[_PERSISTENT_ENGINE_KEY] = None
    
    # Create new engine
    try:
        if os.path.exists(STOCKFISH_PATH):
            engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        else:
            engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        st.session_state[_PERSISTENT_ENGINE_KEY] = engine
        return engine
    except Exception:
        return None


def _is_persistent_engine(engine: chess.engine.SimpleEngine) -> bool:
    """Check if this engine is the persistent one (should not be closed)."""
    persistent = st.session_state.get(_PERSISTENT_ENGINE_KEY)
    return persistent is not None and engine is persistent


def _maybe_quit_engine(engine: chess.engine.SimpleEngine) -> None:
    """Quit engine only if it's not the persistent one."""
    if not _is_persistent_engine(engine):
        try:
            engine.quit()
        except Exception:
            pass


def _get_progress() -> PuzzleProgress:
    if _STATE_KEY not in st.session_state or not isinstance(
        st.session_state[_STATE_KEY], PuzzleProgress
    ):
        st.session_state[_STATE_KEY] = PuzzleProgress()
    return st.session_state[_STATE_KEY]


def _reset_progress() -> None:
    st.session_state[_STATE_KEY] = PuzzleProgress()


def _get_solution_cache() -> dict[tuple[str, str, int], List[str]]:
    cache = st.session_state.get(_SOLUTION_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_SOLUTION_CACHE_KEY] = cache
    return cache


def _get_solution_futures() -> dict[tuple[str, str, int], concurrent.futures.Future]:
    futs = st.session_state.get(_SOLUTION_FUTURES_KEY)
    if not isinstance(futs, dict):
        futs = {}
        st.session_state[_SOLUTION_FUTURES_KEY] = futs
    return futs


def _get_solution_executor() -> concurrent.futures.ThreadPoolExecutor:
    ex = st.session_state.get(_SOLUTION_EXECUTOR_KEY)
    if not isinstance(ex, concurrent.futures.ThreadPoolExecutor):
        # One worker: Stockfish is CPU-heavy; keep UI responsive.
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        st.session_state[_SOLUTION_EXECUTOR_KEY] = ex
    return ex


def _get_supabase_solution_cache() -> dict[str, list[str]]:
    """Get or create the Supabase solution cache for this session."""
    key = "_supabase_solution_cache"
    if key not in st.session_state:
        st.session_state[key] = {}
    return st.session_state[key]


def _try_fetch_cached_solution(puzzle_key: str) -> list[str] | None:
    """Try to fetch solution from Supabase cache."""
    sb_cache = _get_supabase_solution_cache()
    
    # Already fetched this session
    if puzzle_key in sb_cache:
        return sb_cache[puzzle_key] if sb_cache[puzzle_key] else None
    
    # Try Supabase
    try:
        from puzzles.global_supabase_store import get_cached_solution_line
        solution = get_cached_solution_line(puzzle_key)
        if solution:
            sb_cache[puzzle_key] = solution
            return solution
        sb_cache[puzzle_key] = []  # Mark as checked (no solution stored)
    except Exception:
        pass
    return None


def _save_solution_to_supabase(puzzle_key: str, solution_line: list[str]) -> None:
    """Save computed solution to Supabase for future users."""
    if not puzzle_key or not solution_line:
        return
    try:
        from puzzles.global_supabase_store import save_solution_line
        save_solution_line(puzzle_key, solution_line)
        # Update local cache
        sb_cache = _get_supabase_solution_cache()
        sb_cache[puzzle_key] = solution_line
    except Exception:
        pass


def _schedule_solution_line(fen: str, first_uci: str, *, depth: int, puzzle_key: str = None) -> None:
    """Schedule solution-line computation in background if not cached."""
    if not fen or not first_uci:
        return

    cache = _get_solution_cache()
    futs = _get_solution_futures()
    key = (fen, first_uci, int(depth))

    # Already computed locally
    if key in cache:
        return
    
    # Check Supabase cache first (fast network fetch vs slow Stockfish)
    if puzzle_key:
        cached = _try_fetch_cached_solution(puzzle_key)
        if cached:
            cache[key] = cached
            return

    # Already running
    fut = futs.get(key)
    if isinstance(fut, concurrent.futures.Future) and not fut.done():
        return

    # Schedule computation with puzzle_key for saving later
    ex = _get_solution_executor()
    futs[key] = ex.submit(
        _compute_and_cache_solution,
        fen,
        first_uci,
        6,
        int(depth),
        puzzle_key,
    )


def _compute_and_cache_solution(fen: str, first_uci: str, max_depth: int, analysis_depth: int, puzzle_key: str = None) -> list[str]:
    """Compute solution and optionally save to Supabase."""
    solution = compute_solution_line(fen, first_uci, max_depth, analysis_depth)
    
    # Save to Supabase for future users
    if puzzle_key and solution:
        try:
            from puzzles.global_supabase_store import save_solution_line
            save_solution_line(puzzle_key, solution)
        except Exception:
            pass
    
    return solution


def _harvest_solution_line(fen: str, first_uci: str, *, depth: int, wait: bool = False, puzzle_key: str = None) -> None:
    """Move completed background computation into the in-memory cache.
    
    If wait=True, will block up to 5 seconds for the computation to complete.
    """
    if not fen or not first_uci:
        return

    cache = _get_solution_cache()
    futs = _get_solution_futures()
    key = (fen, first_uci, int(depth))
    if key in cache:
        return
    
    # Check Supabase cache if we have puzzle_key
    if puzzle_key:
        cached = _try_fetch_cached_solution(puzzle_key)
        if cached:
            cache[key] = cached
            return

    fut = futs.get(key)
    if not isinstance(fut, concurrent.futures.Future):
        return
    
    # Optionally wait for computation to finish
    if wait and not fut.done():
        try:
            fut.result(timeout=5.0)  # Wait up to 5 seconds
        except Exception:
            pass
    
    if not fut.done():
        return

    try:
        cache[key] = fut.result()
    except Exception:
        cache[key] = [first_uci]
    finally:
        try:
            del futs[key]
        except Exception:
            pass


def _reset_puzzle_progress(progress: PuzzleProgress, puzzle_fen: str) -> None:
    """Reset progress for a new puzzle."""
    progress.last_result = None
    progress.last_uci = None
    progress.opponent_last_uci = None
    progress.current_fen = puzzle_fen
    progress.solution_move_index = 0
    progress.opponent_just_moved = False
    progress.active_solution_moves = None
    progress.reveal_answer = False
    progress.reveal_puzzle_index = None
    progress.reveal_solution_move_index = None
    progress.board_nonce = 0


def _render_puzzle_nav_buttons(progress: PuzzleProgress, total_puzzles: int, puzzle: "PuzzleDefinition") -> None:
    """Render navigation and rating buttons with smooth styling."""
    from puzzles.global_puzzle_store import record_puzzle_rating, get_user_rated_keys
    
    # Inject smooth button styling
    st.markdown("""
<style>
/* Smooth puzzle buttons */
.puzzle-buttons-container button {
    height: 48px !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
}
.puzzle-buttons-container button:hover:not(:disabled) {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(0,0,0,0.15) !important;
}
.puzzle-buttons-container button:active:not(:disabled) {
    transform: translateY(0) !important;
}
.puzzle-buttons-container button:disabled {
    opacity: 0.5 !important;
}
</style>
""", unsafe_allow_html=True)
    
    # Get puzzle key for rating
    puzzle_key = (
        getattr(puzzle, "puzzle_key", None)
        or getattr(puzzle, "puzzle_id", None)
        or f"index_{progress.current_index}"
    )
    
    # Get rater info
    user = st.session_state.get("user")
    if user and user.get("id"):
        rater = user.get("id")
    else:
        rater = (st.session_state.get("puzzle_rater") or "").strip() or None
    
    # Initialize rating state
    if "puzzle_rated_keys" not in st.session_state:
        try:
            rated = get_user_rated_keys(rater)
        except Exception:
            rated = set()
        st.session_state["puzzle_rated_keys"] = set(rated)
    
    rated = st.session_state.get("puzzle_rated_keys")
    if not isinstance(rated, set):
        rated = set(rated) if isinstance(rated, list) else set()
        st.session_state["puzzle_rated_keys"] = rated
    
    last_rating_map = st.session_state.get("puzzle_last_rating")
    if not isinstance(last_rating_map, dict):
        last_rating_map = {}
        st.session_state["puzzle_last_rating"] = last_rating_map
    
    already_rated = puzzle_key in rated
    
    st.markdown('<div class="puzzle-buttons-container">', unsafe_allow_html=True)
    
    # Show rating status if already rated
    if already_rated:
        prev = last_rating_map.get(puzzle_key)
        if prev:
            st.caption(f"✓ Rated: {prev}")
    
    # Rating buttons row
    st.caption("Rate this puzzle:")
    r1, r2, r3 = st.columns(3, gap="small")
    with r1:
        dislike_clicked = st.button("👎", type="secondary", disabled=already_rated, use_container_width=True, key=f"rate_dislike_{puzzle_key}", help="Dislike")
    with r2:
        meh_clicked = st.button("😐", type="secondary", disabled=already_rated, use_container_width=True, key=f"rate_meh_{puzzle_key}", help="Meh")
    with r3:
        like_clicked = st.button("👍", type="secondary", disabled=already_rated, use_container_width=True, key=f"rate_like_{puzzle_key}", help="Like")
    
    # Handle rating clicks
    if not already_rated:
        if dislike_clicked:
            record_puzzle_rating(puzzle_key=str(puzzle_key), rating="dislike", rater=rater)
            st.session_state["puzzle_rated_keys"].add(puzzle_key)
            st.session_state["puzzle_last_rating"][puzzle_key] = "👎"
            st.toast("Rating saved!")
            st.rerun()
        elif meh_clicked:
            record_puzzle_rating(puzzle_key=str(puzzle_key), rating="meh", rater=rater)
            st.session_state["puzzle_rated_keys"].add(puzzle_key)
            st.session_state["puzzle_last_rating"][puzzle_key] = "😐"
            st.toast("Rating saved!")
            st.rerun()
        elif like_clicked:
            record_puzzle_rating(puzzle_key=str(puzzle_key), rating="like", rater=rater)
            st.session_state["puzzle_rated_keys"].add(puzzle_key)
            st.session_state["puzzle_last_rating"][puzzle_key] = "👍"
            st.toast("Rating saved!")
            st.rerun()
    
    # Navigation buttons row
    st.caption("Navigation:")
    nav1, nav2, nav3 = st.columns(3, gap="small")
    with nav1:
        if st.button("⬅️ Back", use_container_width=True, disabled=progress.current_index <= 0, key="puzzle_nav_back"):
            progress.current_index = max(progress.current_index - 1, 0)
            st.rerun()
    with nav2:
        if st.button("➡️ Next", use_container_width=True, disabled=progress.current_index >= total_puzzles - 1, type="primary", key="puzzle_nav_next"):
            progress.current_index = min(progress.current_index + 1, total_puzzles - 1)
            st.rerun()
    with nav3:
        if st.button("🔄 Reset", use_container_width=True, key="puzzle_nav_reset"):
            _reset_progress()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _open_stockfish_engine() -> chess.engine.SimpleEngine:
    """Open Stockfish - prefer persistent engine for speed."""
    # Try to use persistent engine first
    engine = _get_persistent_engine()
    if engine is not None:
        return engine
    # Fallback to new engine
    if os.path.exists(STOCKFISH_PATH):
        return chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    return chess.engine.SimpleEngine.popen_uci("stockfish")


def _score_to_cp(score: chess.engine.PovScore) -> int:
    """Convert a score to centipawns; mate is mapped to a large value."""
    try:
        cp = score.score(mate_score=100000)
        return int(cp) if cp is not None else 0
    except Exception:
        return 0


# Constants for move classification
VIABLE_CPL_THRESHOLD = 50  # 50 centipawns = 0.5 pawns


def _get_acceptable_moves_uci(
    board: chess.Board,
    second_best_max_loss_cp: int = 50,
    depth: int = 20,
) -> List[str]:
    """Return acceptable UCI moves using best + (maybe) second-best.

    Stockfish supports MultiPV output (multiple principal variations). We request
    `multipv=2` and accept the 2nd-best move only if it's within
    `second_best_max_loss_cp` centipawns of the best move for the side to move.

    Note: "0.5" is interpreted as 0.5 pawn = 50 centipawns.
    """
    engine = _open_stockfish_engine()
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
        if not isinstance(infos, list):
            infos = [infos]

        scored: List[tuple[str, int]] = []
        for info in infos:
            pv = info.get("pv")
            if not pv:
                continue
            mv = pv[0]
            score = info.get("score")
            if score is None:
                continue
            uci = mv.uci()
            cp = _score_to_cp(score.pov(board.turn))
            scored.append((uci, cp))

        # Ensure deterministic + unique ordering by score desc, then uci.
        scored_sorted = sorted(scored, key=lambda t: (-t[1], t[0]))
        unique: List[tuple[str, int]] = []
        seen: set[str] = set()
        for uci, cp in scored_sorted:
            if uci in seen:
                continue
            seen.add(uci)
            unique.append((uci, cp))
            if len(unique) >= 2:
                break

        if not unique:
            best = engine.play(board, chess.engine.Limit(depth=depth)).move
            return [best.uci()] if best else []

        best_uci, best_cp = unique[0]
        if len(unique) == 1:
            return [best_uci]

        second_uci, second_cp = unique[1]
        if (best_cp - second_cp) <= second_best_max_loss_cp:
            return [best_uci, second_uci]
        return [best_uci]
    finally:
        _maybe_quit_engine(engine)


def _classify_move(
    board: chess.Board,
    move_uci: str,
    expected_uci: Optional[str],
    depth: int = PUZZLE_CLASSIFICATION_DEPTH,
) -> tuple[str, int, Optional[str]]:
    """
    Classify a move as 'correct', 'viable', or 'incorrect'.
    
    Returns: (classification, cpl, why_not_optimal)
    - 'correct': Best move or equal to best (why_not_optimal is None)
    - 'viable': Within 50 CPL of best (show yellow, includes why not optimal)
    - 'incorrect': More than 50 CPL worse than best
    """
    # If it's the expected move, it's correct
    if move_uci == expected_uci:
        return ('correct', 0, None)
    
    engine = _open_stockfish_engine()
    try:
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=5)
        if not isinstance(infos, list):
            infos = [infos]
        
        if not infos:
            return ('incorrect', 100, None)
        
        # Get best move's eval and the best move itself
        best_info = infos[0]
        best_score = best_info.get("score")
        if not best_score:
            return ('incorrect', 100, None)
        
        best_cp = _score_to_cp(best_score.pov(board.turn))
        best_pv = best_info.get("pv", [])
        best_uci = best_pv[0].uci() if best_pv else None
        best_move = best_pv[0] if best_pv else None
        
        # If our move is the best move, it's correct
        if move_uci == best_uci:
            return ('correct', 0, None)
        
        # Find our move in multipv
        for info in infos:
            pv = info.get("pv", [])
            if pv and pv[0].uci() == move_uci:
                score = info.get("score")
                if score:
                    move_cp = _score_to_cp(score.pov(board.turn))
                    cpl = best_cp - move_cp
                    if cpl <= VIABLE_CPL_THRESHOLD:
                        # Generate why not optimal
                        why_not = _explain_why_not_optimal(board, move_uci, best_move)
                        return ('viable', max(0, cpl), why_not)
                    return ('incorrect', max(0, cpl), None)
        
        # Move not in top 5 - analyze specifically
        try:
            move = chess.Move.from_uci(move_uci)
            if move in board.legal_moves:
                board_after = board.copy()
                board_after.push(move)
                info = engine.analyse(board_after, chess.engine.Limit(depth=depth))
                score = info.get("score")
                if score:
                    # Score is from opponent's perspective after our move
                    move_cp = -_score_to_cp(score.pov(board_after.turn))
                    cpl = best_cp - move_cp
                    if cpl <= VIABLE_CPL_THRESHOLD:
                        why_not = _explain_why_not_optimal(board, move_uci, best_move)
                        return ('viable', max(0, cpl), why_not)
                    return ('incorrect', max(0, cpl), None)
        except Exception:
            pass
        
        return ('incorrect', 100, None)
        
    finally:
        _maybe_quit_engine(engine)


def _explain_why_not_optimal(board: chess.Board, 
                              played_uci: str,
                              best_move: Optional[chess.Move]) -> Optional[str]:
    """Explain why a viable move isn't the optimal choice."""
    if not best_move:
        return "The best move is more precise."
    
    try:
        played_move = chess.Move.from_uci(played_uci)
        best_piece = board.piece_at(best_move.from_square)
        played_piece = board.piece_at(played_move.from_square)
        
        if not best_piece or not played_piece:
            return "The best move is more forcing."
        
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
        
        return "The best move is more forcing."
        
    except Exception:
        return "The best move is more precise."


def _get_player_move_indices(solution_moves: List[str]) -> List[int]:
    """Get indices of player moves in solution (0, 2, 4, ...)."""
    return list(range(0, len(solution_moves), 2))


def _get_next_player_move_index(current_index: int, solution_moves: List[str]) -> Optional[int]:
    """Get the next player move index after current, or None if done."""
    next_idx = current_index + 2  # Skip opponent's response
    if next_idx < len(solution_moves):
        return next_idx
    return None


def _apply_opponent_response(board: chess.Board, solution_moves: List[str], 
                             current_player_index: int) -> Optional[str]:
    """
    Apply opponent's response move if one exists.
    
    Returns the opponent's UCI move if applied, None otherwise.
    """
    opponent_idx = current_player_index + 1
    if opponent_idx < len(solution_moves):
        opponent_uci = solution_moves[opponent_idx]
        try:
            move = chess.Move.from_uci(opponent_uci)
            if move in board.legal_moves:
                board.push(move)
                return opponent_uci
        except Exception:
            pass
    return None


def _legal_moves_uci(fen: str) -> List[str]:
    board = chess.Board(fen)
    return [m.uci() for m in board.legal_moves]


def render_puzzle_metadata(game_metadata: dict):
    """Render metadata about the puzzle's source game."""
    st.markdown(
        f"**Game {game_metadata['game_number']}**, {game_metadata['username']} - {game_metadata['opponent']}"
    )


def render_puzzle_trainer(puzzles: List[PuzzleDefinition]) -> None:
    """Render the new JS-board-based puzzle trainer with multi-move support."""

    if not puzzles:
        st.info("No puzzles to show.")
        return

    # Inject CSS to prevent scroll jumping on first interaction
    # This keeps the viewport stable when Streamlit reruns
    st.markdown(
        """
        <style>
        /* Prevent auto-scroll to changed elements */
        [data-testid="stVerticalBlock"] {
            scroll-margin-top: 0 !important;
        }
        /* Keep main container scroll stable */
        .main .block-container {
            scroll-behavior: auto !important;
        }
        </style>
        <script>
        // Save scroll position before Streamlit reruns
        (function() {
            const key = 'puzzle_scroll_y';
            const saved = sessionStorage.getItem(key);
            if (saved) {
                // Restore scroll position after a short delay to let DOM settle
                setTimeout(function() {
                    window.scrollTo(0, parseInt(saved, 10));
                }, 50);
            }
            // Save scroll position on any scroll
            window.addEventListener('scroll', function() {
                sessionStorage.setItem(key, window.scrollY);
            }, {passive: true});
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    progress = _get_progress()

    # Clamp index
    if progress.current_index < 0:
        progress.current_index = 0
    if progress.current_index >= len(puzzles):
        progress.current_index = len(puzzles) - 1

    # Expose current puzzle index in session_state for stable component keying.
    # This is intentionally stable across reruns while staying unique per puzzle.
    st.session_state.puzzle_index = int(progress.current_index)

    debug_board = bool(st.session_state.get("puzzle_debug_board", False))

    puzzle = puzzles[progress.current_index]
    
    # Get puzzle_key for Supabase solution caching
    puzzle_key = (
        getattr(puzzle, "puzzle_key", None)
        or getattr(puzzle, "puzzle_id", None)
        or f"fen_{hash(puzzle.fen)}"
    )

    # Compute solution lines asynchronously so puzzle load is instant.
    # We'll prefetch the active puzzle + the next puzzle in the background.
    cache = _get_solution_cache()
    first_uci = (getattr(puzzle, "first_move_uci", "") or "").strip() or (
        (puzzle.solution_moves[0] if puzzle.solution_moves else "").strip()
    )
    depth = int(PUZZLE_SOLUTION_ANALYSIS_DEPTH)
    cache_key = (puzzle.fen, first_uci, depth)

    # Schedule active puzzle line in background and harvest if already computed.
    # Pass puzzle_key for Supabase caching (speeds up "other users" puzzles)
    _schedule_solution_line(puzzle.fen, first_uci, depth=depth, puzzle_key=puzzle_key)
    _harvest_solution_line(puzzle.fen, first_uci, depth=depth, puzzle_key=puzzle_key)

    # Prefetch next puzzle while the user is solving this one.
    next_idx = progress.current_index + 1
    if 0 <= next_idx < len(puzzles):
        nxt = puzzles[next_idx]
        nxt_key = (
            getattr(nxt, "puzzle_key", None)
            or getattr(nxt, "puzzle_id", None)
            or f"fen_{hash(nxt.fen)}"
        )
        nxt_first = (getattr(nxt, "first_move_uci", "") or "").strip() or (
            (nxt.solution_moves[0] if nxt.solution_moves else "").strip()
        )
        if nxt_first:
            _schedule_solution_line(nxt.fen, nxt_first, depth=depth, puzzle_key=nxt_key)
            _harvest_solution_line(nxt.fen, nxt_first, depth=depth, puzzle_key=nxt_key)

    # Show source game metadata (if present). Only render player names if available;
    # otherwise omit metadata to avoid showing "Unknown - Unknown".
    src_idx = getattr(puzzle, "source_game_index", None)
    if src_idx:
        white = (getattr(puzzle, "white", "") or "").strip()
        black = (getattr(puzzle, "black", "") or "").strip()
        if white or black:
            render_puzzle_metadata(
                {
                    "game_number": int(src_idx),
                    "username": white or "",
                    "opponent": black or "",
                }
            )

    # Use dynamic solution line (if player chose an alternate viable move)
    solution_moves = progress.active_solution_moves or cache.get(cache_key) or puzzle.solution_moves
    
    # Calculate total player moves in this puzzle
    player_move_indices = _get_player_move_indices(solution_moves)
    total_player_moves = len(player_move_indices)
    current_player_move_num = (progress.solution_move_index // 2) + 1

    # Reset accepted position when switching puzzles
    if progress.active_puzzle_index != progress.current_index:
        progress.active_puzzle_index = progress.current_index
        _reset_puzzle_progress(progress, puzzle.fen)
        # Seed the solution line for this puzzle from cache
        solution_moves = cache.get(cache_key) or puzzle.solution_moves

    board_fen = progress.current_fen or puzzle.fen
    board = chess.Board(board_fen)

    # Keep orientation fixed per puzzle (based on side-to-move in the initial FEN)
    try:
        base_turn = chess.Board(puzzle.fen).turn
        orientation = "white" if base_turn == chess.WHITE else "black"
    except Exception:
        orientation = "white"
    side_to_move = "w" if board.turn == chess.WHITE else "b"

    legal_moves = _legal_moves_uci(board_fen)

    highlights = {
        "correct_squares": [],
        "incorrect_squares": [],
        "viable_squares": [],
    }

    if progress.last_result == "correct" and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            highlights["correct_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    if progress.last_result == "viable" and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            highlights["viable_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    if progress.last_result == "incorrect" and progress.last_uci:
        try:
            mv = chess.Move.from_uci(progress.last_uci)
            highlights["incorrect_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    # Highlight opponent's last move if they just moved
    if progress.opponent_just_moved and progress.opponent_last_uci:
        try:
            mv = chess.Move.from_uci(progress.opponent_last_uci)
            # Use a neutral highlight for opponent moves (we'll show it as "correct" color)
            highlights["correct_squares"] = [
                chess.square_name(mv.from_square),
                chess.square_name(mv.to_square),
            ]
        except Exception:
            pass

    cols = st.columns([2, 1])
    with cols[0]:
        # Show hint based on state
        if progress.last_result == "correct":
            hint = "Puzzle complete!"
        elif progress.opponent_just_moved:
            hint = "Your turn. Find the best move."
        elif progress.last_result is None:
            hint = "Drag a piece or click-to-move."
        else:
            hint = ""
            
        puzzle_id = (
            getattr(puzzle, "id", None)
            or getattr(puzzle, "puzzle_id", None)
            or getattr(puzzle, "uuid", None)
            or f"index_{progress.current_index}"
        )

        # Determine if we should animate a move (opponent just moved or reveal answer)
        animate_move = None
        if progress.opponent_just_moved and progress.opponent_last_uci:
            animate_move = progress.opponent_last_uci
            try:
                # Validate it's a real move before passing to FE
                # (Prevents partial strings from breaking JS)
                chess.Move.from_uci(animate_move)
            except Exception:
                animate_move = None

        elif progress.reveal_answer and progress.reveal_puzzle_index == progress.current_index:
            # Get the answer move to animate
            reveal_uci = (
                solution_moves[progress.solution_move_index]
                if progress.solution_move_index < len(solution_moves)
                else None
            )
            if reveal_uci:
                animate_move = reveal_uci
                try:
                    chess.Move.from_uci(animate_move)
                except Exception:
                    animate_move = None
        
        # Use a stable key to avoid remounting the component (which causes blinking).
        # The chessboard component handles FEN changes internally and re-renders smoothly.
        # Only change the key when switching to a different puzzle.
        
        if debug_board:
            st.write("DEBUG: rendering board", puzzle_id, "animate_move=", animate_move)
        move = render_chessboard(
            fen=board_fen,
            legal_moves=legal_moves,
            orientation=orientation,
            side_to_move=side_to_move,
            highlights=highlights,
            hint=hint,
            animate_move=animate_move,
            key=f"puzzle_board_{st.session_state.puzzle_index}",
        )
        if debug_board:
            st.write("DEBUG: board rendered")

        uci = move

        # Process move only once (and not if puzzle is complete)
        if uci and uci != progress.last_uci and progress.last_result not in ("correct", "viable"):
            progress.last_uci = uci
            progress.opponent_just_moved = False
            
            solution_moves = progress.active_solution_moves or cache.get(cache_key) or puzzle.solution_moves

            # Validate legality with python-chess
            try:
                move = chess.Move.from_uci(uci)
            except Exception:
                progress.last_result = "incorrect"
                st.rerun()

            if move not in board.legal_moves:
                progress.last_result = "incorrect"
                st.rerun()

            # Check against expected move at current solution index
            expected = solution_moves[progress.solution_move_index] if progress.solution_move_index < len(solution_moves) else None
            
            # DEBUG: Log move validation (visible in UI)
            debug_info = f"[DEBUG] Move={uci}, Expected={expected}, Index={progress.solution_move_index}, Total moves={len(solution_moves)}, solution_moves={solution_moves}"
            print(debug_info)
            st.warning(debug_info)  # Also show in UI
            
            # Classify the move: correct (green), viable (yellow), or incorrect (red)
            try:
                classification, cpl, why_not_optimal = _classify_move(board, uci, expected)
                st.info(f"[DEBUG] classification={classification}, cpl={cpl}")
            except Exception as e:
                # Fallback: just check if it matches expected
                st.error(f"[DEBUG] _classify_move exception: {e}")
                classification = "correct" if uci == expected else "incorrect"
                cpl = 0
                why_not_optimal = None
            
            # Store why_not_optimal for UI display
            if classification == "viable" and why_not_optimal:
                st.session_state["last_why_not_optimal"] = why_not_optimal
            else:
                st.session_state["last_why_not_optimal"] = None

            # FAIL FAST: Show incorrect immediately if move is wrong
            if classification == "incorrect":
                st.error(f"[DEBUG] FAIL FAST triggered - classification was incorrect")
                progress.last_result = "incorrect"
                st.rerun()
            
            # Only show "analyzing opponent response" spinner for correct/viable moves
            if classification in ("correct", "viable"):
                # For correct/viable moves, we may need the opponent's response
                # Show analyzing spinner while waiting for opponent response
                if progress.active_solution_moves is None and cache.get(cache_key) is None:
                    with st.spinner("Analyzing opponent response..."):
                        # Wait for solution line computation if still running
                        # This ensures we have the full multi-move solution before processing
                        _harvest_solution_line(puzzle.fen, first_uci, depth=depth, wait=True, puzzle_key=puzzle_key)
                
                # After harvest, re-fetch solution_moves from cache (might have been populated during wait)
                solution_moves = progress.active_solution_moves or cache.get(cache_key) or puzzle.solution_moves
                
                # Good move - continue the puzzle
                # Only recompute solution line if the move differs from expected
                # (for viable/alternate moves) - this avoids expensive engine calls
                if classification == "viable" and uci != expected:
                    try:
                        progress.active_solution_moves = compute_solution_line(
                            board_fen,
                            uci,
                            analysis_depth=PUZZLE_CLASSIFICATION_DEPTH,  # Use lower depth for speed
                        )
                        solution_moves = progress.active_solution_moves or solution_moves
                        progress.solution_move_index = 0
                    except Exception:
                        pass

                board.push(move)
                
                # Check if there's a continuation (opponent response + more player moves)
                next_player_idx = _get_next_player_move_index(
                    progress.solution_move_index, solution_moves
                )
                
                if next_player_idx is not None:
                    # Apply opponent's response
                    opponent_uci = _apply_opponent_response(
                        board, solution_moves, progress.solution_move_index
                    )
                    
                    if opponent_uci:
                        # Update state for continuation
                        progress.current_fen = board.fen()
                        progress.solution_move_index = next_player_idx
                        progress.last_uci = None  # Clear last move to prevent stale component output being reprocessed
                        progress.opponent_last_uci = opponent_uci  # Store for highlighting
                        progress.last_result = None  # Not complete yet
                        progress.opponent_just_moved = True
                        # NOTE: We no longer increment board_nonce - the component handles FEN changes smoothly
                    else:
                        # No valid opponent response, puzzle complete
                        progress.current_fen = board.fen()
                        progress.last_result = classification  # "correct" or "viable"
                        progress.solved += 1
                else:
                    # No more moves - puzzle complete!
                    progress.current_fen = board.fen()
                    progress.last_result = classification  # "correct" or "viable"
                    progress.solved += 1
            else:
                progress.last_result = "incorrect"

            st.rerun()

    with cols[1]:
        st.subheader("Puzzle")
        st.write(f"Theme: **{puzzle.theme}**")
        st.write(f"Difficulty: **{puzzle.difficulty}**")
        
        # Show move progress for multi-move puzzles
        if total_player_moves > 1:
            if progress.last_result in ("correct", "viable"):
                st.write(f"Moves: **{total_player_moves} / {total_player_moves}** ✓")
            else:
                st.write(f"Moves: **{current_player_move_num} / {total_player_moves}**")
        
        st.write(f"Progress: **{progress.current_index + 1} / {len(puzzles)}**")
        st.write(f"Solved: **{progress.solved}**")

        # Reveal answer (for the current move in the sequence)
        if st.button("🔍 Reveal answer", use_container_width=True):
            progress.reveal_answer = True
            progress.reveal_puzzle_index = progress.current_index
            progress.reveal_solution_move_index = progress.solution_move_index
            progress.last_uci = None

        if (
            progress.reveal_answer
            and progress.reveal_puzzle_index == progress.current_index
            and progress.reveal_solution_move_index == progress.solution_move_index
            and progress.last_result not in ("correct", "viable")
        ):
            # Show the answer for the current move in the solution sequence
            expected_uci = (
                solution_moves[progress.solution_move_index]
                if progress.solution_move_index < len(solution_moves)
                else None
            )
            if expected_uci:
                try:
                    b = chess.Board(board_fen)
                    mv = chess.Move.from_uci(expected_uci)
                    expected_san = b.san(mv) if mv in b.legal_moves else expected_uci
                except Exception:
                    expected_san = expected_uci
                st.info(f"Answer for this move: **{expected_san}** ({expected_uci})")

        if progress.last_result == "correct":
            st.success("Correct!" if total_player_moves == 1 else f"Correct! ({total_player_moves} moves)")
            if puzzle.explanation:
                st.info(f"💡 {puzzle.explanation}")
            
        elif progress.last_result == "viable":
            # Show why this isn't the optimal move
            why_not = st.session_state.get("last_why_not_optimal")
            if why_not:
                st.warning(f"Viable move! {why_not}")
            else:
                st.warning("Viable move! This works, but there may be a better option.")
            if puzzle.explanation:
                st.info(f"💡 {puzzle.explanation}")
            
        elif progress.last_result == "incorrect":
            st.error("Incorrect. Try again.")
        elif progress.opponent_just_moved:
            st.info("Opponent played. Find the next best move!")
            
        # Navigation and rating buttons - always visible
        st.markdown("---")
        _render_puzzle_nav_buttons(progress, len(puzzles), puzzle)
