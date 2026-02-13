-- ═══════════════════════════════════════════════════════════
-- Chess Analyzer – Supabase Postgres Schema Migration
-- Run this in the Supabase SQL Editor to create all tables.
-- ═══════════════════════════════════════════════════════════

-- ─── NextAuth.js tables ─────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    email       TEXT UNIQUE,
    email_verified TIMESTAMPTZ,
    image       TEXT,

    -- App-specific
    subscription_tier   TEXT NOT NULL DEFAULT 'free',
    paddle_customer_id  TEXT,
    paddle_subscription_id TEXT,
    ai_coach_reviews_used   INTEGER NOT NULL DEFAULT 0,
    ai_coach_reviews_reset_at TIMESTAMPTZ,
    lichess_username    TEXT,
    chesscom_username   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                TEXT NOT NULL,
    provider            TEXT NOT NULL,
    provider_account_id TEXT NOT NULL,
    refresh_token       TEXT,
    access_token        TEXT,
    expires_at          INTEGER,
    token_type          TEXT,
    scope               TEXT,
    id_token            TEXT,
    session_state       TEXT,
    UNIQUE(provider, provider_account_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    session_token TEXT UNIQUE NOT NULL,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_tokens (
    identifier TEXT NOT NULL,
    token      TEXT NOT NULL,
    expires    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);

-- ─── Games ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS games (
    id               SERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform         TEXT NOT NULL,           -- 'lichess' | 'chess.com'
    platform_game_id TEXT,
    date             TIMESTAMPTZ NOT NULL,
    color            TEXT NOT NULL,           -- 'white' | 'black'
    result           TEXT NOT NULL,           -- 'win' | 'loss' | 'draw'
    opening_name     TEXT,
    eco_code         TEXT,
    time_control     TEXT,
    player_elo       INTEGER,
    opponent_elo     INTEGER,
    white_player     TEXT,
    black_player     TEXT,
    moves_count      INTEGER,
    moves_pgn        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, platform, platform_game_id)
);

CREATE INDEX IF NOT EXISTS ix_games_user_date ON games(user_id, date DESC);
CREATE INDEX IF NOT EXISTS ix_games_opening ON games(opening_name);

