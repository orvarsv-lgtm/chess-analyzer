"""
SQLAlchemy ORM Models – Supabase Postgres

Ported from SQLite schema (src/database.py) and consolidated with
existing Supabase tables. Adds NextAuth.js tables for auth.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════
# NextAuth.js required tables
# ═══════════════════════════════════════════════════════════════


class User(Base):
    """NextAuth.js User table + app-specific fields."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)  # NextAuth uses cuid/uuid strings
    name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=True)
    email_verified = Column(DateTime(timezone=True), nullable=True)
    image = Column(String, nullable=True)

    # ── App-specific fields ──
    subscription_tier = Column(String, default="free")  # 'free' | 'pro'
    paddle_customer_id = Column(String, nullable=True)
    paddle_subscription_id = Column(String, nullable=True)
    ai_coach_reviews_used = Column(Integer, default=0)
    ai_coach_reviews_reset_at = Column(DateTime(timezone=True), nullable=True)
    lichess_username = Column(String, nullable=True)
    chesscom_username = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    daily_warmup_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    games = relationship("Game", back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    """NextAuth.js Account table – OAuth provider links."""

    __tablename__ = "accounts"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # 'oauth' | 'email' | 'credentials'
    provider = Column(String, nullable=False)
    provider_account_id = Column(String, nullable=False)
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    expires_at = Column(Integer, nullable=True)
    token_type = Column(String, nullable=True)
    scope = Column(String, nullable=True)
    id_token = Column(Text, nullable=True)
    session_state = Column(String, nullable=True)

    user = relationship("User", back_populates="accounts")

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_provider_account"),
    )


