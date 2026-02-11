"""
User routes – Profile, settings, linked accounts.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


class UserProfile(BaseModel):
    id: str
    email: Optional[str]
    name: Optional[str]
    subscription_tier: str
    lichess_username: Optional[str]
    chesscom_username: Optional[str]
    ai_coach_reviews_used: int

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    lichess_username: Optional[str] = None
    chesscom_username: Optional[str] = None
    name: Optional[str] = None


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: User = Depends(require_user),
):
    """Get current user profile."""
    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        subscription_tier=user.subscription_tier,
        lichess_username=user.lichess_username,
        chesscom_username=user.chesscom_username,
        ai_coach_reviews_used=user.ai_coach_reviews_used,
    )


@router.patch("/me", response_model=UserProfile)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile (linked usernames, display name)."""
    if body.lichess_username is not None:
        user.lichess_username = body.lichess_username
    if body.chesscom_username is not None:
        user.chesscom_username = body.chesscom_username
    if body.name is not None:
        user.name = body.name

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        subscription_tier=user.subscription_tier,
        lichess_username=user.lichess_username,
        chesscom_username=user.chesscom_username,
        ai_coach_reviews_used=user.ai_coach_reviews_used,
    )
