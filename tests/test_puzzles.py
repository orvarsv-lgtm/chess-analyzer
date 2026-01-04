"""
Tests for Chess Puzzle Module

Tests puzzle generation, FEN legality, move validation, and difficulty classification.
All tests are deterministic - no randomness.
"""

import unittest
import chess

from puzzles.puzzle_types import (
    Puzzle,
    PuzzleSession,
    PuzzleAttempt,
    PuzzleType,
    Difficulty,
)
from puzzles.difficulty import (
    classify_difficulty,
    get_difficulty_emoji,
    get_difficulty_description,
    EASY_CP_THRESHOLD,
    MEDIUM_CP_THRESHOLD,
    HARD_CP_THRESHOLD,
)
from puzzles.puzzle_engine import (
    PuzzleGenerator,
    generate_puzzles_from_games,
    get_puzzle_stats,
    _classify_puzzle_type,
    generate_puzzle_explanation,
)
from puzzles.puzzle_ui import (
    validate_move,
    check_puzzle_answer,
    get_legal_moves_display,
)


class TestPuzzleTypes(unittest.TestCase):
    """Tests for puzzle data types."""
    
    def test_puzzle_creation(self):
        """Test creating a puzzle with all required fields."""
        puzzle = Puzzle(
            puzzle_id="1_5_white",
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            side_to_move="black",
            best_move_san="e5",
            played_move_san="a6",
            eval_loss_cp=150,
            phase="opening",
            puzzle_type=PuzzleType.OPENING_ERROR,
            difficulty=Difficulty.MEDIUM,
            source_game_index=1,
            move_number=5,
        )
        
        self.assertEqual(puzzle.puzzle_id, "1_5_white")
        self.assertEqual(puzzle.side_to_move, "black")
        self.assertEqual(puzzle.eval_loss_cp, 150)
        self.assertEqual(puzzle.puzzle_type, PuzzleType.OPENING_ERROR)
        self.assertEqual(puzzle.difficulty, Difficulty.MEDIUM)
    
    def test_puzzle_serialization(self):
        """Test puzzle to_dict and from_dict roundtrip."""
        original = Puzzle(
            puzzle_id="test_1",
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            side_to_move="white",
            best_move_san="e4",
            played_move_san="a3",
            eval_loss_cp=200,
            phase="opening",
            puzzle_type=PuzzleType.OPENING_ERROR,
            difficulty=Difficulty.MEDIUM,
            source_game_index=1,
            move_number=1,
            eval_before=0,
            eval_after=-200,
        )
        
        # Convert to dict and back
        data = original.to_dict()
        restored = Puzzle.from_dict(data)
        
        self.assertEqual(original.puzzle_id, restored.puzzle_id)
        self.assertEqual(original.fen, restored.fen)
        self.assertEqual(original.best_move_san, restored.best_move_san)
        self.assertEqual(original.puzzle_type, restored.puzzle_type)
        self.assertEqual(original.difficulty, restored.difficulty)
    
    def test_puzzle_session_initialization(self):
        """Test puzzle session creation and state management."""
        puzzles = [
            Puzzle(
                puzzle_id=f"p_{i}",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300,
                phase="opening",
                puzzle_type=PuzzleType.OPENING_ERROR,
                difficulty=Difficulty.EASY,
                source_game_index=1,
                move_number=i,
            )
            for i in range(10)
        ]
        
        session = PuzzleSession(puzzles=puzzles)
        
        self.assertEqual(session.total_puzzles, 10)
        self.assertEqual(session.current_index, 0)
        self.assertEqual(session.solved_count, 0)
        self.assertIsNotNone(session.current_puzzle)
    
    def test_puzzle_session_free_limit(self):
        """Test free tier puzzle limit enforcement."""
        puzzles = [
            Puzzle(
                puzzle_id=f"p_{i}",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300,
                phase="opening",
                puzzle_type=PuzzleType.OPENING_ERROR,
                difficulty=Difficulty.EASY,
                source_game_index=1,
                move_number=i,
            )
            for i in range(10)
        ]
        
        # Free user session
        session = PuzzleSession(puzzles=puzzles, is_premium=False)
        
        self.assertEqual(session.available_puzzle_count, 5)  # MAX_FREE_PUZZLES
        self.assertFalse(session.is_at_limit)
        
        # Advance to limit
        for _ in range(5):
            session.advance_to_next()
        
        self.assertTrue(session.is_at_limit)
        self.assertFalse(session.advance_to_next())  # Can't advance past limit
    
    def test_puzzle_session_premium(self):
        """Test premium user has no puzzle limit."""
        puzzles = [
            Puzzle(
                puzzle_id=f"p_{i}",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300,
                phase="opening",
                puzzle_type=PuzzleType.OPENING_ERROR,
                difficulty=Difficulty.EASY,
                source_game_index=1,
                move_number=i,
            )
            for i in range(10)
        ]
        
        # Premium user session
        session = PuzzleSession(puzzles=puzzles, is_premium=True)
        
        self.assertEqual(session.available_puzzle_count, 10)  # All puzzles
        
        # Can advance through all puzzles
        for _ in range(9):
            self.assertTrue(session.advance_to_next())
    
    def test_puzzle_attempt_recording(self):
        """Test recording puzzle attempts."""
        puzzles = [
            Puzzle(
                puzzle_id="test_puzzle",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300,
                phase="opening",
                puzzle_type=PuzzleType.OPENING_ERROR,
                difficulty=Difficulty.EASY,
                source_game_index=1,
                move_number=1,
            )
        ]
        
        session = PuzzleSession(puzzles=puzzles)
        
        # Record incorrect attempt
        attempt1 = session.record_attempt("a4", is_correct=False)
        self.assertEqual(attempt1.attempt_number, 1)
        self.assertFalse(attempt1.is_correct)
        self.assertEqual(session.solved_count, 0)
        
        # Record correct attempt
        attempt2 = session.record_attempt("e4", is_correct=True)
        self.assertEqual(attempt2.attempt_number, 2)
        self.assertTrue(attempt2.is_correct)
        self.assertEqual(session.solved_count, 1)


