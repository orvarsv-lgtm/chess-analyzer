
from __future__ import annotations

import os
import re
import tempfile

import requests
import streamlit as st

from src.lichess_api import fetch_lichess_pgn

ANALYZE_ROUTE = "/analyze_game"

def _get_engine_endpoint() -> tuple[str, str]:
    """Resolve engine URL and API key (Streamlit secrets first, then env)."""
    try:
        url = st.secrets["VPS_ANALYSIS_URL"]
        api_key = st.secrets["VPS_API_KEY"]
        return url, api_key
    except Exception:
        url = os.getenv("VPS_ANALYSIS_URL") or ""
        api_key = os.getenv("VPS_API_KEY") or ""
        return url, api_key


def _post_to_engine(pgn_text: str) -> dict:
    url, api_key = _get_engine_endpoint()
    if not url:
        raise RuntimeError("Engine endpoint not configured")

    endpoint = f"{url.rstrip('/')}{ANALYZE_ROUTE}"
    headers = {"x-api-key": api_key} if api_key else {}
    payload = {"pgn": pgn_text}

    # Temporary debug logging to confirm correct route/payload
    st.write("POSTING TO:", endpoint)
    st.write("Payload keys:", list(payload.keys()))

    resp = requests.post(endpoint, json=payload, timeout=300, headers=headers)

    if resp.status_code == 403:
        raise RuntimeError("VPS Authentication Failed")
    if resp.status_code == 404:
        raise RuntimeError(f"Engine endpoint not found: {endpoint}. Check FastAPI route definition.")
    if not resp.ok:
        raise RuntimeError(f"Engine analysis failed (status {resp.status_code})")

    return resp.json()


def main() -> None:
    st.title("Chess Analyzer (Remote Engine)")

    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"])

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        if st.button("Run analysis"):
            if not username:
                st.error("Please enter a username")
                return
            try:
                pgn_text = fetch_lichess_pgn(username, max_games=50)
            except Exception as e:
                st.error(f"Failed to fetch PGN: {e}")
                st.stop()
            try:
                results = _post_to_engine(pgn_text)
            except Exception as e:
                st.error(str(e))
                st.stop()
            st.json(results)

    else:
        uploaded = st.file_uploader("Upload PGN", type=["pgn"])
        if st.button("Run analysis"):
            if not uploaded:
                st.error("Please upload a PGN file.")
                return

            original_stem = os.path.splitext(uploaded.name or "uploaded")[0]
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", original_stem).strip("_") or "uploaded"

            # Keep temporary file handling only for naming consistency; analysis uses content, not local engine.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pgn", prefix=f"{safe_stem}_") as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name

            try:
                pgn_text = uploaded.getvalue().decode(errors="ignore")
                results = _post_to_engine(pgn_text)
            except Exception as e:
                st.error(str(e))
                st.stop()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            st.json(results)


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

