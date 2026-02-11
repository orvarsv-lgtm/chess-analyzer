"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "ok", "service": "chess-analyzer-api", "version": "2.0.0"}


@router.get("/health")
async def health():
    return {"status": "healthy"}
