"""Supabase Auth helpers for Streamlit.

Uses magic-link (email OTP) authentication.
Stores user session in st.session_state['user'].
"""
from __future__ import annotations

import os
from typing import Any, Optional

import streamlit as st

# Lazy import to avoid crashing if supabase not installed
_supabase_client = None


def _get_supabase_client():
    """Get or create a Supabase client using anon key (for auth)."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client
    except ImportError:
        return None

    # Try to get from Streamlit secrets first, then env vars
    url = None
    key = None

    try:
        secrets = st.secrets
        url = secrets.get("SUPABASE_URL")
        # For auth, prefer anon key; fall back to service role if anon not set
        key = secrets.get("SUPABASE_ANON_KEY") or secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    except Exception:
        pass

    if not url:
        url = os.getenv("SUPABASE_URL", "").strip()
    if not key:
        key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        key = key.strip()

    if not url or not key:
        return None

    try:
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception:
        return None


def get_current_user() -> Optional[dict]:
    """Return the currently logged-in user from session state, or None."""
    return st.session_state.get("user")


def is_logged_in() -> bool:
    """Check if a user is currently logged in."""
    return get_current_user() is not None


def sign_in_with_magic_link(email: str) -> tuple[bool, str]:
    """Send a magic link to the user's email.

    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Supabase not configured. Check SUPABASE_URL and SUPABASE_ANON_KEY."

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return False, "Please enter a valid email address."

    try:
        # Send magic link (OTP via email)
        response = client.auth.sign_in_with_otp({"email": email})
        return True, f"✅ Magic link sent to **{email}**! Check your inbox and click the link to sign in."
    except Exception as e:
        err_msg = str(e)
        if "rate" in err_msg.lower():
            return False, "Too many requests. Please wait a minute before trying again."
        return False, f"Failed to send magic link: {err_msg}"


def sign_in_with_password(email: str, password: str) -> tuple[bool, str]:
    """Sign in with email and password.

    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Supabase not configured. Check SUPABASE_URL and SUPABASE_ANON_KEY."

    email = (email or "").strip().lower()
    password = (password or "").strip()

    if not email or "@" not in email:
        return False, "Please enter a valid email address."
    if not password:
        return False, "Please enter your password."

    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if response.user:
            st.session_state["user"] = {
                "id": response.user.id,
                "email": response.user.email,
                "created_at": str(response.user.created_at) if response.user.created_at else None,
            }
            st.session_state["supabase_session"] = {
                "access_token": response.session.access_token if response.session else None,
                "refresh_token": response.session.refresh_token if response.session else None,
            }
            return True, f"✅ Welcome back, **{email}**!"
        return False, "Invalid credentials."
    except Exception as e:
        err_msg = str(e)
        if "invalid" in err_msg.lower() or "credentials" in err_msg.lower():
            return False, "Invalid email or password."
        return False, f"Sign in failed: {err_msg}"


def sign_up_with_password(email: str, password: str) -> tuple[bool, str]:
    """Create a new account with email and password.

    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Supabase not configured. Check SUPABASE_URL and SUPABASE_ANON_KEY."

    email = (email or "").strip().lower()
    password = (password or "").strip()

    if not email or "@" not in email:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    try:
        response = client.auth.sign_up({"email": email, "password": password})
        if response.user:
            # Some Supabase configs require email confirmation
            if response.user.email_confirmed_at:
                st.session_state["user"] = {
                    "id": response.user.id,
                    "email": response.user.email,
                    "created_at": str(response.user.created_at) if response.user.created_at else None,
                }
                return True, f"✅ Account created! Welcome, **{email}**!"
            else:
                return True, f"✅ Account created! Please check **{email}** for a confirmation link."
        return False, "Failed to create account."
    except Exception as e:
        err_msg = str(e)
        if "already" in err_msg.lower() or "exists" in err_msg.lower():
            return False, "An account with this email already exists. Try signing in instead."
        return False, f"Sign up failed: {err_msg}"


def verify_otp(email: str, token: str) -> tuple[bool, str]:
    """Verify OTP token from magic link or email confirmation.

    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Supabase not configured."

    email = (email or "").strip().lower()
    token = (token or "").strip()

    if not email or not token:
        return False, "Email and token are required."

    try:
        response = client.auth.verify_otp({"email": email, "token": token, "type": "email"})
        if response.user:
            st.session_state["user"] = {
                "id": response.user.id,
                "email": response.user.email,
                "created_at": str(response.user.created_at) if response.user.created_at else None,
            }
            st.session_state["supabase_session"] = {
                "access_token": response.session.access_token if response.session else None,
                "refresh_token": response.session.refresh_token if response.session else None,
            }
            return True, f"✅ Signed in as **{email}**!"
        return False, "Invalid or expired token."
    except Exception as e:
        return False, f"Verification failed: {str(e)}"


def sign_out() -> tuple[bool, str]:
    """Sign out the current user.

    Returns (success, message).
    """
    client = _get_supabase_client()

    # Clear local session state regardless of API call success
    st.session_state.pop("user", None)
    st.session_state.pop("supabase_session", None)

    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass  # Ignore errors; we've cleared local state

    return True, "✅ Signed out successfully."


def render_auth_sidebar() -> None:
    """Render the authentication UI in the sidebar."""
    with st.sidebar:
        st.markdown("---")

        user = get_current_user()

        if user:
            # Logged in state
            st.success(f"👤 **{user.get('email', 'User')}**")
            if st.button("🚪 Sign Out", use_container_width=True, key="auth_signout_btn"):
                success, msg = sign_out()
                if success:
                    st.rerun()
        else:
            # Login form
            st.subheader("🔐 Sign In")

            auth_mode = st.radio(
                "Method",
                ["Password", "Magic Link"],
                horizontal=True,
                key="auth_mode_radio",
                label_visibility="collapsed",
            )

            email = st.text_input("Email", key="auth_email_input", placeholder="you@example.com")

            if auth_mode == "Password":
                password = st.text_input("Password", type="password", key="auth_pass_input")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Sign In", use_container_width=True, key="auth_signin_btn"):
                        success, msg = sign_in_with_password(email, password)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                with col2:
                    if st.button("Sign Up", use_container_width=True, key="auth_signup_btn"):
                        success, msg = sign_up_with_password(email, password)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            else:  # Magic Link mode
                if st.button("📧 Send Magic Link", use_container_width=True, key="auth_magic_btn"):
                    success, msg = sign_in_with_magic_link(email)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

                # OTP verification (for users who clicked the link and got redirected)
                with st.expander("Have a code? Enter it here"):
                    token = st.text_input("6-digit code", key="auth_otp_input", max_chars=6)
                    if st.button("Verify", key="auth_verify_btn"):
                        success, msg = verify_otp(email, token)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                        if success:
                            st.success(msg)
                            if "confirmation" not in msg.lower():
                                st.rerun()
                        else:
                            st.error(msg)

        st.markdown("---")


def require_auth(feature_name: str = "this feature") -> bool:
    """Check if user is logged in; if not, show a message and return False.

    Usage:
        if not require_auth("Premium Coach"):
            return
        # ... rest of the feature code
    """
    if is_logged_in():
        return True

    st.warning(f"🔒 **Sign in required** to access {feature_name}.")
    st.info("Use the sidebar to sign in with your email.")
    return False
