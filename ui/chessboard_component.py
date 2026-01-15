from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components


_COMPONENT_DIR = Path(__file__).parent / "chessboard_component_frontend"

_chessboard_component = components.declare_component(
    "chessboard_component",
    path=str(_COMPONENT_DIR),
)


def render_chessboard(
    *,
    fen: str,
    legal_moves: List[str],
    orientation: str,
    side_to_move: str,
    highlights: Optional[Dict[str, Any]] = None,
    hint: str = "",
    animate_move: Optional[str] = None,
    no_rerun_mode: bool = False,
    key: str = "chessboard",
) -> Optional[str]:
    """Render an interactive JS chessboard and return a UCI move when user plays.

    Args:
        fen: Current position in FEN.
        legal_moves: List of legal moves in UCI (e.g., ["e2e4", "g1f3"]).
        orientation: "white" or "black".
        side_to_move: "w" or "b".
        highlights: Dict controlling UI highlights.
        hint: Small hint text under the board.
        animate_move: UCI move to animate (e.g., "e2e4"). Shows piece sliding.
        no_rerun_mode: If True, moves are stored in localStorage instead of
            triggering a Streamlit rerun. Use with poll_for_move() to retrieve.
        key: Streamlit component key.

    Returns:
        UCI string if the user made a move, else None.
        In no_rerun_mode, always returns None (use poll_for_move instead).
    """

    if orientation not in {"white", "black"}:
        orientation = "white"
    if side_to_move not in {"w", "b"}:
        side_to_move = "w"

    payload = {
        "fen": fen,
        "legal_moves": legal_moves,
        "orientation": orientation,
        "side_to_move": side_to_move,
        "highlights": highlights or {},
        "ui": {"hint": hint},
        "animate_move": animate_move,
        "no_rerun_mode": no_rerun_mode,
    }

    value = _chessboard_component(**payload, key=key, default=None)

    # Support both formats:
    # - legacy: {"uci": "e2e4"}
    # - current: "e2e4"
    if isinstance(value, str) and value.strip():
        return value.strip()

    if isinstance(value, dict):
        uci = value.get("uci")
        if isinstance(uci, str) and uci.strip():
            return uci.strip()

    return None