class TestDifficultyClassification(unittest.TestCase):
    """Tests for difficulty classification logic."""
    
    def test_easy_classification(self):
        """Test easy difficulty for high eval loss with clear tactic."""
        # Position where Nxe5 is a capture - captures are easier
        fen = "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
        
        # 350+ cp loss with capture = easy
        difficulty = classify_difficulty(
            fen=fen,
            best_move_san="Nxe5",  # Capture makes it easier
            eval_loss_cp=350,
            phase="opening",
        )
        
        self.assertEqual(difficulty, Difficulty.EASY)
    
    def test_medium_classification(self):
        """Test medium difficulty for moderate eval loss."""
        # Position with a check opportunity
        fen = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
        
        difficulty = classify_difficulty(
            fen=fen,
            best_move_san="Qh4+",  # Check makes it easier
            eval_loss_cp=220,
            phase="opening",
        )
        
        # Check moves get a difficulty reduction
        self.assertIn(difficulty, [Difficulty.EASY, Difficulty.MEDIUM])
    
    def test_hard_classification(self):
        """Test hard difficulty for low eval loss."""
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        
        difficulty = classify_difficulty(
            fen=fen,
            best_move_san="d3",  # Quiet move
            eval_loss_cp=120,
            phase="middlegame",
        )
        
        # Quiet move with lower eval loss = harder
        self.assertIn(difficulty, [Difficulty.MEDIUM, Difficulty.HARD])
    
    def test_check_move_easier(self):
        """Test that check moves are classified as easier."""
        # Position where Qh4+ is check
        fen = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
        
        difficulty = classify_difficulty(
            fen=fen,
            best_move_san="Qh4+",
            eval_loss_cp=200,
            phase="opening",
        )
        
        # Check moves should trend easier
        self.assertIn(difficulty, [Difficulty.EASY, Difficulty.MEDIUM])
    
    def test_difficulty_emoji(self):
        """Test difficulty emoji mapping."""
        self.assertEqual(get_difficulty_emoji(Difficulty.EASY), "🟢")
        self.assertEqual(get_difficulty_emoji(Difficulty.MEDIUM), "🟡")
        self.assertEqual(get_difficulty_emoji(Difficulty.HARD), "🔴")
    
    def test_difficulty_description(self):
        """Test difficulty descriptions exist."""
        for diff in Difficulty:
            desc = get_difficulty_description(diff)
            self.assertIsInstance(desc, str)
            self.assertTrue(len(desc) > 0)


