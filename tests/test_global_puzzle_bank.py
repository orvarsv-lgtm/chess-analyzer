import os
import chess
from puzzles.puzzle_types import Puzzle, Difficulty, PuzzleType
from puzzles.global_puzzle_store import save_puzzles_to_global_bank, load_global_puzzles

def test_global_puzzle_bank_roundtrip(tmp_path):
    os.environ["PUZZLE_DATA_DIR"] = str(tmp_path)
    # Setup: create a dummy puzzle
    p = Puzzle(
        puzzle_id="test_1",
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
    # Save to global bank
    n_added = save_puzzles_to_global_bank([p], source_user="testuser")
    assert n_added >= 1
    # Load back
    loaded = load_global_puzzles(exclude_source_user=None)
    assert any(x.fen == p.fen and x.best_move_san == p.best_move_san for x in loaded)
