"""
Auth dependency – Verify NextAuth.js JWT session tokens.

The Next.js frontend sends a session token (JWT) in the Authorization header.
This module decodes it using the shared NEXTAUTH_SECRET.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Decode NextAuth.js JWT and return the User row.
    Returns None for unauthenticated requests (public endpoints).
    """
    if credentials is None:
        return None

    settings = get_settings()
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.nextauth_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except JWTError:
        return None

    user_id: Optional[str] = payload.get("sub")
    email: Optional[str] = payload.get("email")
    if user_id is None:
        return None

    # Try to find user by ID first
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    # If not found, try by email
    if user is None and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    # Auto-create user if they don't exist yet (first sign-in via NextAuth)
    if user is None:
        import uuid
        user = User(
            id=str(uuid.uuid4()),
            email=email or user_id,
            name=(email or user_id).split("@")[0] if email or user_id else "User",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Dependency that raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


async def require_pro(
    user: User = Depends(require_user),
) -> User:
    """Dependency that raises 403 if user is not on Pro tier."""
    if user.subscription_tier != "pro":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required",
        )
    return user
