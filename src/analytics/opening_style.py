"""Opening style heuristics.

This module assigns a lightweight, *heuristic* style profile to common opening
families. It is intentionally approximate and used only as a small signal in
playstyle classification.

Scales:
- Each axis is 1..10 (inclusive).
- Unknown openings default to neutral (5).

Axes:
- defensive: solid, risk-averse structures
- aggressive: direct king attacks / initiative-first play
- positional: long-term structure/piece maneuvering emphasis
- tactical: sharp, forcing, calculation-heavy play
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OpeningStyle:
    defensive: int
    aggressive: int
    positional: int
    tactical: int


_NEUTRAL = OpeningStyle(defensive=5, aggressive=5, positional=5, tactical=5)

# Prefix-based matching against normalized opening names.
# Keep this list short and broad; it’s not meant to be encyclopedic.
_STYLE_BY_PREFIX: list[tuple[str, OpeningStyle]] = [
    ("king's gambit", OpeningStyle(defensive=2, aggressive=9, positional=3, tactical=9)),
    ("evans gambit", OpeningStyle(defensive=2, aggressive=8, positional=4, tactical=8)),
    ("fried liver", OpeningStyle(defensive=2, aggressive=9, positional=3, tactical=9)),

    ("italian game", OpeningStyle(defensive=5, aggressive=6, positional=6, tactical=6)),
    ("ruy lopez", OpeningStyle(defensive=6, aggressive=5, positional=8, tactical=6)),

    ("sicilian", OpeningStyle(defensive=5, aggressive=7, positional=6, tactical=8)),
    ("sicilian: najdorf", OpeningStyle(defensive=4, aggressive=8, positional=6, tactical=9)),
    ("sicilian: closed", OpeningStyle(defensive=6, aggressive=5, positional=7, tactical=6)),

    ("french defence", OpeningStyle(defensive=7, aggressive=4, positional=7, tactical=5)),
    ("caro-kann", OpeningStyle(defensive=8, aggressive=3, positional=7, tactical=4)),
    ("scandinavian", OpeningStyle(defensive=5, aggressive=5, positional=4, tactical=6)),

    ("queen's gambit declined", OpeningStyle(defensive=7, aggressive=3, positional=8, tactical=5)),
    ("queen's gambit accepted", OpeningStyle(defensive=5, aggressive=4, positional=7, tactical=6)),

    ("nimzo-indian", OpeningStyle(defensive=7, aggressive=4, positional=8, tactical=6)),
    ("queen's indian", OpeningStyle(defensive=7, aggressive=3, positional=8, tactical=5)),
    ("slav", OpeningStyle(defensive=8, aggressive=3, positional=7, tactical=5)),

    ("king's indian", OpeningStyle(defensive=4, aggressive=8, positional=5, tactical=8)),

    ("english opening", OpeningStyle(defensive=6, aggressive=4, positional=7, tactical=5)),
    ("reti", OpeningStyle(defensive=6, aggressive=3, positional=7, tactical=4)),
    ("bird's", OpeningStyle(defensive=3, aggressive=7, positional=4, tactical=7)),

    ("alekhine", OpeningStyle(defensive=5, aggressive=6, positional=5, tactical=7)),
    ("modern defence", OpeningStyle(defensive=6, aggressive=5, positional=6, tactical=6)),
    ("pirc", OpeningStyle(defensive=5, aggressive=6, positional=5, tactical=7)),

    ("grob", OpeningStyle(defensive=1, aggressive=8, positional=2, tactical=6)),
]


def get_opening_style(opening_name: str) -> OpeningStyle:
    """Return a heuristic style profile for an opening name.

    Uses prefix matching on a normalized (lowercased) opening name.
    Unknown openings return a neutral profile.
    """
    if not opening_name:
        return _NEUTRAL

    name = str(opening_name).strip().lower()

    # Some sources use "Defense" vs "Defence".
    name = name.replace("defense", "defence")

    for prefix, style in _STYLE_BY_PREFIX:
        if name.startswith(prefix):
            return style

    # Also try substring match for common cases like
    # "Sicilian Defense: Najdorf, English Attack".
    for prefix, style in _STYLE_BY_PREFIX:
        if prefix in name:
            return style

    return _NEUTRAL


def opening_style_to_percent(axis_1_to_10: float) -> int:
    """Convert 1..10 scale to 0..100."""
    clamped = max(1.0, min(10.0, float(axis_1_to_10)))
    return int(round((clamped - 1.0) / 9.0 * 100.0))
