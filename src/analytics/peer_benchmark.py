# src/analytics/peer_benchmark.py
"""Module 6: Peer Benchmarking.

Compare player performance to rating peers.

Requirements:
- Compare CPL, blunder rate, phase strength
- Use percentile or relative deltas
- Support future population data

Note: This module uses placeholder baselines. In production, these would
come from a population database of aggregated player statistics by rating.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .schemas import PeerBenchmark

if TYPE_CHECKING:
    from typing import Any

# Placeholder peer baselines grouped in 300-point brackets.
# Format: {bracket: {metric: (mean, std_dev)}}
PEER_BASELINES: dict[str, dict[str, tuple[float, float]]] = {
    "0-299": {
        "overall_cpl": (240, 60),
        "opening_cpl": (170, 55),
        "middlegame_cpl": (270, 65),
        "endgame_cpl": (285, 70),
        "blunder_rate": (11.0, 3.5),
    },
    "300-599": {
        "overall_cpl": (210, 55),
        "opening_cpl": (150, 45),
        "middlegame_cpl": (230, 60),
        "endgame_cpl": (250, 65),
        "blunder_rate": (9.0, 3.2),
    },
    "600-899": {
        "overall_cpl": (170, 45),
        "opening_cpl": (120, 35),
        "middlegame_cpl": (190, 50),
        "endgame_cpl": (205, 55),
        "blunder_rate": (7.5, 2.8),
    },
    "900-1199": {
        "overall_cpl": (135, 40),
        "opening_cpl": (95, 30),
        "middlegame_cpl": (155, 45),
        "endgame_cpl": (170, 50),
        "blunder_rate": (5.8, 2.3),
    },
    "1200-1499": {
        "overall_cpl": (105, 35),
        "opening_cpl": (75, 28),
        "middlegame_cpl": (125, 40),
        "endgame_cpl": (135, 45),
        "blunder_rate": (4.2, 1.8),
    },
    "1500-1799": {
        "overall_cpl": (80, 28),
        "opening_cpl": (55, 22),
        "middlegame_cpl": (95, 32),
        "endgame_cpl": (105, 35),
        "blunder_rate": (3.0, 1.4),
    },
    "1800-2099": {
        "overall_cpl": (58, 22),
        "opening_cpl": (40, 18),
        "middlegame_cpl": (70, 26),
        "endgame_cpl": (78, 28),
        "blunder_rate": (2.0, 1.0),
    },
    "2100-2399": {
        "overall_cpl": (42, 18),
        "opening_cpl": (30, 14),
        "middlegame_cpl": (50, 20),
        "endgame_cpl": (55, 22),
        "blunder_rate": (1.2, 0.7),
    },
    "2400+": {
        "overall_cpl": (30, 14),
        "opening_cpl": (22, 10),
        "middlegame_cpl": (35, 15),
        "endgame_cpl": (38, 18),
        "blunder_rate": (0.8, 0.4),
    },
}

# Sample sizes (placeholder)
SAMPLE_SIZES = {
    "0-299": 800,
    "300-599": 2500,
    "600-899": 6000,
    "900-1199": 12000,
    "1200-1499": 18000,
    "1500-1799": 15000,
    "1800-2099": 9000,
    "2100-2399": 5000,
    "2400+": 2000,
}

BRACKET_SIZE = 300
BRACKET_CEILING = 2400


def _get_rating_bracket(rating: int) -> str:
    """Map rating into a 300-point bracket label."""
    try:
        rating_val = int(rating)
    except Exception:
        rating_val = 0

    rating_val = max(0, rating_val)
    if rating_val >= BRACKET_CEILING:
        return f"{BRACKET_CEILING}+"

    lower = (rating_val // BRACKET_SIZE) * BRACKET_SIZE
    upper = lower + BRACKET_SIZE - 1
    return f"{lower}-{upper}"


def _compute_percentile(value: float, mean: float, std: float, lower_is_better: bool = True) -> int:
    """Compute percentile using normal distribution approximation.

    Args:
        value: Player's value
        mean: Population mean
        std: Population std dev
        lower_is_better: If True, lower values = higher percentile

    Returns:
        Percentile (0-100)
    """
    if std <= 0:
        return 50

    # Z-score
    z = (value - mean) / std

    # Approximate CDF using error function
    # For chess CPL, lower is better, so we want 1 - CDF
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))

    if lower_is_better:
        percentile = (1 - cdf) * 100
    else:
        percentile = cdf * 100

    return max(0, min(100, int(math.ceil(percentile))))


def _ceil_int(x: float) -> int:
    return int(math.ceil(x))


def compute_peer_benchmark(
    player_rating: int,
    overall_cpl: float,
    opening_cpl: float,
    middlegame_cpl: float,
    endgame_cpl: float,
    blunder_rate: float,
    tactics_accuracy: float = 0.0,
) -> PeerBenchmark:
    """Compute peer benchmark comparison.

    Args:
        player_rating: Player's rating
        overall_cpl: Player's overall CPL
        opening_cpl: Player's opening CPL
        middlegame_cpl: Player's middlegame CPL
        endgame_cpl: Player's endgame CPL
        blunder_rate: Player's blunder rate per 100 moves
        tactics_accuracy: Player's tactics accuracy (optional)

    Returns:
        PeerBenchmark with percentiles and comparisons.
    """
    bracket = _get_rating_bracket(player_rating)
    baselines = PEER_BASELINES.get(bracket, PEER_BASELINES["1200-1499"])

    result = PeerBenchmark()
    result.player_rating = player_rating
    result.rating_bracket = bracket
    result.sample_size = SAMPLE_SIZES.get(bracket, 10000)

    # Compute percentiles (lower CPL is better)
    result.overall_cpl_percentile = _compute_percentile(
        overall_cpl, baselines["overall_cpl"][0], baselines["overall_cpl"][1], lower_is_better=True
    )
    result.opening_cpl_percentile = _compute_percentile(
        opening_cpl, baselines["opening_cpl"][0], baselines["opening_cpl"][1], lower_is_better=True
    )
    result.middlegame_cpl_percentile = _compute_percentile(
        middlegame_cpl, baselines["middlegame_cpl"][0], baselines["middlegame_cpl"][1], lower_is_better=True
    )
    result.endgame_cpl_percentile = _compute_percentile(
        endgame_cpl, baselines["endgame_cpl"][0], baselines["endgame_cpl"][1], lower_is_better=True
    )

    # Blunder rate percentile (lower is better)
    result.blunder_rate_percentile = _compute_percentile(
        blunder_rate, baselines["blunder_rate"][0], baselines["blunder_rate"][1], lower_is_better=True
    )

    # Blunder rate vs peers (positive = worse than peers)
    peer_blunder_mean = baselines["blunder_rate"][0]
    if peer_blunder_mean > 0:
        result.blunder_rate_vs_peers_pct = _ceil_int(((blunder_rate / peer_blunder_mean) - 1) * 100)
    else:
        result.blunder_rate_vs_peers_pct = 0

    # Tactics accuracy (if provided, higher is better)
    if tactics_accuracy > 0:
        result.tactics_accuracy_percentile = _ceil_int(tactics_accuracy)  # placeholder

    # Determine strongest/weakest vs peers
    phase_percentiles = {
        "opening": result.opening_cpl_percentile,
        "middlegame": result.middlegame_cpl_percentile,
        "endgame": result.endgame_cpl_percentile,
    }
    sorted_phases = sorted(phase_percentiles.items(), key=lambda x: x[1], reverse=True)
    result.strongest_vs_peers = sorted_phases[0][0]
    result.weakest_vs_peers = sorted_phases[-1][0]

    return result


def benchmark_from_games_data(
    games_data: list[dict[str, Any]],
    player_rating: int | None = None,
) -> PeerBenchmark:
    """Compute peer benchmark from games data.

    Args:
        games_data: List of game dicts with move_evals
        player_rating: Optional player rating (extracted from games if not provided)

    Returns:
        PeerBenchmark
    """
    # Extract metrics from games
    all_cp_losses: list[int] = []
    phase_losses: dict[str, list[int]] = {"opening": [], "middlegame": [], "endgame": []}
    blunder_count = 0
    total_moves = 0
    ratings: list[int] = []

    for game in games_data:
        game_info = game.get("game_info", {}) or {}

        # Try to get rating
        for key in ("player_rating", "rating", "white_rating", "black_rating"):
            r = game_info.get(key)
            if r:
                try:
                    ratings.append(int(r))
                except Exception:
                    pass

        move_evals = game.get("move_evals", []) or []
        for m in move_evals:
            cp_loss = int(m.get("cp_loss") or 0)
            phase = str(m.get("phase") or "middlegame")
            total_moves += 1

            if cp_loss > 0:
                capped = min(cp_loss, 2000)
                all_cp_losses.append(capped)
                if phase in phase_losses:
                    phase_losses[phase].append(capped)

            if cp_loss >= 300:
                blunder_count += 1

    # Compute averages
    overall_cpl = sum(all_cp_losses) / len(all_cp_losses) if all_cp_losses else 0.0
    opening_cpl = sum(phase_losses["opening"]) / len(phase_losses["opening"]) if phase_losses["opening"] else 0.0
    middlegame_cpl = sum(phase_losses["middlegame"]) / len(phase_losses["middlegame"]) if phase_losses["middlegame"] else 0.0
    endgame_cpl = sum(phase_losses["endgame"]) / len(phase_losses["endgame"]) if phase_losses["endgame"] else 0.0
    blunder_rate = (blunder_count / total_moves * 100) if total_moves > 0 else 0.0

    # Determine rating
    if player_rating is None:
        player_rating = int(sum(ratings) / len(ratings)) if ratings else 1200

    return compute_peer_benchmark(
        player_rating=player_rating,
        overall_cpl=overall_cpl,
        opening_cpl=opening_cpl,
        middlegame_cpl=middlegame_cpl,
        endgame_cpl=endgame_cpl,
        blunder_rate=blunder_rate,
    )
