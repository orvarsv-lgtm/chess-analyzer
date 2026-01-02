
from __future__ import annotations

import os
from dataclasses import dataclass
from io import StringIO
from typing import Any

import pandas as pd
import requests
import streamlit as st
import chess.pgn

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


@dataclass(frozen=True)
class GameInput:
    index: int
    pgn: str
    headers: dict[str, str]
    move_sans: list[str]
    num_plies: int


def _split_pgn_into_games(pgn_text: str, max_games: int) -> list[GameInput]:
    pgn_io = StringIO(pgn_text or "")
    games: list[GameInput] = []
    while len(games) < int(max_games):
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        headers = {k: str(v) for k, v in dict(game.headers).items() if v is not None}
        move_sans: list[str] = []
        board = game.board()
        for mv in game.mainline_moves():
            move_sans.append(board.san(mv))
            board.push(mv)

        games.append(
            GameInput(
                index=len(games) + 1,
                pgn=str(game),
                headers=headers,
                move_sans=move_sans,
                num_plies=len(move_sans),
            )
        )
    return games


def _infer_focus_color(headers: dict[str, str], focus_player: str | None) -> str | None:
    if not focus_player:
        return None
    fp = focus_player.strip().lower()
    white = (headers.get("White") or "").strip().lower()
    black = (headers.get("Black") or "").strip().lower()
    if fp and white and fp == white:
        return "white"
    if fp and black and fp == black:
        return "black"
    return None


def _result_for_focus(headers: dict[str, str], focus_color: str | None) -> str | None:
    res = (headers.get("Result") or "").strip()
    if not res:
        return None
    if focus_color == "white":
        return "win" if res == "1-0" else "loss" if res == "0-1" else "draw" if res == "1/2-1/2" else None
    if focus_color == "black":
        return "win" if res == "0-1" else "loss" if res == "1-0" else "draw" if res == "1/2-1/2" else None
    return None


def _phase_for_ply(ply_index: int, total_plies: int) -> str:
    """Heuristic phase split by plies (half-moves).

    Opening: first 20 plies (~10 moves)
    Endgame: last 20 plies (~10 moves)
    Middlegame: everything in between
    """
    opening_end = min(20, total_plies)
    endgame_start = max(total_plies - 20, opening_end)
    if ply_index < opening_end:
        return "opening"
    if ply_index >= endgame_start:
        return "endgame"
    return "middlegame"


def _compute_cp_loss_rows(
    analysis_rows: list[dict[str, Any]],
    focus_color: str | None,
    total_plies: int,
) -> list[dict[str, Any]]:
    """Compute per-ply cp_loss from successive score_cp values.

    score_cp is assumed to be White POV evaluation after the move.
    cp_loss is assigned to the side that just moved.
    """
    scores: list[int] = []
    for r in analysis_rows:
        try:
            scores.append(int(r.get("score_cp") or 0))
        except Exception:
            scores.append(0)

    out: list[dict[str, Any]] = []
    prev_score: int | None = None
    for i, r in enumerate(analysis_rows):
        curr = scores[i] if i < len(scores) else 0
        mover = "white" if (i % 2 == 0) else "black"

        cp_loss = 0
        if prev_score is not None:
            if mover == "white":
                cp_loss = max(0, prev_score - curr)
            else:
                cp_loss = max(0, curr - prev_score)

        prev_score = curr
        if focus_color and mover != focus_color:
            cp_loss = 0

        phase = _phase_for_ply(i, total_plies)
        out.append(
            {
                "ply": i + 1,
                "mover": mover,
                "move_san": r.get("move_san"),
                "score_cp": curr,
                "cp_loss": cp_loss,
                "phase": phase,
            }
        )
    return out


