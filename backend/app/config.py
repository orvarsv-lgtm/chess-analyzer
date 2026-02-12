"""
Chess Analyzer Backend - Configuration

Loads settings from environment variables with Pydantic validation.
"""

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ─── Database ───
    database_url: str = "postgresql+asyncpg://localhost:5432/chess_analyzer"

    # ─── Supabase ───
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    # ─── Auth ───
    nextauth_secret: str = "dev-secret-change-me"

    # ─── Stockfish ───
    stockfish_path: str = "/usr/games/stockfish"
    default_analysis_depth: int = 12
    deep_analysis_depth: int = 18

    # ─── Redis ───
    redis_url: str = "redis://localhost:6379"

    # ─── Paddle ───
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""
    paddle_price_pro: str = ""

    # ─── OpenAI ───
    openai_api_key: str = ""

    # ─── App ───
    cors_origins: str = "http://localhost:3000"
    env: str = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url_async(self) -> str:
        """Normalize DATABASE_URL for SQLAlchemy async engine.

        Accepts Railway-style URLs like:
        - postgres://...
        - postgresql://...
        and converts them to:
        - postgresql+asyncpg://...
        """
        url = self.database_url or ""
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
