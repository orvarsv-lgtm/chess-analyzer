"""Play vs Engine tab with move explanations and AI review.

This module provides:
1. A chessboard where the user plays against Stockfish (depth 10)
2. Optional explanation mode where user explains moves before making them
3. Post-game AI review that analyzes both the moves and the player's explanations
"""

from __future__ import annotations

import os
import shutil
import time
import chess
import chess.engine
import streamlit as st
from typing import Any, Optional
from dataclasses import dataclass, field


# Stockfish configuration - auto-detect path
def _find_stockfish_path() -> str:
    """Find Stockfish binary across different environments."""
    # Check environment variable first
    env_path = os.getenv("STOCKFISH_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    
    # Common paths to check
    candidates = [
        "/usr/games/stockfish",      # Linux apt (Streamlit Cloud)
        "/usr/bin/stockfish",        # Linux alternative
        "/opt/homebrew/bin/stockfish",  # macOS Homebrew ARM
        "/usr/local/bin/stockfish",  # macOS Homebrew Intel
        "stockfish",                 # In PATH
    ]
    
    for path in candidates:
        if os.path.isfile(path):
            return path
    
    # Try shutil.which as fallback
    which_path = shutil.which("stockfish")
    if which_path:
        return which_path
    
    # Default fallback
    return "/usr/games/stockfish"


STOCKFISH_PATH = _find_stockfish_path()
ENGINE_PLAY_DEPTH = 10  # Depth for engine opponent
ENGINE_REVIEW_DEPTH = 20  # Higher depth for post-game review


@dataclass
class GameState:
    """Represents the current state of a game vs engine."""
    board: chess.Board = field(default_factory=chess.Board)
    player_color: str = "white"  # "white" or "black"
    move_explanations: dict[int, str] = field(default_factory=dict)  # move_num -> explanation
    move_history: list[dict[str, Any]] = field(default_factory=list)
    game_over: bool = False
    result: str = ""
    pending_explanation: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "fen": self.board.fen(),
            "player_color": self.player_color,
            "move_explanations": self.move_explanations.copy(),
            "move_history": self.move_history.copy(),
            "game_over": self.game_over,
            "result": self.result,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        state = cls()
        state.board = chess.Board(data.get("fen", chess.STARTING_FEN))
        state.player_color = data.get("player_color", "white")
        state.move_explanations = data.get("move_explanations", {})
        state.move_history = data.get("move_history", [])
        state.game_over = data.get("game_over", False)
        state.result = data.get("result", "")
        return state


def _get_engine() -> Optional[chess.engine.SimpleEngine]:
    """Get a Stockfish engine instance."""
    try:
        return chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError:
        st.error(f"Stockfish not found at {STOCKFISH_PATH}. Please install Stockfish.")
        return None
    except Exception as e:
        st.error(f"Failed to start engine: {e}")
        return None


def _get_engine_elo() -> int:
    """Get the current engine Elo setting from session state."""
    return st.session_state.get("vs_engine_elo", 1500)


def _elo_to_description(elo: int) -> str:
    """Convert Elo to a human-readable skill description."""
    if elo <= 800:
        return "Beginner"
    elif elo <= 1000:
        return "Novice"
    elif elo <= 1200:
        return "Casual"
    elif elo <= 1400:
        return "Club Player"
    elif elo <= 1600:
        return "Intermediate"
    elif elo <= 1800:
        return "Advanced"
    elif elo <= 2000:
        return "Expert"
    elif elo <= 2200:
        return "Candidate Master"
    elif elo <= 2400:
        return "Master"
    elif elo <= 2600:
        return "International Master"
    else:
        return "Grandmaster"


def _get_engine_move(board: chess.Board, depth: int = ENGINE_PLAY_DEPTH, elo: int | None = None) -> Optional[chess.Move]:
    """Get the engine's best move for the current position.
    
    Args:
        board: Current board position
        depth: Search depth
        elo: Target Elo rating (uses UCI_LimitStrength). If None, uses session state.
    """
    engine = _get_engine()
    if engine is None:
        return None
    
    try:
        # Get target Elo from session state if not provided
        target_elo = elo if elo is not None else _get_engine_elo()
        
        # Configure engine strength using UCI options
        # Stockfish supports UCI_LimitStrength and UCI_Elo
        try:
            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": target_elo,
            })
        except chess.engine.EngineError:
            # Fallback for older Stockfish versions - use Skill Level (0-20)
            # Map Elo to skill level: 800 -> 0, 3200 -> 20
            skill = max(0, min(20, (target_elo - 800) // 120))
            try:
                engine.configure({"Skill Level": skill})
            except chess.engine.EngineError:
                pass  # Engine doesn't support skill limiting
        
        result = engine.play(board, chess.engine.Limit(depth=depth))
        move = result.move
        return move
    except Exception as e:
        st.error(f"Engine play error: {e}")
        return None
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def _analyze_position(board: chess.Board, depth: int = ENGINE_REVIEW_DEPTH) -> dict[str, Any]:
    """Analyze a position and return evaluation details."""
    engine = _get_engine()
    if engine is None:
        return {"error": "Engine not available"}
    
    try:
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info.get("score")
        pv = info.get("pv", [])
        
        if score is not None:
            cp = score.white().score(mate_score=10000)
        else:
            cp = 0
        
        return {
            "eval_cp": cp,
            "best_line": [board.san(m) for m in pv[:5]] if pv else [],
            "depth": depth,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def _get_phase(move_num: int) -> str:
    """Classify game phase by move number."""
    if move_num <= 15:
        return "Opening"
    elif move_num <= 40:
        return "Middlegame"
    else:
        return "Endgame"


def _classify_move_quality(cp_loss: int) -> str:
    """Classify move quality based on centipawn loss."""
    if cp_loss <= 10:
        return "Best"
    elif cp_loss <= 30:
        return "Excellent"
    elif cp_loss <= 60:
        return "Good"
    elif cp_loss <= 150:
        return "Inaccuracy"
    elif cp_loss <= 300:
        return "Mistake"
    else:
        return "Blunder"


def _init_game_state() -> None:
    """Initialize or reset the game state in session."""
    if "vs_engine_game" not in st.session_state:
        st.session_state["vs_engine_game"] = GameState()
    if "vs_engine_explanation_mode" not in st.session_state:
        st.session_state["vs_engine_explanation_mode"] = False
    if "vs_engine_review" not in st.session_state:
        st.session_state["vs_engine_review"] = None
    if "vs_engine_pending_move" not in st.session_state:
        st.session_state["vs_engine_pending_move"] = None
    if "vs_engine_elo" not in st.session_state:
        st.session_state["vs_engine_elo"] = 1500
    if "vs_engine_last_move" not in st.session_state:
        st.session_state["vs_engine_last_move"] = None
    if "vs_engine_thinking" not in st.session_state:
        st.session_state["vs_engine_thinking"] = False
    if "review_auto_play" not in st.session_state:
        st.session_state["review_auto_play"] = False


def _reset_game(player_color: str = "white") -> None:
    """Reset the game to initial state."""
    st.session_state["vs_engine_game"] = GameState(player_color=player_color)
    st.session_state["vs_engine_review"] = None
    st.session_state["vs_engine_pending_move"] = None
    
    # If player is black, engine plays first
    if player_color == "black":
        game = st.session_state["vs_engine_game"]
        engine_move = _get_engine_move(game.board)
        if engine_move:
            san = game.board.san(engine_move)
            game.board.push(engine_move)
            game.move_history.append({
                "move_num": 1,
                "san": san,
                "uci": engine_move.uci(),
                "player": "engine",
                "fen_after": game.board.fen(),
            })



def _make_engine_move(game: GameState, delay: float = 0.5) -> bool:
    """Execute engine move for the current turn.
    
    Args:
        game: Current game state
        delay: Seconds to wait before making move (for realism)
    """
    # Add a small delay for more natural feeling
    if delay > 0:
        time.sleep(delay)
    
    engine_move = _get_engine_move(game.board)
    if engine_move:
        engine_san = game.board.san(engine_move)
        engine_uci = engine_move.uci()
        game.board.push(engine_move)
        
        # Store last move for animation
        st.session_state["vs_engine_last_move"] = engine_uci
        
        current_move_num = (len(game.move_history) // 2) + 1
        
        game.move_history.append({
            "move_num": current_move_num,
            "san": engine_san,
            "uci": engine_uci,
            "player": "engine",
            "fen_after": game.board.fen(),
        })
        
        # Check if game is over after engine move
        if game.board.is_game_over():
            game.game_over = True
            game.result = game.board.result()
            
        st.session_state["vs_engine_game"] = game
        st.session_state["vs_engine_thinking"] = False
        return True
    st.session_state["vs_engine_thinking"] = False
    return False


def _make_player_move(uci_move: str, explanation: str = "") -> bool:
    """Execute a player move and get engine response."""
    game: GameState = st.session_state["vs_engine_game"]
    
    try:
        move = chess.Move.from_uci(uci_move)
        if move not in game.board.legal_moves:
            return False
        
        # Record player move
        move_num = (len(game.move_history) // 2) + 1
        san = game.board.san(move)
        game.board.push(move)
        
        # Save move to history
        player_move_data = {
            "move_num": move_num,
            "san": san,
            "uci": uci_move,
            "player": "human",
            "fen_after": game.board.fen(),
        }
        game.move_history.append(player_move_data)
        
        # Save explanation if provided
        if explanation.strip():
            game.move_explanations[len(game.move_history)] = explanation.strip()
        
        # Check if game is over after player move
        if game.board.is_game_over():
            game.game_over = True
            game.result = game.board.result()
            # Force session state update
            st.session_state["vs_engine_game"] = game
            return True
        
        # Engine responds
        _make_engine_move(game)
        
        # Force session state update
        st.session_state["vs_engine_game"] = game
        return True
        
    except Exception as e:
        st.error(f"Move error: {e}")
        return False


def _review_game_with_ai() -> dict[str, Any]:
    """Review the completed game with deep engine analysis and explanation review."""
    game: GameState = st.session_state["vs_engine_game"]
    
    if not game.move_history:
        return {"error": "No moves to review"}
    
    review = {
        "moves_analysis": [],
        "phase_summary": {"Opening": [], "Middlegame": [], "Endgame": []},
        "explanation_review": [],
        "overall_summary": "",
    }
    
    # Replay the game and analyze each player move
    analysis_board = chess.Board()
    player_moves_analyzed = 0
    total_cp_loss = 0
    
    for i, move_data in enumerate(game.move_history):
        move = chess.Move.from_uci(move_data["uci"])
        san = move_data["san"]
        is_player_move = move_data["player"] == "human"
        
        if is_player_move:
            player_moves_analyzed += 1
            move_num = (player_moves_analyzed + 1) // 2 if game.player_color == "white" else player_moves_analyzed // 2 + 1
            phase = _get_phase(move_num)
            
            # Get evaluation before the move
            eval_before = _analyze_position(analysis_board, depth=ENGINE_REVIEW_DEPTH)
            
            # Get best move according to engine
            engine = _get_engine()
            best_move = None
            best_san = ""
            if engine:
                try:
                    result = engine.play(analysis_board, chess.engine.Limit(depth=ENGINE_REVIEW_DEPTH))
                    best_move = result.move
                    best_san = analysis_board.san(best_move) if best_move else ""
                except Exception:
                    pass
                finally:
                    try:
                        engine.quit()
                    except Exception:
                        pass
            
            # Make the actual move
            analysis_board.push(move)
            
            # Get evaluation after the move
            eval_after = _analyze_position(analysis_board, depth=ENGINE_REVIEW_DEPTH)
            
            # Calculate CP loss (from player's perspective)
            cp_before = eval_before.get("eval_cp", 0)
            cp_after = eval_after.get("eval_cp", 0)
            
            if game.player_color == "white":
                cp_loss = max(0, cp_before - cp_after)
            else:
                cp_loss = max(0, cp_after - cp_before)
            
            total_cp_loss += cp_loss
            quality = _classify_move_quality(cp_loss)
            
            # Check if there was an explanation for this move
            explanation = game.move_explanations.get(i + 1, "")
            
            # Generate AI coaching feedback for this move
            ai_feedback = _generate_move_feedback(san, best_san, cp_loss, quality, phase)
            
            move_analysis = {
                "move_num": move_num,
                "san": san,
                "phase": phase,
                "eval_before": cp_before,
                "eval_after": cp_after,
                "cp_loss": cp_loss,
                "quality": quality,
                "best_move": best_san,
                "was_best": san == best_san,
                "explanation": explanation,
                "ai_feedback": ai_feedback,
                "history_index": i,  # Track position in move history
            }
            
            review["moves_analysis"].append(move_analysis)
            review["phase_summary"][phase].append(move_analysis)
            
            # Review the explanation if provided
            if explanation:
                explanation_feedback = _review_explanation(
                    explanation, san, best_san, cp_loss, quality, phase
                )
                review["explanation_review"].append({
                    "move_num": move_num,
                    "san": san,
                    "explanation": explanation,
                    "feedback": explanation_feedback,
                })
        else:
            # Engine move - just push it
            analysis_board.push(move)
    
    # Generate overall summary
    avg_cp_loss = total_cp_loss / player_moves_analyzed if player_moves_analyzed > 0 else 0
    
    review["overall_summary"] = _generate_overall_summary(
        review, avg_cp_loss, player_moves_analyzed, game.result, game.player_color
    )
    
    return review


def _generate_move_feedback(
    played_move: str,
    best_move: str,
    cp_loss: int,
    quality: str,
    phase: str,
) -> str:
    """Generate AI coaching feedback for a move (regardless of whether it was explained)."""
    feedback_parts = []
    
    was_best = played_move == best_move
    
    if was_best:
        feedback_parts.append(f"🏆 **Excellent!** You found the best move ({played_move}).")
        if phase == "Opening":
            feedback_parts.append("Great opening knowledge!")
        elif phase == "Middlegame":
            feedback_parts.append("Sharp tactical vision!")
        else:
            feedback_parts.append("Precise endgame technique!")
    elif quality in ("Best", "Excellent"):
        feedback_parts.append(
            f"⭐ **Very good!** Your move {played_move} was strong. "
            f"The engine's top choice was {best_move}, but yours was nearly as good."
        )
    elif quality == "Good":
        feedback_parts.append(
            f"✅ **Solid move.** {played_move} is a reasonable choice. "
            f"The best move was {best_move} (you lost ~{cp_loss}cp)."
        )
    elif quality == "Inaccuracy":
        feedback_parts.append(
            f"⚠️ **Inaccuracy.** {played_move} is playable but not optimal. "
            f"{best_move} was better (lost ~{cp_loss}cp)."
        )
        # Add phase-specific tip
        if phase == "Opening":
            feedback_parts.append("💡 *Tip: Focus on development and controlling the center.*")
        elif phase == "Middlegame":
            feedback_parts.append("💡 *Tip: Look for tactical patterns and piece coordination.*")
        else:
            feedback_parts.append("💡 *Tip: Activate your king and create passed pawns.*")
    elif quality == "Mistake":
        feedback_parts.append(
            f"❌ **Mistake.** {played_move} gave up significant advantage. "
            f"{best_move} was much better (lost ~{cp_loss}cp)."
        )
        feedback_parts.append("🔍 *Take a moment to understand why the engine's move was stronger.*")
    else:  # Blunder
        feedback_parts.append(
            f"🚨 **Blunder!** {played_move} was a serious error. "
            f"{best_move} was critical here (lost ~{cp_loss}cp)."
        )
        feedback_parts.append("📚 *Study this position carefully - what did you miss?*")
    
    return " ".join(feedback_parts)


def _review_explanation(
    explanation: str,
    played_move: str,
    best_move: str,
    cp_loss: int,
    quality: str,
    phase: str,
) -> str:
    """Generate feedback on the player's explanation for a move."""
    feedback_parts = []
    
    was_best = played_move == best_move
    
    if was_best:
        feedback_parts.append(f"✅ **Good thinking!** You played the best move ({played_move}).")
    elif quality in ("Best", "Excellent", "Good"):
        feedback_parts.append(
            f"👍 **Solid reasoning.** Your move ({played_move}) was {quality.lower()}. "
            f"The engine's top choice was {best_move}, but your move was also strong."
        )
    elif quality == "Inaccuracy":
        feedback_parts.append(
            f"⚠️ **Slight inaccuracy.** Your reasoning led to {played_move}, "
            f"but {best_move} was more precise (lost ~{cp_loss}cp)."
        )
    elif quality == "Mistake":
        feedback_parts.append(
            f"❌ **Mistake detected.** Your explanation for {played_move} may have missed "
            f"a tactical or positional nuance. {best_move} was significantly better "
            f"(lost ~{cp_loss}cp)."
        )
    else:  # Blunder
        feedback_parts.append(
            f"🚨 **Blunder!** The reasoning for {played_move} had a critical flaw. "
            f"{best_move} was much stronger (lost ~{cp_loss}cp). "
            f"Consider what you might have overlooked."
        )
    
    # Phase-specific advice
    if phase == "Opening" and quality not in ("Best", "Excellent", "Good"):
        feedback_parts.append("💡 *In the opening, prioritize development and center control.*")
    elif phase == "Middlegame" and quality not in ("Best", "Excellent", "Good"):
        feedback_parts.append("💡 *In the middlegame, look for tactical opportunities and piece coordination.*")
    elif phase == "Endgame" and quality not in ("Best", "Excellent", "Good"):
        feedback_parts.append("💡 *In the endgame, king activity and pawn promotion are key themes.*")
    
    return " ".join(feedback_parts)


def _generate_overall_summary(
    review: dict[str, Any],
    avg_cp_loss: float,
    total_moves: int,
    result: str,
    player_color: str,
) -> str:
    """Generate an overall game summary."""
    summary_parts = []
    
    # Result interpretation
    if result == "1-0":
        won = player_color == "white"
    elif result == "0-1":
        won = player_color == "black"
    else:
        won = None
    
    if won is True:
        summary_parts.append("🎉 **Congratulations on the win!**")
    elif won is False:
        summary_parts.append("📚 **Good effort! Let's learn from this game.**")
    else:
        summary_parts.append("🤝 **A hard-fought draw.**")
    
    # Performance rating
    if avg_cp_loss <= 30:
        summary_parts.append(f"Your average centipawn loss was **{avg_cp_loss:.0f}** - excellent accuracy!")
    elif avg_cp_loss <= 60:
        summary_parts.append(f"Your average centipawn loss was **{avg_cp_loss:.0f}** - good play.")
    elif avg_cp_loss <= 100:
        summary_parts.append(f"Your average centipawn loss was **{avg_cp_loss:.0f}** - room for improvement.")
    else:
        summary_parts.append(f"Your average centipawn loss was **{avg_cp_loss:.0f}** - focus on reducing mistakes.")
    
    # Phase breakdown
    for phase in ("Opening", "Middlegame", "Endgame"):
        phase_moves = review["phase_summary"].get(phase, [])
        if phase_moves:
            phase_cpl = sum(m["cp_loss"] for m in phase_moves) / len(phase_moves)
            blunders = sum(1 for m in phase_moves if m["quality"] == "Blunder")
            mistakes = sum(1 for m in phase_moves if m["quality"] == "Mistake")
            
            if blunders > 0 or mistakes > 0:
                summary_parts.append(
                    f"**{phase}:** {len(phase_moves)} moves, avg CPL {phase_cpl:.0f} "
                    f"({blunders} blunders, {mistakes} mistakes)"
                )
            else:
                summary_parts.append(
                    f"**{phase}:** {len(phase_moves)} moves, avg CPL {phase_cpl:.0f} - solid!"
                )
    
    # Explanation review summary
    if review["explanation_review"]:
        good_explanations = sum(
            1 for e in review["explanation_review"]
            if "Good" in e["feedback"] or "Solid" in e["feedback"]
        )
        summary_parts.append(
            f"\n📝 **Explanation Quality:** {good_explanations}/{len(review['explanation_review'])} "
            f"of your explained moves showed good thinking."
        )
    
    return "\n\n".join(summary_parts)


def _render_simple_board(board: chess.Board, orientation: str = "white", selected_move: str | None = None, animate_move: str | None = None) -> str | None:
    """Render a chess board with optional highlight for pending move.
    
    Args:
        board: Current board position
        orientation: "white" or "black"
        selected_move: UCI move to highlight (e.g., "e2e4") - highlights destination green
        animate_move: UCI move to animate (piece sliding)
    
    Returns the UCI move if user made one, else None.
    """
    # Use the JS board component if available
    try:
        from ui.chessboard_component import render_chessboard
        
        legal_moves = [m.uci() for m in board.legal_moves]
        side_to_move = "w" if board.turn == chess.WHITE else "b"
        
        # Build highlights dict for selected move
        highlights = {}
        if selected_move and len(selected_move) >= 4:
            to_sq = selected_move[2:4]
            highlights = {
                "correct_squares": [to_sq],
            }
        
        # Use stable key - component should handle FEN updates internally
        component_key = "vs_engine_board_main"
        
        move = render_chessboard(
            fen=board.fen(),
            legal_moves=legal_moves,
            orientation=orientation,
            side_to_move=side_to_move,
            highlights=highlights,
            animate_move=animate_move,
            key=component_key,
        )
        
        return move
            
    except ImportError:
        # Fallback to text board
        st.code(board.unicode(invert_color=orientation == "black"))
        return None


def render_play_vs_engine_tab() -> None:
    """Render the Play vs Engine tab."""
    st.header("⚔️ Play vs Engine")
    st.caption("Challenge Stockfish and improve your thinking • Explain your moves to get AI feedback")
    
    _init_game_state()
    
    game: GameState = st.session_state["vs_engine_game"]
    explanation_mode = st.session_state["vs_engine_explanation_mode"]
    review = st.session_state["vs_engine_review"]
    
    # Sidebar controls
    with st.sidebar:
        st.subheader("⚙️ Game Settings")
        
        # Color selection
        new_color = st.radio(
            "Play as",
            options=["White", "Black"],
            horizontal=True,
            key="vs_engine_color_select",
        )
        
        # Engine strength slider
        current_elo = st.session_state.get("vs_engine_elo", 1500)
        new_elo = st.slider(
            "🤖 Engine Rating",
            min_value=800,
            max_value=3200,
            value=current_elo,
            step=100,
            key="vs_engine_elo_slider",
            help="Adjust the engine's playing strength (Elo rating)",
        )
        
        # Show skill description
        skill_desc = _elo_to_description(new_elo)
        st.caption(f"**{new_elo} Elo** — {skill_desc}")
        
        # Update session state if changed
        if new_elo != current_elo:
            st.session_state["vs_engine_elo"] = new_elo
        
        st.divider()
        
        # Explanation mode toggle
        st.session_state["vs_engine_explanation_mode"] = st.toggle(
            "🧠 Explanation Mode",
            value=explanation_mode,
            help="When enabled, you'll explain your thinking before each move",
        )
        
        # New game button
        if st.button("🔄 New Game", use_container_width=True):
            _reset_game(player_color=new_color.lower())
            st.rerun()
    
    # Main game area
    if review is not None:
        # Show game review
        _render_game_review(review)
        
        if st.button("🎮 Play Another Game"):
            st.session_state["vs_engine_review"] = None
            st.session_state["review_move_index"] = 0
            _reset_game(player_color=game.player_color)
            st.rerun()
    else:
        # Active game
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Get pending move for highlighting (only in explanation mode)
            pending_move = st.session_state.get("vs_engine_pending_move")
            last_move = st.session_state.get("vs_engine_last_move")
            
            # Display board with highlight if move is pending, animate last engine move
            user_move = _render_simple_board(
                game.board, 
                orientation=game.player_color,
                selected_move=pending_move,
                animate_move=last_move
            )
            
            # Clear the animation after render
            if last_move:
                st.session_state["vs_engine_last_move"] = None
            
            # If user made a move on the board
            if user_move:
                if st.session_state["vs_engine_explanation_mode"]:
                    # Explanation mode - store as pending, show confirm
                    # Only update if different to avoid infinite rerun loops
                    if st.session_state.get("vs_engine_pending_move") != user_move:
                        st.session_state["vs_engine_pending_move"] = user_move
                        st.rerun()
                else:
                    # No explanation mode - play immediately
                    # Show "thinking" and schedule engine move
                    st.session_state["vs_engine_thinking"] = True
                    _make_player_move(user_move, "")
                    st.rerun()
            
            if game.game_over:
                st.success(f"**Game Over!** Result: {game.result}")
                if st.button("📊 Review this Game with AI"):
                    with st.spinner("Analyzing game with depth 20..."):
                        review_result = _review_game_with_ai()
                        st.session_state["vs_engine_review"] = review_result
                    st.rerun()
            elif pending_move and st.session_state["vs_engine_explanation_mode"]:
                # Explanation mode with pending move - show explanation box and confirm
                # Convert UCI to readable format
                try:
                    move_obj = chess.Move.from_uci(pending_move)
                    san = game.board.san(move_obj)
                    st.success(f"**Selected:** {san}")
                except:
                    st.success(f"**Selected:** {pending_move}")
                
                # Explanation text area
                move_count = len(game.move_history)
                explanation = st.text_area(
                    "📝 Explain your thinking:",
                    placeholder="Why are you playing this move? What's your plan?",
                    key=f"move_explanation_input_{move_count}",
                )
                
                # Confirm and Cancel buttons
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("✅ Confirm", use_container_width=True, type="primary"):
                        with st.spinner("Engine is thinking..."):
                            _make_player_move(pending_move, explanation)
                            st.session_state["vs_engine_pending_move"] = None
                            st.rerun()
                with col_cancel:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state["vs_engine_pending_move"] = None
                        st.rerun()
            else:
                # Check whose turn it is
                is_player_turn = (
                    (game.board.turn == chess.WHITE and game.player_color == "white") or
                    (game.board.turn == chess.BLACK and game.player_color == "black")
                )
                
                if is_player_turn:
                    st.info("🎯 **Your turn** - Click a piece, then click destination")
                else:
                    # Engine's turn - show thinking message and make move
                    st.info("🤔 **Engine is thinking...**")
                    _make_engine_move(game, delay=0.8)  # Slight delay for realism
                    st.rerun()
            
            # Resign button (always visible during active game)
            if not game.game_over:
                st.divider()
                if st.button("🏳️ Resign", use_container_width=True, type="secondary"):
                    game.game_over = True
                    game.result = "0-1" if game.player_color == "white" else "1-0"
                    st.rerun()
        
        with col2:
            # Move history
            st.subheader("📜 Moves")
            if game.move_history:
                moves_text = []
                for i, m in enumerate(game.move_history):
                    if m["player"] == "human":
                        san = f"**{m['san']}**"
                    else:
                        san = m["san"]
                    
                    if i % 2 == 0:
                        move_num = (i // 2) + 1
                        moves_text.append(f"{move_num}. {san}")
                    else:
                        moves_text[-1] += f" {san}"
                
                st.markdown("  \n".join(moves_text))
            else:
                st.caption("No moves yet")
            
            # Explanations summary
            if game.move_explanations:
                st.subheader("💭 Your Explanations")
                for move_idx, expl in sorted(game.move_explanations.items()):
                    move_data = game.move_history[move_idx - 1] if move_idx <= len(game.move_history) else None
                    if move_data:
                        st.caption(f"**{move_data['san']}:** {expl[:100]}...")


def _render_game_review(review: dict[str, Any]) -> None:
    """Render the AI game review with interactive board navigation."""
    st.subheader("📊 AI Game Review")
    
    if "error" in review:
        st.error(review["error"])
        return
    
    game: GameState = st.session_state["vs_engine_game"]
    
    # Initialize review navigation state
    if "review_move_index" not in st.session_state:
        st.session_state["review_move_index"] = 0
    
    moves_analysis = review.get("moves_analysis", [])
    move_history = game.move_history
    
    # Build list of all positions (starting + after each move)
    positions = [chess.STARTING_FEN]
    for m in move_history:
        positions.append(m["fen_after"])
    
    # Current position index
    current_idx = st.session_state["review_move_index"]
    max_idx = len(positions) - 1
    
    # Auto-play state
    auto_playing = st.session_state.get("review_auto_play", False)
    
    # Get the move to animate (the move that led to current position)
    animate_move = None
    if current_idx > 0:
        animate_move = move_history[current_idx - 1].get("uci")
    
    # Layout: board on left, analysis on right
    col_board, col_analysis = st.columns([1, 1])
    
    with col_board:
        # Render the board at current position with animation
        current_fen = positions[current_idx]
        board = chess.Board(current_fen)
        
        try:
            from ui.chessboard_component import render_chessboard
            render_chessboard(
                fen=current_fen,
                legal_moves=[],  # No moves during review
                orientation=game.player_color,
                side_to_move="w" if board.turn == chess.WHITE else "b",
                animate_move=animate_move,
                key="vs_engine_review_board",
            )
        except ImportError:
            st.code(board.unicode(invert_color=game.player_color == "black"))
        
        # Navigation buttons - first row: main controls
        col_first, col_prev, col_play, col_next, col_last = st.columns(5)
        
        with col_first:
            if st.button("⏮️", use_container_width=True, disabled=current_idx == 0, key="review_first"):
                st.session_state["review_auto_play"] = False
                st.session_state["review_move_index"] = 0
                st.rerun()
        
        with col_prev:
            if st.button("◀️", use_container_width=True, disabled=current_idx == 0, key="review_prev"):
                st.session_state["review_auto_play"] = False
                st.session_state["review_move_index"] = current_idx - 1
                st.rerun()
        
        with col_play:
            # Auto-play toggle
            if auto_playing:
                if st.button("⏸️", use_container_width=True, key="review_pause"):
                    st.session_state["review_auto_play"] = False
                    st.rerun()
            else:
                if st.button("▶️", use_container_width=True, disabled=current_idx >= max_idx, key="review_play"):
                    st.session_state["review_auto_play"] = True
                    st.rerun()
        
        with col_next:
            if st.button("▶️", use_container_width=True, disabled=current_idx >= max_idx, key="review_next"):
                st.session_state["review_auto_play"] = False
                st.session_state["review_move_index"] = current_idx + 1
                st.rerun()
        
        with col_last:
            if st.button("⏭️", use_container_width=True, disabled=current_idx >= max_idx, key="review_last"):
                st.session_state["review_auto_play"] = False
                st.session_state["review_move_index"] = max_idx
                st.rerun()
        
        # Progress indicator
        progress = current_idx / max_idx if max_idx > 0 else 0
        st.progress(progress, text=f"Move {current_idx} of {max_idx}")
        
        # Auto-play: advance to next position after delay
        if auto_playing and current_idx < max_idx:
            time.sleep(1.2)  # Delay between moves for comfortable viewing
            st.session_state["review_move_index"] = current_idx + 1
            st.rerun()
        elif auto_playing and current_idx >= max_idx:
            st.session_state["review_auto_play"] = False
    
    with col_analysis:
        # Show analysis for the current move (if any)
        if current_idx > 0:
            # Get the move that led to this position
            move_data = move_history[current_idx - 1]
            san = move_data["san"]
            player = move_data["player"]
            
            if player == "human":
                # Find the analysis for this move
                move_analysis = None
                for m in moves_analysis:
                    if m["san"] == san:
                        move_analysis = m
                        break
                
                if move_analysis:
                    quality = move_analysis["quality"]
                    quality_emoji = {
                        "Best": "🏆",
                        "Excellent": "⭐",
                        "Good": "✅",
                        "Inaccuracy": "⚠️",
                        "Mistake": "❌",
                        "Blunder": "🚨",
                    }.get(quality, "•")
                    
                    st.markdown(f"### Move {move_analysis['move_num']}: {san}")
                    
                    # Show key metrics in columns
                    met_col1, met_col2 = st.columns(2)
                    with met_col1:
                        st.metric("Quality", f"{quality_emoji} {quality}")
                    with met_col2:
                        st.metric("CPL", f"{move_analysis['cp_loss']}")
                    
                    st.caption(f"Phase: {move_analysis['phase']}")
                    
                    if move_analysis["was_best"]:
                        st.success("✓ This was the best move!")
                    else:
                        st.warning(f"Best move: **{move_analysis['best_move']}**")
                    
                    st.divider()
                    
                    # Show AI feedback (always available now)
                    st.markdown("**🤖 AI Coach:**")
                    st.markdown(move_analysis.get("ai_feedback", "No analysis available."))
                    
                    # Show user's explanation if they provided one
                    explanation_review = None
                    for er in review.get("explanation_review", []):
                        if er["san"] == san:
                            explanation_review = er
                            break
                    
                    if explanation_review:
                        st.divider()
                        st.markdown("**💭 Your explanation:**")
                        st.markdown(f"*\"{explanation_review['explanation']}\"*")
                        st.markdown("**Feedback:** " + explanation_review["feedback"])
                else:
                    st.markdown(f"### Your move: {san}")
                    st.caption("Analysis not available for this move.")
            else:
                st.markdown(f"### Engine played: {san}")
                st.caption("This was the engine's response.")
        else:
            st.markdown("### Starting Position")
            st.caption("Use the navigation buttons to step through the game.")
        
        st.divider()
        
        # Overall summary at the bottom
        with st.expander("📋 Overall Summary", expanded=False):
            st.markdown(review.get("overall_summary", ""))