class TestPuzzleGeneration(unittest.TestCase):
    """Tests for puzzle generation from analyzed games."""
    
    def test_puzzle_generator_init(self):
        """Test puzzle generator initialization."""
        generator = PuzzleGenerator(min_eval_loss=150)
        self.assertEqual(generator.min_eval_loss, 150)
    
    def test_generate_from_empty_game(self):
        """Test generating from empty move list."""
        generator = PuzzleGenerator()
        puzzles = generator.generate_from_game(
            game_index=1,
            move_evals=[],
        )
        self.assertEqual(len(puzzles), 0)
    
    def test_generate_from_perfect_game(self):
        """Test no puzzles from perfect play (no mistakes)."""
        # All moves have 0 cp_loss
        move_evals = [
            {"san": "e4", "cp_loss": 0, "phase": "opening", "move_num": 1},
            {"san": "e5", "cp_loss": 0, "phase": "opening", "move_num": 1},
            {"san": "Nf3", "cp_loss": 0, "phase": "opening", "move_num": 2},
        ]
        
        generator = PuzzleGenerator()
        puzzles = generator.generate_from_game(
            game_index=1,
            move_evals=move_evals,
        )
        
        self.assertEqual(len(puzzles), 0)
    
    def test_puzzle_stats_empty(self):
        """Test puzzle stats with empty list."""
        stats = get_puzzle_stats([])
        
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["by_difficulty"], {})
        self.assertEqual(stats["avg_eval_loss"], 0)
    
    def test_puzzle_stats_populated(self):
        """Test puzzle stats with puzzles."""
        puzzles = [
            Puzzle(
                puzzle_id=f"p_{i}",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300 if i < 2 else 150,
                phase="opening" if i < 1 else "middlegame",
                puzzle_type=PuzzleType.MISSED_TACTIC,
                difficulty=Difficulty.EASY if i < 2 else Difficulty.MEDIUM,
                source_game_index=1,
                move_number=i,
            )
            for i in range(5)
        ]
        
        stats = get_puzzle_stats(puzzles)
        
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["by_difficulty"]["easy"], 2)
        self.assertEqual(stats["by_difficulty"]["medium"], 3)
        self.assertGreater(stats["avg_eval_loss"], 0)


class TestMoveValidation(unittest.TestCase):
    """Tests for move validation logic."""
    
    def test_validate_san_move(self):
        """Test validating SAN notation moves."""
        board = chess.Board()  # Starting position
        
        # Valid moves
        is_valid, move, msg = validate_move(board, "e4")
        self.assertTrue(is_valid)
        self.assertIsNotNone(move)
        
        is_valid, move, msg = validate_move(board, "Nf3")
        self.assertTrue(is_valid)
        self.assertIsNotNone(move)
    
    def test_validate_uci_move(self):
        """Test validating UCI notation moves."""
        board = chess.Board()
        
        is_valid, move, msg = validate_move(board, "e2e4")
        self.assertTrue(is_valid)
        self.assertIsNotNone(move)
        
        is_valid, move, msg = validate_move(board, "g1f3")
        self.assertTrue(is_valid)
        self.assertIsNotNone(move)
    
    def test_validate_illegal_move(self):
        """Test rejecting illegal moves."""
        board = chess.Board()
        
        # Illegal pawn move
        is_valid, move, msg = validate_move(board, "e5")
        self.assertFalse(is_valid)
        self.assertIsNone(move)
        
        # Invalid notation
        is_valid, move, msg = validate_move(board, "xyz")
        self.assertFalse(is_valid)
    
    def test_validate_empty_input(self):
        """Test handling empty input."""
        board = chess.Board()
        
        is_valid, move, msg = validate_move(board, "")
        self.assertFalse(is_valid)
        self.assertIn("enter", msg.lower())
    
    def test_check_puzzle_answer_correct(self):
        """Test correct puzzle answer."""
        board = chess.Board()
        correct_move = board.parse_san("e4")
        
        is_correct, msg = check_puzzle_answer(board, correct_move, "e4")
        self.assertTrue(is_correct)
        self.assertIn("Correct", msg)
    
    def test_check_puzzle_answer_incorrect(self):
        """Test incorrect puzzle answer."""
        board = chess.Board()
        wrong_move = board.parse_san("d4")
        
        is_correct, msg = check_puzzle_answer(board, wrong_move, "e4")
        self.assertFalse(is_correct)
        self.assertIn("Incorrect", msg)
        self.assertIn("e4", msg)  # Shows correct move
    
    def test_get_legal_moves(self):
        """Test getting legal moves list."""
        board = chess.Board()
        moves = get_legal_moves_display(board)
        
        # Starting position has 20 legal moves
        self.assertEqual(len(moves), 20)
        self.assertIn("e4", moves)
        self.assertIn("Nf3", moves)


