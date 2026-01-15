"""Tiny hidden component that polls localStorage for pending chess moves.

This component is used in conjunction with the chessboard component when
running in "no-flash" mode. The chessboard stores moves in localStorage
instead of calling setComponentValue, and this poller retrieves them.
This decouples user interaction from Streamlit reruns.
"""

from pathlib import Path
from typing import Optional

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).parent / "move_poller_frontend"

_move_poller_component = components.declare_component(
    "move_poller_component",
    path=str(_COMPONENT_DIR),
)


def poll_for_move(key: str = "move_poller") -> Optional[str]:
    """Poll localStorage for a pending chess move.
    
    Returns:
        UCI string if a move was found, else None.
    """
    value = _move_poller_component(key=key, default=None)
    
    if isinstance(value, str) and value.strip():
        return value.strip()
    
    return None
