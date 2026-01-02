
from __future__ import annotations

import os

import requests
import streamlit as st

from src.lichess_api import fetch_lichess_pgn

ANALYZE_ROUTE = "/analyze_game"  # Base URL only; do NOT include this path in secrets/env.

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


def _post_to_engine(pgn_text: str, max_games: int) -> dict:
    url, api_key = _get_engine_endpoint()
    if not url:
        raise RuntimeError("Engine endpoint not configured")

    # Normalize base URL: strip trailing slash and reject accidental paths.
    base = url.rstrip("/")
    # Prevent double /analyze_game in misconfigured secrets/env.
    if "/analyze_game" in base:
        base = base.split("/analyze_game")[0]
    endpoint = f"{base}{ANALYZE_ROUTE}"
    if endpoint.count("/analyze_game") != 1:
        raise RuntimeError(f"Invalid engine endpoint: {endpoint}")
    headers = {"x-api-key": api_key} if api_key else {}
    payload = {"pgn": pgn_text, "max_games": max_games}

    # Temporary debug logging to confirm correct route/payload
    st.write("POSTING TO:", endpoint)
    st.write("Payload keys:", list(payload.keys()))

    resp = requests.post(endpoint, json=payload, timeout=300, headers=headers)

    if resp.status_code == 403:
        raise RuntimeError("VPS Authentication Failed")
    if resp.status_code == 422:
        st.error("Engine rejected request (422 Validation Error)")
        try:
            st.json(resp.json())
        except Exception:
            st.write(resp.text)
        st.stop()
    if resp.status_code == 404:
        raise RuntimeError(f"Engine endpoint not found: {endpoint}. Check FastAPI route definition.")
    if not resp.ok:
        raise RuntimeError(f"Engine analysis failed (status {resp.status_code})")

    return resp.json()


def _validate_engine_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise RuntimeError("Invalid engine response: expected JSON object")
    if not data.get("success"):
        raise RuntimeError("Engine reported failure")
    analysis = data.get("analysis")
    if not analysis:
        raise RuntimeError("Engine returned no analysis")
    for entry in analysis:
        if "move_san" not in entry or "score_cp" not in entry:
            raise RuntimeError("Engine response missing move_san or score_cp")
    return data


def _render_results(data: dict) -> None:
    analysis = data.get("analysis", [])
    st.subheader("Analysis Result")
    st.metric("Total moves analyzed", len(analysis))
    table_rows = [{"move_san": row.get("move_san"), "score_cp": row.get("score_cp")}
                  for row in analysis]
    st.dataframe(table_rows)
    st.success("Analysis completed")


def main() -> None:
    st.title("Chess Analyzer (Remote Engine)")

    if "analysis_result" not in st.session_state:
        st.session_state["analysis_result"] = None

    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"])
    max_games = st.number_input("Max games", min_value=1, max_value=100, value=20, step=1)

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        if st.button("Run analysis"):
            if not username:
                st.error("Please enter a username")
                return
            try:
                pgn_text = fetch_lichess_pgn(username, max_games=max_games)
                results = _post_to_engine(pgn_text, max_games=max_games)
                st.session_state["analysis_result"] = _validate_engine_response(results)
            except Exception as e:
                st.error(str(e))
                st.stop()

    else:
        uploaded = st.file_uploader("Upload PGN", type=["pgn"])
        if st.button("Run analysis"):
            if not uploaded:
                st.error("Please upload a PGN file.")
                return

            try:
                pgn_text = uploaded.read().decode("utf-8", errors="ignore")
                results = _post_to_engine(pgn_text, max_games=max_games)
                st.session_state["analysis_result"] = _validate_engine_response(results)
            except Exception as e:
                st.error(str(e))
                st.stop()

    if st.session_state.get("analysis_result"):
        _render_results(st.session_state["analysis_result"])


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