def _aggregate_postprocessed_results(games: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-game move tables into phase stats, opening performance, trends, and coach summary."""
    all_move_rows: list[dict[str, Any]] = []
    for g in games:
        all_move_rows.extend(g.get("moves_table") or [])

    # Phase stats
    phase_stats: dict[str, dict[str, Any]] = {}
    for phase in ("opening", "middlegame", "endgame"):
        phase_rows = [r for r in all_move_rows if r.get("phase") == phase]
        cpl_vals = [int(r.get("cp_loss") or 0) for r in phase_rows if int(r.get("cp_loss") or 0) > 0]
        avg_cpl = (sum(cpl_vals) / len(cpl_vals)) if cpl_vals else 0.0
        mistakes = sum(1 for v in cpl_vals if v >= 100)
        blunders = sum(1 for v in cpl_vals if v >= 300)
        phase_stats[phase] = {
            "avg_cpl": float(avg_cpl),
            "moves": int(len(phase_rows)),
            "mistakes": int(mistakes),
            "blunders": int(blunders),
        }

    # Weakest/strongest phases
    phase_by_cpl = sorted(((p, s.get("avg_cpl", 0.0)) for p, s in phase_stats.items()), key=lambda x: x[1], reverse=True)
    weakest_phase = phase_by_cpl[0][0] if phase_by_cpl else "opening"
    strongest_phase = phase_by_cpl[-1][0] if phase_by_cpl else "opening"

    # Win/draw/loss by opening (for focus player when possible)
    opening_counts: dict[str, dict[str, int]] = {}
    for g in games:
        opening = (g.get("opening") or g.get("eco") or "Unknown").strip() or "Unknown"
        opening_counts.setdefault(opening, {"win": 0, "draw": 0, "loss": 0, "games": 0})
        opening_counts[opening]["games"] += 1

        focus_color = g.get("focus_color")
        headers = {
            "White": g.get("white") or "",
            "Black": g.get("black") or "",
            "Result": g.get("result") or "",
        }
        outcome = _result_for_focus(headers, focus_color)
        if outcome in {"win", "draw", "loss"}:
            opening_counts[opening][outcome] += 1

    # Keep top openings by sample size
    opening_rates: list[dict[str, Any]] = []
    for opening, rec in sorted(opening_counts.items(), key=lambda kv: kv[1].get("games", 0), reverse=True)[:12]:
        opening_rates.append(
            {
                "opening": opening,
                "win": rec["win"],
                "draw": rec["draw"],
                "loss": rec["loss"],
            }
        )

    # CPL trend over games (avg cp_loss per game for focus player)
    cpl_trend: list[dict[str, Any]] = []
    for g in games:
        rows = g.get("moves_table") or []
        cpl_vals = [int(r.get("cp_loss") or 0) for r in rows if int(r.get("cp_loss") or 0) > 0]
        avg = (sum(cpl_vals) / len(cpl_vals)) if cpl_vals else 0.0
        cpl_trend.append({"game": f"Game {g.get('index')}", "avg_cpl": float(avg)})

    # Endgame success (games that reached endgame where outcome is win)
    endgame_games = 0
    endgame_wins = 0
    for g in games:
        rows = g.get("moves_table") or []
        if any(r.get("phase") == "endgame" for r in rows):
            endgame_games += 1
            headers = {
                "White": g.get("white") or "",
                "Black": g.get("black") or "",
                "Result": g.get("result") or "",
            }
            outcome = _result_for_focus(headers, g.get("focus_color"))
            if outcome == "win":
                endgame_wins += 1

    endgame_success = {
        "endgame_games": int(endgame_games),
        "endgame_wins": int(endgame_wins),
        "endgame_win_rate": (float(endgame_wins) / float(endgame_games)) if endgame_games else 0.0,
    }

    # Coach summary (deterministic, minimal)
    strengths: list[str] = []
    recommended: list[str] = []

    strengths.append(f"Strongest phase: {strongest_phase.title()}")
    recommended.append(f"Focus: {weakest_phase.title()} phase accuracy")

    if phase_stats.get(weakest_phase, {}).get("blunders", 0) > 0:
        recommended.append("Tactical review: reduce blunders (>=300cp swings)")
    if phase_stats.get(weakest_phase, {}).get("mistakes", 0) > 0:
        recommended.append("Conversion practice: reduce medium mistakes (>=100cp swings)")

    if endgame_success["endgame_games"] > 0:
        strengths.append(
            f"Endgames reached: {endgame_success['endgame_games']} (win rate {round(endgame_success['endgame_win_rate'] * 100, 1)}%)"
        )
    else:
        recommended.append("Endgame fundamentals: reach simplified positions confidently")

    coach_summary = {
        "primary_weakness": f"Weakest phase: {weakest_phase.title()}",
        "strengths": strengths[:4],
        "recommended_focus": recommended[:4],
    }

    return {
        "success": True,
        "games_analyzed": len(games),
        "total_moves": int(len(all_move_rows)),
        "analysis": [],
        "games": games,
        "phase_stats": phase_stats,
        "opening_rates": opening_rates,
        "cpl_trend": cpl_trend,
        "endgame_success": endgame_success,
        "coach_summary": coach_summary,
    }


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
            "Backend contract mismatch: the server at this URL is not accepting JSON bodies. "
            "It is requiring multipart/form-data with a required 'file' field (confirmed by /openapi.json and by a direct JSON POST).\n\n"
            "To satisfy the project rule (PGN text only; keys ['pgn','max_games']), you must either:\n"
            "1) Point VPS_ANALYSIS_URL at the correct JSON-accepting backend, or\n"
            "2) Update the FastAPI backend /analyze_game endpoint to accept application/json with a body containing 'pgn' and 'max_games'."
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


def _render_enhanced_ui(aggregated: dict[str, Any]) -> None:
    games: list[dict[str, Any]] = aggregated.get("games", []) or []
    all_rows: list[dict[str, Any]] = aggregated.get("analysis", []) or []

    st.subheader("Analysis")
    st.metric("Games analyzed", int(aggregated.get("games_analyzed") or len(games) or 0))
    st.metric("Total moves analyzed", int(aggregated.get("total_moves") or len(all_rows) or 0))

    # --- Per-game summary table ---
    if games:
        summary_df = pd.DataFrame(
            [
                {
                    "#": g.get("index"),
                    "Date": g.get("date"),
                    "White": g.get("white"),
                    "Black": g.get("black"),
                    "Result": g.get("result"),
                    "ECO": g.get("eco"),
                    "Opening": g.get("opening"),
                    "Moves": g.get("moves"),
                }
                for g in games
            ]
        )
        st.subheader("Games")
        st.dataframe(summary_df, use_container_width=True)

        for g in games:
            title = f"Game {g.get('index')}: {g.get('white')} vs {g.get('black')} ({g.get('result')})"
            with st.expander(title, expanded=False):
                st.write(
                    f"Opening: {g.get('opening') or 'Unknown'} "
                    f"{('(' + str(g.get('eco')) + ')') if g.get('eco') else ''}"
                )
                moves_df = pd.DataFrame(g.get("moves_table") or [])
                if not moves_df.empty:
                    st.dataframe(moves_df, use_container_width=True)
                else:
                    st.warning("No move rows to display for this game.")

    # --- Phase analysis ---
    phase_stats = aggregated.get("phase_stats") or {}
    if phase_stats:
        st.subheader("Phase Analysis")
        phase_df = pd.DataFrame(
            [
                {
                    "Phase": p.title(),
                    "Avg CPL": round(float(s.get("avg_cpl") or 0.0), 1),
                    "Moves": int(s.get("moves") or 0),
                    "Mistakes (>=100)": int(s.get("mistakes") or 0),
                    "Blunders (>=300)": int(s.get("blunders") or 0),
                }
                for p, s in phase_stats.items()
            ]
        )
        st.dataframe(phase_df, use_container_width=True)

        # Simple charts without adding deps
        chart_df = phase_df.set_index("Phase")[["Avg CPL", "Mistakes (>=100)", "Blunders (>=300)"]]
        st.bar_chart(chart_df)

    # --- Win rates / opening performance ---
    opening_rates = aggregated.get("opening_rates") or []
    if opening_rates:
        st.subheader("Win/Draw/Loss by Opening")
        odf = pd.DataFrame(opening_rates)
        if not odf.empty:
            odf = odf.set_index("opening")[["win", "draw", "loss"]]
            st.bar_chart(odf)

    # --- CPL trend ---
    trend = aggregated.get("cpl_trend") or []
    if trend:
        st.subheader("CPL Trend")
        tdf = pd.DataFrame(trend)
        if not tdf.empty:
            tdf = tdf.set_index("game")[["avg_cpl"]]
            st.line_chart(tdf)

    # --- Coach summary ---
    coach = aggregated.get("coach_summary") or {}
    if coach:
        st.subheader("Coach Summary")
        st.write(f"Primary weakness: {coach.get('primary_weakness')}")
        strengths = coach.get("strengths") or []
        focus = coach.get("recommended_focus") or []
        if strengths:
            st.write("Strengths:")
            for s in strengths:
                st.write(f"- {s}")
        if focus:
            st.write("Recommended training focus:")
            for f in focus:
                st.write(f"- {f}")


def main() -> None:
    st.title("Chess Analyzer (Remote Engine)")

    if "analysis_result" not in st.session_state:
        st.session_state["analysis_result"] = None
    if "analysis_request" not in st.session_state:
        st.session_state["analysis_request"] = None

    st.subheader("Inputs")
    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"], horizontal=True)
    max_games = st.slider("Max games", min_value=1, max_value=200, value=10, step=1)

    pgn_text: str = ""  # single canonical analysis input
    focus_player: str | None = None

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        focus_player = username.strip() if username else None
        if st.button("Run analysis"):
            if not username:
                st.error("Please enter a username")
                return
            try:
                pgn_text = fetch_lichess_pgn(username, max_games=max_games)
            except Exception as e:
                st.error(str(e))
                st.stop()

            games_inputs = _split_pgn_into_games(pgn_text, max_games=max_games)
            num_games_in_pgn = max(pgn_text.count("[Event "), len(games_inputs))
            games_to_analyze = min(len(games_inputs), int(max_games))
            st.session_state["analysis_request"] = {
                "source": "lichess",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            progress = st.progress(0)
            status = st.empty()
            moves_counter = st.empty()

            aggregated_games: list[dict[str, Any]] = []
            aggregated_rows: list[dict[str, Any]] = []

            for i, gi in enumerate(games_inputs[:games_to_analyze], start=1):
                status.info(f"Analyzing {i} of {games_to_analyze} games...")
                try:
                    resp = _post_to_engine(gi.pgn, max_games=1)
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                rows = valid.get("analysis", []) or []
                # Build per-game rows table + phase stats
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(rows, focus_color=focus_color, total_plies=gi.num_plies)
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "phase"]].to_dict(
                    orient="records"
                )
                aggregated_rows.extend(rows)

                aggregated_games.append(
                    {
                        "index": gi.index,
                        "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                        "white": gi.headers.get("White") or "",
                        "black": gi.headers.get("Black") or "",
                        "result": gi.headers.get("Result") or "",
                        "eco": gi.headers.get("ECO") or "",
                        "opening": gi.headers.get("Opening") or "",
                        "moves": int((gi.num_plies + 1) // 2),
                        "moves_table": moves_table,
                        "focus_color": focus_color,
                    }
                )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")

            status.success("Backend status: 200 OK")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            st.session_state["analysis_result"] = aggregated

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

            games_inputs = _split_pgn_into_games(pgn_text, max_games=max_games)
            num_games_in_pgn = max(pgn_text.count("[Event "), len(games_inputs))
            games_to_analyze = min(len(games_inputs), int(max_games))
            st.session_state["analysis_request"] = {
                "source": "upload",
                "max_games": int(max_games),
                "num_games_in_pgn": int(num_games_in_pgn),
                "games_to_analyze": int(games_to_analyze),
            }

            progress = st.progress(0)
            status = st.empty()
            moves_counter = st.empty()

            aggregated_games: list[dict[str, Any]] = []
            aggregated_rows: list[dict[str, Any]] = []

            # Default focus for uploads: White (no username context)
            focus_player = (games_inputs[0].headers.get("White") if games_inputs else None)

            for i, gi in enumerate(games_inputs[:games_to_analyze], start=1):
                status.info(f"Analyzing {i} of {games_to_analyze} games...")
                try:
                    resp = _post_to_engine(gi.pgn, max_games=1)
                    valid = _validate_engine_response(resp)
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                rows = valid.get("analysis", []) or []
                focus_color = _infer_focus_color(gi.headers, focus_player)
                cp_rows = _compute_cp_loss_rows(rows, focus_color=focus_color, total_plies=gi.num_plies)
                moves_table = pd.DataFrame(cp_rows)[["ply", "mover", "move_san", "score_cp", "cp_loss", "phase"]].to_dict(
                    orient="records"
                )
                aggregated_rows.extend(rows)

                aggregated_games.append(
                    {
                        "index": gi.index,
                        "date": gi.headers.get("UTCDate") or gi.headers.get("Date") or "",
                        "white": gi.headers.get("White") or "",
                        "black": gi.headers.get("Black") or "",
                        "result": gi.headers.get("Result") or "",
                        "eco": gi.headers.get("ECO") or "",
                        "opening": gi.headers.get("Opening") or "",
                        "moves": int((gi.num_plies + 1) // 2),
                        "moves_table": moves_table,
                        "focus_color": focus_color,
                    }
                )

                progress.progress(int((i / games_to_analyze) * 100))
                moves_counter.write(f"Total moves analyzed: {len(aggregated_rows)}")

            status.success("Backend status: 200 OK")

            aggregated = _aggregate_postprocessed_results(aggregated_games)
            st.session_state["analysis_result"] = aggregated

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
        _render_enhanced_ui(st.session_state["analysis_result"])


# Prevent any accidental local analysis path.
def _legacy_local_analyzer_guard(*_args, **_kwargs):
    raise RuntimeError("Local analyzer must never run in Streamlit")


if __name__ == "__main__":
    main()

