
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

    # Defensive payload validation (hard stop)
    if not isinstance(pgn_text, str) or not pgn_text.strip():
        st.error("Invalid PGN input: expected non-empty text")
        st.stop()
    if set(payload.keys()) != {"pgn", "max_games"}:
        st.error(f"Invalid payload keys: {sorted(payload.keys())}. Expected ['max_games', 'pgn']")
        st.stop()

    # Temporary debug logging to confirm correct route/payload
    st.write("POSTING TO:", endpoint)
    st.write("Payload keys:", list(payload.keys()))

    resp = requests.post(endpoint, json=payload, timeout=300, headers=headers)

    if resp.status_code == 403:
        raise RuntimeError("VPS Authentication Failed")
    if resp.status_code == 422:
        st.error("Engine rejected request (422 Validation Error)")
        st.info(
            "This backend is rejecting JSON payloads. "
            "If your backend is meant to accept PGN text, it must accept a JSON body with keys 'pgn' and 'max_games'. "
            "The current server at this URL appears to require a multipart 'file' field instead."
        )
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
    if "analysis_request" not in st.session_state:
        st.session_state["analysis_request"] = None

    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"])
    max_games = st.number_input("Max games", min_value=1, max_value=100, value=20, step=1)

    pgn_text: str = ""

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        if st.button("Run analysis"):
            if not username:
                st.error("Please enter a username")
                return
            try:
                pgn_text = fetch_lichess_pgn(username, max_games=max_games)
            except Exception as e:
                st.error(str(e))
                st.stop()

            num_games_in_pgn = pgn_text.count("[Event ")
            games_to_analyze = min(num_games_in_pgn, int(max_games)) if num_games_in_pgn else 0
            st.session_state["analysis_request"] = {
                "source": "lichess",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            try:
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
            except Exception as e:
                st.error(str(e))
                st.stop()

            num_games_in_pgn = pgn_text.count("[Event ")
            games_to_analyze = min(num_games_in_pgn, int(max_games)) if num_games_in_pgn else 0
            st.session_state["analysis_request"] = {
                "source": "upload",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            try:
                results = _post_to_engine(pgn_text, max_games=max_games)
                st.session_state["analysis_result"] = _validate_engine_response(results)
            except Exception as e:
                st.error(str(e))
                st.stop()

    req = st.session_state.get("analysis_request")
    if req:
        if req.get("num_games_in_pgn", 0) > 0:
            st.info(
                f"Analyzing {req.get('games_to_analyze')} of {req.get('num_games_in_pgn')} games "
                f"(limited by max_games={req.get('max_games')})."
            )
        else:
            st.warning(
                "Could not count games in PGN (no '[Event ' headers found). "
                "This usually means the PGN is a single game or is missing headers."
            )

    if st.session_state.get("analysis_result"):
        # If backend provides a games-analyzed count, validate it against expectation.
        expected_games = (req or {}).get("games_to_analyze")
        backend_games = (
            st.session_state["analysis_result"].get("games_analyzed")
            or st.session_state["analysis_result"].get("num_games")
            or st.session_state["analysis_result"].get("games_processed")
        )
        if expected_games is not None and backend_games is not None and int(backend_games) < int(expected_games):
            st.warning(f"Backend analyzed {backend_games} games, expected {expected_games}.")
        elif expected_games and backend_games is None:
            st.warning(
                "Backend did not report how many games it analyzed; "
                "cannot verify multi-game processing from the response."
            )
        _render_results(st.session_state["analysis_result"])


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

