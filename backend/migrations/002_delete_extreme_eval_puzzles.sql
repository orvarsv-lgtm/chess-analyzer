-- Migration 002: Remove puzzles where the position was already completely winning
-- (one side up 600+ centipawns). These are trivial and not useful for training.
--
-- We identify these by checking if the FEN position's eval (stored in move_evaluations)
-- was extreme at puzzle creation time. Since puzzles store fen and we can cross-reference
-- with move_evaluations.fen_before, we delete puzzles that match extreme eval positions.
--
-- Simpler approach: delete puzzles where eval_loss_cp is very high (>= 600) 
-- OR where the puzzle's source move had an extreme eval. Since we don't have
-- eval_before stored on puzzles directly, we use the move_evaluations table.

DELETE FROM puzzle_attempts
WHERE puzzle_id IN (
    SELECT p.id FROM puzzles p
    JOIN move_evaluations me ON me.game_id = p.source_game_id
        AND me.fen_before = p.fen
    WHERE ABS(me.eval_before) >= 600
);

DELETE FROM puzzles
WHERE id IN (
    SELECT p.id FROM puzzles p
    JOIN move_evaluations me ON me.game_id = p.source_game_id
        AND me.fen_before = p.fen
    WHERE ABS(me.eval_before) >= 600
);