-- ─── Game Analysis ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS game_analysis (
    id                    SERIAL PRIMARY KEY,
    game_id               INTEGER UNIQUE NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    overall_cpl           REAL,
    phase_opening_cpl     REAL,
    phase_middlegame_cpl  REAL,
    phase_endgame_cpl     REAL,
    blunders_count        INTEGER NOT NULL DEFAULT 0,
    mistakes_count        INTEGER NOT NULL DEFAULT 0,
    inaccuracies_count    INTEGER NOT NULL DEFAULT 0,
    best_moves_count      INTEGER NOT NULL DEFAULT 0,
    great_moves_count     INTEGER NOT NULL DEFAULT 0,
    brilliant_moves_count INTEGER NOT NULL DEFAULT 0,
    missed_wins_count     INTEGER NOT NULL DEFAULT 0,
    accuracy              REAL,
    average_move_time     REAL,
    time_trouble_blunders INTEGER NOT NULL DEFAULT 0,
    analysis_depth        INTEGER NOT NULL DEFAULT 12,
    analyzed_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_analysis_game ON game_analysis(game_id);

-- ─── Move Evaluations ──────────────────────────────────

CREATE TABLE IF NOT EXISTS move_evaluations (
    id              SERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    move_number     INTEGER NOT NULL,
    color           TEXT NOT NULL,
    san             TEXT NOT NULL,
    uci             TEXT,
    cp_loss         INTEGER NOT NULL DEFAULT 0,
    cp_loss_weighted REAL NOT NULL DEFAULT 0,
    piece           TEXT,
    phase           TEXT,            -- 'opening' | 'middlegame' | 'endgame'
    move_quality    TEXT,            -- 'Best'..'Blunder'
    blunder_type    TEXT,
    blunder_subtype TEXT,
    eval_before     INTEGER,
    eval_after      INTEGER,
    fen_before      TEXT,
    best_move_san   TEXT,
    best_move_uci   TEXT,
    win_prob_before REAL,
    win_prob_after  REAL,
    accuracy        REAL,
    time_remaining  REAL,
    is_mate_before  BOOLEAN NOT NULL DEFAULT FALSE,
    is_mate_after   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_moves_game ON move_evaluations(game_id);
CREATE INDEX IF NOT EXISTS ix_moves_quality ON move_evaluations(move_quality);
CREATE INDEX IF NOT EXISTS ix_moves_phase ON move_evaluations(phase);

-- ─── Puzzles ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS puzzles (
    id              SERIAL PRIMARY KEY,
    puzzle_key      TEXT UNIQUE NOT NULL,
    source_game_id  INTEGER REFERENCES games(id) ON DELETE SET NULL,
    source_user_id  TEXT REFERENCES users(id) ON DELETE SET NULL,
    fen             TEXT NOT NULL,
    side_to_move    TEXT NOT NULL,
    best_move_san   TEXT NOT NULL,
    best_move_uci   TEXT,
    played_move_san TEXT,
    eval_loss_cp    INTEGER NOT NULL,
    phase           TEXT NOT NULL,
    puzzle_type     TEXT NOT NULL,
    difficulty      TEXT NOT NULL,       -- 'bronze' | 'silver' | 'gold' | 'platinum'
    move_number     INTEGER,
    explanation     TEXT,
    themes          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_puzzles_type ON puzzles(puzzle_type);
CREATE INDEX IF NOT EXISTS ix_puzzles_difficulty ON puzzles(difficulty);
CREATE INDEX IF NOT EXISTS ix_puzzles_themes ON puzzles USING GIN(themes);

-- ─── Puzzle Attempts ────────────────────────────────────

CREATE TABLE IF NOT EXISTS puzzle_attempts (
    id                SERIAL PRIMARY KEY,
    puzzle_id         INTEGER NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    correct           BOOLEAN NOT NULL,
    time_taken        REAL,
    attempted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_review_at    TIMESTAMPTZ,
    repetition_number INTEGER NOT NULL DEFAULT 0,
    easiness_factor   REAL NOT NULL DEFAULT 2.5
);

CREATE INDEX IF NOT EXISTS ix_attempts_user ON puzzle_attempts(user_id);
CREATE INDEX IF NOT EXISTS ix_attempts_review ON puzzle_attempts(user_id, next_review_at);

-- ─── Opening Repertoire ─────────────────────────────────

CREATE TABLE IF NOT EXISTS opening_repertoire (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opening_name    TEXT NOT NULL,
    eco_code        TEXT,
    color           TEXT NOT NULL,
    games_played    INTEGER NOT NULL DEFAULT 0,
    games_won       INTEGER NOT NULL DEFAULT 0,
    games_drawn     INTEGER NOT NULL DEFAULT 0,
    games_lost      INTEGER NOT NULL DEFAULT 0,
    average_cpl     REAL,
    early_deviations INTEGER NOT NULL DEFAULT 0,
    last_played_at  TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, opening_name, color)
);

CREATE INDEX IF NOT EXISTS ix_repertoire_user ON opening_repertoire(user_id);

-- ─── Streaks ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS streaks (
    id            SERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    streak_type   TEXT NOT NULL,
    current_count INTEGER NOT NULL DEFAULT 0,
    best_count    INTEGER NOT NULL DEFAULT 0,
    context       TEXT,
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, streak_type, context)
);

CREATE INDEX IF NOT EXISTS ix_streaks_user ON streaks(user_id);

-- ─── Analysis Jobs (background queue tracking) ─────────

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_type        TEXT NOT NULL,       -- 'full_analysis' | 'single_game'
    status          TEXT NOT NULL DEFAULT 'pending',
    total_games     INTEGER NOT NULL DEFAULT 0,
    games_completed INTEGER NOT NULL DEFAULT 0,
    result          JSONB,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_jobs_user_status ON analysis_jobs(user_id, status);

-- ─── Population Stats ───────────────────────────────────

CREATE TABLE IF NOT EXISTS population_stats (
    id              SERIAL PRIMARY KEY,
    rating_bracket  TEXT NOT NULL,
    stat_type       TEXT NOT NULL,
    stat_value      REAL NOT NULL,
    sample_size     INTEGER,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(rating_bracket, stat_type)
);

CREATE INDEX IF NOT EXISTS ix_pop_bracket ON population_stats(rating_bracket);

-- ─── Row Level Security (RLS) ───────────────────────────
-- Enable RLS on user-owned tables so Supabase enforces isolation.

ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE move_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE puzzles ENABLE ROW LEVEL SECURITY;
ALTER TABLE puzzle_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_repertoire ENABLE ROW LEVEL SECURITY;
ALTER TABLE streaks ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;

-- Service role (backend) can do everything
CREATE POLICY "Service role full access" ON games FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON game_analysis FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON move_evaluations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON puzzles FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON puzzle_attempts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON opening_repertoire FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON streaks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON analysis_jobs FOR ALL USING (true) WITH CHECK (true);
