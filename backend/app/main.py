"""
Chess Analyzer Backend - FastAPI Application

Main application factory with middleware, routes, and lifecycle events.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.session import engine, async_session
from app.db.models import Base
from app.routes import games, analysis, puzzles, insights, users, webhooks, health, coach, anonymous


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # Create tables if they don't exist (dev only; use Alembic in prod)
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    yield

    # Cleanup
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Chess Analyzer API",
        version="2.0.0",
        description="Backend API for Chess Analyzer – game analysis, puzzles, coaching",
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──
    app.include_router(health.router, tags=["health"])
    app.include_router(anonymous.router, prefix="/api/anonymous", tags=["anonymous"])
    app.include_router(games.router, prefix="/api/games", tags=["games"])
    app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
    app.include_router(puzzles.router, prefix="/api/puzzles", tags=["puzzles"])
    app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
    app.include_router(coach.router, prefix="/api/coach", tags=["coach"])

    return app


app = create_app()
