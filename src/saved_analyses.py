"""Save and load user analyses to/from Supabase.

Table schema (create in Supabase):
CREATE TABLE saved_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'lichess',
    num_games INT NOT NULL,
    analysis_depth INT NOT NULL DEFAULT 15,
    analysis_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_saved_analyses_user_id ON saved_analyses(user_id);
CREATE INDEX idx_saved_analyses_username ON saved_analyses(username);

-- RLS policies
ALTER TABLE saved_analyses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own analyses"
    ON saved_analyses FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own analyses"
    ON saved_analyses FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own analyses"
    ON saved_analyses FOR DELETE
    USING (auth.uid() = user_id);
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional, List, Dict

import streamlit as st


def _get_supabase_client():
    """Get Supabase client (reuse from auth module pattern)."""
    try:
        from supabase import create_client
    except ImportError:
        return None

    url = None
    key = None

    try:
        secrets = st.secrets
        url = secrets.get("SUPABASE_URL")
        key = secrets.get("SUPABASE_SERVICE_ROLE_KEY") or secrets.get("SUPABASE_ANON_KEY")
    except Exception:
        pass

    if not url:
        url = os.getenv("SUPABASE_URL", "").strip()
    if not key:
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
        key = key.strip()

    if not url or not key:
        return None

    try:
        return create_client(url, key)
    except Exception:
        return None


def save_analysis(
    user_id: str,
    username: str,
    source: str,
    num_games: int,
    analysis_depth: int,
    analysis_data: Dict[str, Any],
) -> tuple[bool, str]:
    """Save an analysis for a user.
    
    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Database not configured."

    if not user_id:
        return False, "Must be signed in to save analyses."

    try:
        # Check if analysis for this user/username combo already exists
        existing = client.table("saved_analyses").select("id").eq("user_id", user_id).eq("username", username.lower()).execute()
        
        record = {
            "user_id": user_id,
            "username": username.lower(),
            "source": source,
            "num_games": num_games,
            "analysis_depth": analysis_depth,
            "analysis_data": analysis_data,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if existing.data:
            # Update existing
            client.table("saved_analyses").update(record).eq("id", existing.data[0]["id"]).execute()
            return True, f"✅ Analysis for '{username}' updated."
        else:
            # Insert new
            record["created_at"] = datetime.utcnow().isoformat()
            client.table("saved_analyses").insert(record).execute()
            return True, f"✅ Analysis for '{username}' saved."

    except Exception as e:
        return False, f"Failed to save: {str(e)}"


def list_saved_analyses(user_id: str) -> List[Dict[str, Any]]:
    """List all saved analyses for a user.
    
    Returns list of analysis summaries (without full data).
    """
    client = _get_supabase_client()
    if not client or not user_id:
        return []

    try:
        result = client.table("saved_analyses").select(
            "id, username, source, num_games, analysis_depth, created_at, updated_at"
        ).eq("user_id", user_id).order("updated_at", desc=True).execute()
        
        return result.data or []
    except Exception:
        return []


def load_analysis(user_id: str, analysis_id: str) -> Optional[Dict[str, Any]]:
    """Load a specific saved analysis.
    
    Returns the full analysis data or None.
    """
    client = _get_supabase_client()
    if not client or not user_id:
        return None

    try:
        result = client.table("saved_analyses").select("*").eq("id", analysis_id).eq("user_id", user_id).single().execute()
        return result.data
    except Exception:
        return None


def delete_analysis(user_id: str, analysis_id: str) -> tuple[bool, str]:
    """Delete a saved analysis.
    
    Returns (success, message).
    """
    client = _get_supabase_client()
    if not client:
        return False, "Database not configured."

    if not user_id:
        return False, "Must be signed in."

    try:
        client.table("saved_analyses").delete().eq("id", analysis_id).eq("user_id", user_id).execute()
        return True, "✅ Analysis deleted."
    except Exception as e:
        return False, f"Failed to delete: {str(e)}"


def render_load_analysis_ui() -> Optional[Dict[str, Any]]:
    """Render UI for loading a previous analysis.
    
    Returns the loaded analysis data if user selects one, else None.
    """
    # Import translation function
    try:
        from src.translations import t
    except ImportError:
        def t(key): return key
    
    user = st.session_state.get("user")
    if not user:
        return None

    user_id = user.get("id")
    if not user_id:
        return None

    saved = list_saved_analyses(user_id)
    if not saved:
        st.info(t("no_saved_analyses"))
        return None

    st.markdown(f"#### 📂 {t('saved_analyses')}")
    
    # Format options
    options = []
    for s in saved:
        updated = s.get("updated_at", "")[:10]
        label = f"{s['username']} ({s['num_games']} {t('games')}, {t('depth')} {s['analysis_depth']}) - {updated}"
        options.append((s["id"], label, s["username"]))

    selected_idx = st.selectbox(
        t("load_analysis"),
        range(len(options)),
        format_func=lambda i: options[i][1],
        key="load_analysis_select",
    )

    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.button(f"📥 {t('load_analysis')}", use_container_width=True, key="load_analysis_btn"):
            analysis_id = options[selected_idx][0]
            loaded = load_analysis(user_id, analysis_id)
            if loaded:
                st.success(f"Loaded analysis for '{loaded['username']}'")
                return loaded
            else:
                st.error(t("error"))
    
    with col2:
        if st.button("🗑️", key="delete_analysis_btn", help=t("delete")):