class Session(Base):
    """NextAuth.js Session table."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    session_token = Column(String, unique=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="sessions")


class VerificationToken(Base):
    """NextAuth.js email verification tokens."""

    __tablename__ = "verification_tokens"

    identifier = Column(String, primary_key=True)
    token = Column(String, primary_key=True)
    expires = Column(DateTime(timezone=True), nullable=False)


# ═══════════════════════════════════════════════════════════════
# Core application tables (ported from SQLite)
# ═══════════════════════════════════════════════════════════════


class Game(Base):
    """Imported chess games (Lichess + Chess.com PGN)."""

    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)  # 'lichess' | 'chess.com'
    platform_game_id = Column(String, nullable=True)  # Platform-specific game ID
    date = Column(DateTime(timezone=True), nullable=False)
    color = Column(String, nullable=False)  # 'white' | 'black'
    result = Column(String, nullable=False)  # 'win' | 'loss' | 'draw'
    opening_name = Column(String, nullable=True)
    eco_code = Column(String, nullable=True)
    time_control = Column(String, nullable=True)
    player_elo = Column(Integer, nullable=True)
    opponent_elo = Column(Integer, nullable=True)
    white_player = Column(String, nullable=True)
    black_player = Column(String, nullable=True)
    moves_count = Column(Integer, nullable=True)
    moves_pgn = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="games")
    analysis = relationship("GameAnalysis", back_populates="game", uselist=False, cascade="all, delete-orphan")
    move_evals = relationship("MoveEvaluation", back_populates="game", cascade="all, delete-orphan")
    puzzles = relationship("Puzzle", back_populates="source_game", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "platform", "platform_game_id", name="uq_game_per_user"),
        Index("ix_games_user_date", "user_id", "date"),
        Index("ix_games_opening", "opening_name"),
    )


class GameAnalysis(Base):
    """Per-game analysis summary (CPL, blunder counts, etc.)."""

    __tablename__ = "game_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False)
    overall_cpl = Column(Float, nullable=True)
    phase_opening_cpl = Column(Float, nullable=True)
    phase_middlegame_cpl = Column(Float, nullable=True)
    phase_endgame_cpl = Column(Float, nullable=True)
    blunders_count = Column(Integer, default=0)
    mistakes_count = Column(Integer, default=0)
    inaccuracies_count = Column(Integer, default=0)
    best_moves_count = Column(Integer, default=0)
    great_moves_count = Column(Integer, default=0)
    brilliant_moves_count = Column(Integer, default=0)
    missed_wins_count = Column(Integer, default=0)
    accuracy = Column(Float, nullable=True)  # chess.com-style win-prob accuracy
    average_move_time = Column(Float, nullable=True)
    time_trouble_blunders = Column(Integer, default=0)
    analysis_depth = Column(Integer, default=12)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    game = relationship("Game", back_populates="analysis")

    __table_args__ = (Index("ix_analysis_game", "game_id"),)


class MoveEvaluation(Base):
    """Move-by-move engine evaluation data."""

    __tablename__ = "move_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    move_number = Column(Integer, nullable=False)
    color = Column(String, nullable=False)
    san = Column(String, nullable=False)
    uci = Column(String, nullable=True)
    cp_loss = Column(Integer, default=0)
    cp_loss_weighted = Column(Float, default=0)
    piece = Column(String, nullable=True)
    phase = Column(String, nullable=True)  # 'opening' | 'middlegame' | 'endgame'
    move_quality = Column(String, nullable=True)  # 'Best' .. 'Blunder'
    blunder_type = Column(String, nullable=True)
    blunder_subtype = Column(String, nullable=True)
    eval_before = Column(Integer, nullable=True)
    eval_after = Column(Integer, nullable=True)
    fen_before = Column(Text, nullable=True)
    best_move_san = Column(String, nullable=True)
    best_move_uci = Column(String, nullable=True)
    win_prob_before = Column(Float, nullable=True)
    win_prob_after = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)  # per-move chess.com-style accuracy
    time_remaining = Column(Float, nullable=True)
    is_mate_before = Column(Boolean, default=False)
    is_mate_after = Column(Boolean, default=False)

    game = relationship("Game", back_populates="move_evals")

    __table_args__ = (
        Index("ix_moves_game", "game_id"),
        Index("ix_moves_quality", "move_quality"),
        Index("ix_moves_phase", "phase"),
    )


class Puzzle(Base):
    """Tactical puzzles generated from user games."""

    __tablename__ = "puzzles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_key = Column(String, unique=True, nullable=False)  # Hash for dedup
    source_game_id = Column(Integer, ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    source_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fen = Column(String, nullable=False)
    side_to_move = Column(String, nullable=False)
    best_move_san = Column(String, nullable=False)
    best_move_uci = Column(String, nullable=True)
    played_move_san = Column(String, nullable=True)
    eval_loss_cp = Column(Integer, nullable=False)
    phase = Column(String, nullable=False)
    puzzle_type = Column(String, nullable=False)
    difficulty = Column(String, nullable=True, default="standard")  # deprecated — kept for compat
    move_number = Column(Integer, nullable=True)
    explanation = Column(Text, nullable=True)
    solution_line = Column(JSONB, default=list)  # Multi-move sequence [uci1, uci2, ...]
    themes = Column(JSONB, default=list)  # Tactical themes array
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_game = relationship("Game", back_populates="puzzles")
    attempts = relationship("PuzzleAttempt", back_populates="puzzle", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_puzzles_type", "puzzle_type"),
        Index("ix_puzzles_phase", "phase"),
        Index("ix_puzzles_themes", "themes", postgresql_using="gin"),
    )


class PuzzleAttempt(Base):
    """Puzzle attempt tracking with spaced repetition (SM-2)."""

    __tablename__ = "puzzle_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_id = Column(Integer, ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    correct = Column(Boolean, nullable=False)
    time_taken = Column(Float, nullable=True)
    attempted_at = Column(DateTime(timezone=True), server_default=func.now())
    next_review_at = Column(DateTime(timezone=True), nullable=True)
    repetition_number = Column(Integer, default=0)
    easiness_factor = Column(Float, default=2.5)

    puzzle = relationship("Puzzle", back_populates="attempts")

    __table_args__ = (
        Index("ix_attempts_user", "user_id"),
        Index("ix_attempts_review", "user_id", "next_review_at"),
    )


class OpeningRepertoire(Base):
    """Aggregated opening statistics per user."""

    __tablename__ = "opening_repertoire"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opening_name = Column(String, nullable=False)
    eco_code = Column(String, nullable=True)
    color = Column(String, nullable=False)
    games_played = Column(Integer, default=0)
    games_won = Column(Integer, default=0)
    games_drawn = Column(Integer, default=0)
    games_lost = Column(Integer, default=0)
    average_cpl = Column(Float, nullable=True)
    early_deviations = Column(Integer, default=0)
    last_played_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "opening_name", "color", name="uq_repertoire"),
        Index("ix_repertoire_user", "user_id"),
    )


class Streak(Base):
    """Win/loss/blunder-free streak tracking."""

    __tablename__ = "streaks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    streak_type = Column(String, nullable=False)  # 'win' | 'loss' | 'blunder_free'
    current_count = Column(Integer, default=0)
    best_count = Column(Integer, default=0)
    context = Column(String, nullable=True)  # JSON extra info
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "streak_type", "context", name="uq_streak"),
        Index("ix_streaks_user", "user_id"),
    )


class AnalysisJob(Base):
    """Background analysis job tracking."""

    __tablename__ = "analysis_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String, nullable=False)  # 'full_analysis' | 'single_game'
    status = Column(String, default="pending")  # 'pending' | 'processing' | 'completed' | 'failed'
    total_games = Column(Integer, default=0)
    games_completed = Column(Integer, default=0)
    result = Column(JSONB, nullable=True)  # Summary when complete
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_jobs_user_status", "user_id", "status"),)


class PopulationStats(Base):
    """Population benchmarking data cache."""

    __tablename__ = "population_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rating_bracket = Column(String, nullable=False)
    stat_type = Column(String, nullable=False)
    stat_value = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("rating_bracket", "stat_type", name="uq_pop_stat"),
        Index("ix_pop_bracket", "rating_bracket"),
    )