class TestFENLegality(unittest.TestCase):
    """Tests for FEN position legality."""
    
    def test_valid_starting_position(self):
        """Test standard starting position FEN."""
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        self.assertTrue(board.is_valid())
    
    def test_valid_midgame_position(self):
        """Test a valid midgame position."""
        fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
        board = chess.Board(fen)
        self.assertTrue(board.is_valid())
    
    def test_valid_endgame_position(self):
        """Test a valid endgame position."""
        fen = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 50"
        board = chess.Board(fen)
        self.assertTrue(board.is_valid())
    
    def test_invalid_fen_rejected(self):
        """Test that invalid FEN is rejected."""
        invalid_fen = "this is not a valid fen"
        with self.assertRaises(Exception):
            chess.Board(invalid_fen)
    
    def test_puzzle_fen_is_legal(self):
        """Test that puzzles have legal FEN positions."""
        # Sample puzzle
        puzzle = Puzzle(
            puzzle_id="test",
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            side_to_move="black",
            best_move_san="e5",
            played_move_san="a6",
            eval_loss_cp=150,
            phase="opening",
            puzzle_type=PuzzleType.OPENING_ERROR,
            difficulty=Difficulty.MEDIUM,
            source_game_index=1,
            move_number=1,
        )
        
        # FEN should be parseable
        board = chess.Board(puzzle.fen)
        self.assertTrue(board.is_valid())
        
        # Best move should be legal in this position
        best_move = board.parse_san(puzzle.best_move_san)
        self.assertIn(best_move, board.legal_moves)


class TestPuzzleTypeClassification(unittest.TestCase):
    """Tests for puzzle type classification."""
    
    def test_opening_error_early_game(self):
        """Test opening error detection for early moves."""
        board = chess.Board()
        best_move = board.parse_san("e4")
        played_move = board.parse_san("a3")
        
        puzzle_type = _classify_puzzle_type(
            board=board,
            best_move=best_move,
            played_move=played_move,
            eval_loss_cp=200,
            phase="opening",
            move_number=3,  # Early move
        )
        
        self.assertEqual(puzzle_type, PuzzleType.OPENING_ERROR)
    
    def test_missed_tactic_capture(self):
        """Test missed tactic detection for captures."""
        # Position where Bxf7+ is winning
        fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
        board = chess.Board(fen)
        best_move = board.parse_san("Bxf7+")
        played_move = board.parse_san("O-O")
        
        puzzle_type = _classify_puzzle_type(
            board=board,
            best_move=best_move,
            played_move=played_move,
            eval_loss_cp=400,
            phase="middlegame",
            move_number=15,
        )
        
        self.assertEqual(puzzle_type, PuzzleType.MISSED_TACTIC)
    
    def test_endgame_technique(self):
        """Test endgame technique detection."""
        # Simple king and pawn endgame
        fen = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 50"
        board = chess.Board(fen)
        best_move = board.parse_san("Kd4")
        played_move = board.parse_san("Kd3")
        
        puzzle_type = _classify_puzzle_type(
            board=board,
            best_move=best_move,
            played_move=played_move,
            eval_loss_cp=150,
            phase="endgame",
            move_number=50,
        )
        
        self.assertEqual(puzzle_type, PuzzleType.ENDGAME_TECHNIQUE)


