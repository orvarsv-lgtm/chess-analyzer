"""
Webhook routes – Paddle payment webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Paddle webhook events:
    - subscription.created  → activate Pro
    - subscription.updated  → update tier
    - subscription.canceled → downgrade to Free
    - subscription.paused   → downgrade to Free
    """
    settings = get_settings()
    body = await request.body()

    # ── Verify webhook signature ──
    signature = request.headers.get("Paddle-Signature", "")
    if settings.paddle_webhook_secret and signature:
        # Paddle v2 webhook signature verification
        parts = dict(p.split("=", 1) for p in signature.split(";") if "=" in p)
        ts = parts.get("ts", "")
        h1 = parts.get("h1", "")

        signed_payload = f"{ts}:{body.decode()}"
        expected = hmac.new(
            settings.paddle_webhook_secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(h1, expected):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # ── Parse event ──
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event_type", "")
    data = event.get("data", {})

    # Get customer email from Paddle event
    customer = data.get("customer", {})
    email = customer.get("email", "").lower().strip()
    paddle_customer_id = customer.get("id", "")
    subscription_id = data.get("id", "")

    if not email:
        # Can't map to user without email
        return {"received": True, "action": "skipped", "reason": "no email"}

    # Find user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return {"received": True, "action": "skipped", "reason": "user not found"}

    # ── Process event ──
    action = "none"

    if event_type in ("subscription.created", "subscription.activated"):
        user.subscription_tier = "pro"
        user.paddle_customer_id = paddle_customer_id
        user.paddle_subscription_id = subscription_id
        action = "activated_pro"

    elif event_type == "subscription.updated":
        # Check if still active
        status = data.get("status", "")
        if status == "active":
            user.subscription_tier = "pro"
            action = "updated_pro"
        elif status in ("canceled", "paused"):
            user.subscription_tier = "free"
            action = "downgraded_free"

    elif event_type in ("subscription.canceled", "subscription.paused"):
        user.subscription_tier = "free"
        action = "downgraded_free"

    db.add(user)
    await db.commit()

    return {"received": True, "action": action, "event_type": event_type}
