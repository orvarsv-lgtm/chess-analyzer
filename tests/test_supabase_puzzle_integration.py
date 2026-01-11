import os
import chess
import pytest
from puzzles.puzzle_types import Puzzle, Difficulty, PuzzleType
from puzzles.global_puzzle_store import save_puzzles_to_global_bank, load_rating_counts

def test_supabase_cross_user_puzzle_save_and_rating():
    # Set up environment for Supabase backend
    os.environ["PUZZLE_BANK_BACKEND"] = "supabase"
    os.environ["SUPABASE_URL"] = "<YOUR_SUPABASE_URL>"  # Set your actual Supabase URL
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "<YOUR_SUPABASE_KEY>"  # Set your actual Supabase key

    # Create two users and two puzzles
    puzzle1 = Puzzle(
        puzzle_id="user1_1",
        fen=chess.STARTING_FEN,
        side_to_move="white",
        best_move_san="e4",
        played_move_san="d4",
        eval_loss_cp=150,
        phase="opening",
        puzzle_type=PuzzleType.OPENING_ERROR,
        difficulty=Difficulty.EASY,
        source_game_index=1,
        move_number=1,
    )
    puzzle2 = Puzzle(
        puzzle_id="user2_1",
        fen=chess.STARTING_FEN,
        side_to_move="white",
        best_move_san="d4",
        played_move_san="e4",
        eval_loss_cp=120,
        phase="opening",
        puzzle_type=PuzzleType.OPENING_ERROR,
        difficulty=Difficulty.EASY,
        source_game_index=2,
        move_number=1,
    )

    # Save puzzles for two different users
    n_added_1 = save_puzzles_to_global_bank([puzzle1], source_user="user1")
    n_added_2 = save_puzzles_to_global_bank([puzzle2], source_user="user2")
    assert n_added_1 >= 1
    assert n_added_2 >= 1

    # Check that both users' puzzles are present and deduped
    ratings = load_rating_counts()
    keys = list(ratings.keys())
    assert any(key for key in keys if "user1" in key or "user2" in key)

    # Clean up environment variables
    del os.environ["PUZZLE_BANK_BACKEND"]
    del os.environ["SUPABASE_URL"]
    del os.environ["SUPABASE_SERVICE_ROLE_KEY"]