class TestDeterminism(unittest.TestCase):
    """Tests to verify all puzzle logic is deterministic."""
    
    def test_difficulty_deterministic(self):
        """Test that difficulty classification is deterministic."""
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        
        # Run classification multiple times
        results = []
        for _ in range(10):
            diff = classify_difficulty(
                fen=fen,
                best_move_san="e4",
                eval_loss_cp=250,
                phase="opening",
            )
            results.append(diff)
        
        # All results should be identical
        self.assertEqual(len(set(results)), 1)
    
    def test_puzzle_generation_deterministic(self):
        """Test that puzzle generation is deterministic."""
        move_evals = [
            {"san": "e4", "cp_loss": 0, "phase": "opening", "move_num": 1},
            {"san": "e5", "cp_loss": 0, "phase": "opening", "move_num": 1},
            {"san": "Nf3", "cp_loss": 200, "phase": "opening", "move_num": 2},
        ]
        
        generator = PuzzleGenerator()
        
        # Generate multiple times
        results = []
        for _ in range(5):
            puzzles = generator.generate_from_game(
                game_index=1,
                move_evals=move_evals,
            )
            results.append(len(puzzles))
        
        # All runs should produce same number of puzzles
        self.assertEqual(len(set(results)), 1)
    
    def test_puzzle_session_stats_deterministic(self):
        """Test that session stats are deterministic."""
        puzzles = [
            Puzzle(
                puzzle_id="p_1",
                fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                side_to_move="white",
                best_move_san="e4",
                played_move_san="a3",
                eval_loss_cp=300,
                phase="opening",
                puzzle_type=PuzzleType.MISSED_TACTIC,
                difficulty=Difficulty.EASY,
                source_game_index=1,
                move_number=1,
            )
        ]
        
        session = PuzzleSession(puzzles=puzzles)
        
        # Get stats multiple times
        stats1 = session.get_stats()
        stats2 = session.get_stats()
        
        self.assertEqual(stats1, stats2)


class TestPuzzleExplanation(unittest.TestCase):
    """Tests for puzzle explanation generation."""
    
    def test_explanation_for_capture(self):
        """Test explanation for a winning capture."""
        # Position where white can capture undefended bishop
        fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        board = chess.Board(fen)
        best_move = board.parse_san("Qxf7+")  # Queen takes f7 with check
        
        explanation = generate_puzzle_explanation(
            board=board,
            best_move=best_move,
            eval_loss_cp=500,
            puzzle_type=PuzzleType.MISSED_TACTIC,
            phase="opening",
        )
        
        self.assertIsInstance(explanation, str)
        self.assertTrue(len(explanation) > 0)
        # Should mention check
        self.assertIn("check", explanation.lower())
    
    def test_explanation_for_checkmate(self):
        """Test explanation for checkmate."""
        # Back rank mate position
        fen = "6k1/5ppp/8/8/8/8/8/R3K3 w Q - 0 1"
        board = chess.Board(fen)
        best_move = board.parse_san("Ra8#")
        
        explanation = generate_puzzle_explanation(
            board=board,
            best_move=best_move,
            eval_loss_cp=10000,
            puzzle_type=PuzzleType.MISSED_TACTIC,
            phase="endgame",
        )
        
        self.assertIn("checkmate", explanation.lower())
    
    def test_explanation_deterministic(self):
        """Test that explanations are deterministic."""
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        board = chess.Board(fen)
        best_move = board.parse_san("e5")
        
        explanations = []
        for _ in range(5):
            exp = generate_puzzle_explanation(
                board=board,
                best_move=best_move,
                eval_loss_cp=100,
                puzzle_type=PuzzleType.OPENING_ERROR,
                phase="opening",
            )
            explanations.append(exp)
        
        # All explanations should be identical
        self.assertEqual(len(set(explanations)), 1)


if __name__ == "__main__":
    unittest.main()
