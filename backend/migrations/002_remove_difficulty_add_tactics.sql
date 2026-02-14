-- Migration 002: Remove puzzle difficulty, enhance tactic tagging
-- Run with: psql $DATABASE_URL -f migrations/002_remove_difficulty_add_tactics.sql

-- 1. Make difficulty nullable (backward compat) and set default
ALTER TABLE puzzles ALTER COLUMN difficulty SET DEFAULT 'standard';
ALTER TABLE puzzles ALTER COLUMN difficulty DROP NOT NULL;

-- 2. Drop the difficulty index (no longer used for filtering)
DROP INDEX IF EXISTS ix_puzzles_difficulty;

-- 3. Update all existing difficulty values to 'standard'
UPDATE puzzles SET difficulty = 'standard' WHERE difficulty IS NOT NULL AND difficulty != 'standard';

-- 4. Ensure themes GIN index exists (for tactic-based filtering)
-- (Already exists from 001, but be safe)
CREATE INDEX IF NOT EXISTS ix_puzzles_themes ON puzzles USING GIN (themes);

-- 5. Add index on puzzle_type for faster filtering
CREATE INDEX IF NOT EXISTS ix_puzzles_phase ON puzzles (phase);

-- Done
