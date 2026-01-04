"""
Puzzle Data Types and Schemas

Defines all data structures for the puzzle system.
All types are deterministic and serializable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import json


class PuzzleType(str, Enum):
    """
    Categories of puzzles based on the nature of the mistake.
    
    Classification Rules:
    - MISSED_TACTIC: Move involved capture/check/fork/pin opportunity missed
    - ENDGAME_TECHNIQUE: Error occurred in endgame phase with significant eval loss
    - OPENING_ERROR: Deviation from theory before move 10
    """
    MISSED_TACTIC = "missed_tactic"
    ENDGAME_TECHNIQUE = "endgame_technique"
    OPENING_ERROR = "opening_error"


class Difficulty(str, Enum):
    """
    Puzzle difficulty levels.
    
    Classification Rules (deterministic):
    - EASY: Single obvious best move, eval loss ≥300cp (clear blunder)
    - MEDIUM: Eval loss ≥200cp, typically involves capture or tactic
    - HARD: Eval loss ≥100cp, often quiet/defensive moves
    """
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class Puzzle:
    """
    A single chess puzzle derived from an analyzed game.
    
    All fields are deterministic and derived from engine analysis.
    No AI/LLM-generated content - purely data from engine evaluation.
    """
    # Unique identifier: "{source_game_index}_{move_number}"
    puzzle_id: str
    
    # FEN position BEFORE the played move (this is the puzzle position)
    fen: str
    
    # Side to move: derived from FEN (w/b parsed to "white"/"black")
    side_to_move: str  # "white" or "black"
    
    # The correct answer: best engine move in SAN notation
    best_move_san: str
    
    # The move that was actually played (the mistake/blunder)
    played_move_san: str
    
    # Evaluation loss in centipawns (always positive)
    eval_loss_cp: int
    
    # Game phase when the mistake occurred
    phase: str  # "opening", "middlegame", or "endgame"
    
    # Classified puzzle type
    puzzle_type: PuzzleType
    
    # Difficulty classification
    difficulty: Difficulty
    
    # Reference to source game
    source_game_index: int
    
    # Move number where the mistake occurred
    move_number: int
    
    # Additional metadata for UI display (optional)
    eval_before: Optional[int] = None  # Eval before the move (centipawns)
    eval_after: Optional[int] = None   # Eval after the played move
    best_move_uci: Optional[str] = None  # UCI notation for move validation
    
    # Deterministic explanation of why the move is correct (generated from position)
    explanation: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "puzzle_id": self.puzzle_id,
            "fen": self.fen,
            "side_to_move": self.side_to_move,
            "best_move_san": self.best_move_san,
            "played_move_san": self.played_move_san,
            "eval_loss_cp": self.eval_loss_cp,
            "phase": self.phase,
            "puzzle_type": self.puzzle_type.value,
            "difficulty": self.difficulty.value,
            "source_game_index": self.source_game_index,
            "move_number": self.move_number,
            "eval_before": self.eval_before,
            "eval_after": self.eval_after,
            "best_move_uci": self.best_move_uci,
            "explanation": self.explanation,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Puzzle:
        """Create Puzzle from dictionary."""
        return cls(
            puzzle_id=data["puzzle_id"],
            fen=data["fen"],
            side_to_move=data["side_to_move"],
            best_move_san=data["best_move_san"],
            played_move_san=data["played_move_san"],
            eval_loss_cp=data["eval_loss_cp"],
            phase=data["phase"],
            puzzle_type=PuzzleType(data["puzzle_type"]),
            difficulty=Difficulty(data["difficulty"]),
            source_game_index=data["source_game_index"],
            move_number=data["move_number"],
            eval_before=data.get("eval_before"),
            eval_after=data.get("eval_after"),
            best_move_uci=data.get("best_move_uci"),
            explanation=data.get("explanation"),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PuzzleAttempt:
    """
    Records a single attempt at solving a puzzle.
    """
    puzzle_id: str
    attempted_move_san: str
    is_correct: bool
    attempt_number: int  # 1-indexed, how many tries
    
    def to_dict(self) -> dict:
        return {
            "puzzle_id": self.puzzle_id,
            "attempted_move_san": self.attempted_move_san,
            "is_correct": self.is_correct,
            "attempt_number": self.attempt_number,
        }


@dataclass
class PuzzleSession:
    """
    Tracks a puzzle-solving session.
    
    Manages state for:
    - Current puzzle index
    - Attempts per puzzle
    - Total solved count
    - Free vs paid gating
    """
    # All puzzles available in this session
    puzzles: List[Puzzle] = field(default_factory=list)
    
    # Current position in puzzle list (0-indexed)
    current_index: int = 0
    
    # Attempts for each puzzle: puzzle_id -> list of attempts
    attempts: dict = field(default_factory=dict)
    
    # Count of correctly solved puzzles
    solved_count: int = 0
    
    # Premium status (affects puzzle limit)
    is_premium: bool = False
    
    # Maximum puzzles for free users
    MAX_FREE_PUZZLES: int = 5
    
    @property
    def current_puzzle(self) -> Optional[Puzzle]:
        """Get the current puzzle, if any."""
        if 0 <= self.current_index < len(self.puzzles):
            return self.puzzles[self.current_index]
        return None
    
    @property
    def total_puzzles(self) -> int:
        """Total number of puzzles in session."""
        return len(self.puzzles)
    
    @property
    def puzzles_remaining(self) -> int:
        """How many puzzles left to attempt."""
        return max(0, len(self.puzzles) - self.current_index)
    
    @property
    def is_at_limit(self) -> bool:
        """Check if free user has hit puzzle limit."""
        if self.is_premium:
            return False
        return self.current_index >= self.MAX_FREE_PUZZLES
    
    @property
    def available_puzzle_count(self) -> int:
        """Number of puzzles available to user based on premium status."""
        if self.is_premium:
            return len(self.puzzles)
        return min(len(self.puzzles), self.MAX_FREE_PUZZLES)
    
    def get_attempts_for_current(self) -> List[PuzzleAttempt]:
        """Get all attempts for current puzzle."""
        if self.current_puzzle is None:
            return []
        return self.attempts.get(self.current_puzzle.puzzle_id, [])
    
    def record_attempt(self, move_san: str, is_correct: bool) -> PuzzleAttempt:
        """Record an attempt at the current puzzle."""
        if self.current_puzzle is None:
            raise ValueError("No current puzzle to attempt")
        
        puzzle_id = self.current_puzzle.puzzle_id
        if puzzle_id not in self.attempts:
            self.attempts[puzzle_id] = []
        
        attempt = PuzzleAttempt(
            puzzle_id=puzzle_id,
            attempted_move_san=move_san,
            is_correct=is_correct,
            attempt_number=len(self.attempts[puzzle_id]) + 1,
        )
        self.attempts[puzzle_id].append(attempt)
        
        if is_correct:
            self.solved_count += 1
        
        return attempt
    
    def advance_to_next(self) -> bool:
        """
        Move to next puzzle.
        Returns True if successfully advanced, False if at end or limit.
        """
        if self.is_at_limit:
            return False
        if self.current_index >= len(self.puzzles) - 1:
            return False
        self.current_index += 1
        return True
    
    def reset(self) -> None:
        """Reset session to beginning."""
        self.current_index = 0
        self.attempts = {}
        self.solved_count = 0
    
    def get_stats(self) -> dict:
        """Get session statistics."""
        total_attempts = sum(len(a) for a in self.attempts.values())
        return {
            "total_puzzles": self.total_puzzles,
            "puzzles_attempted": len(self.attempts),
            "puzzles_solved": self.solved_count,
            "total_attempts": total_attempts,
            "current_index": self.current_index,
            "is_premium": self.is_premium,
            "is_at_limit": self.is_at_limit,
        }
    
    def to_dict(self) -> dict:
        """Serialize session state."""
        return {
            "puzzles": [p.to_dict() for p in self.puzzles],
            "current_index": self.current_index,
            "attempts": {
                pid: [a.to_dict() for a in attempts]
                for pid, attempts in self.attempts.items()
            },
            "solved_count": self.solved_count,
            "is_premium": self.is_premium,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> PuzzleSession:
        """Deserialize session state."""
        session = cls(
            puzzles=[Puzzle.from_dict(p) for p in data.get("puzzles", [])],
            current_index=data.get("current_index", 0),
            solved_count=data.get("solved_count", 0),
            is_premium=data.get("is_premium", False),
        )
        
        # Reconstruct attempts
        for pid, attempts in data.get("attempts", {}).items():
            session.attempts[pid] = [
                PuzzleAttempt(
                    puzzle_id=a["puzzle_id"],
                    attempted_move_san=a["attempted_move_san"],
                    is_correct=a["is_correct"],
                    attempt_number=a["attempt_number"],
                )
                for a in attempts
            ]
        
        return session
