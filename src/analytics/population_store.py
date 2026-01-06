"""Local population store for peer benchmarking.

This module maintains a single append-only JSONL file that accumulates
per-analysis aggregate stats. The goal is to improve peer comparisons over time
using *local* usage data.

Design:
- One record per analysis run.
- Append-only JSON Lines for robustness.
- Minimal PII: username is stored only if provided by caller.
- Deterministic values derived from engine-evaluated `games_data`.

If the file is empty or sample sizes are too small, benchmarking should fall
back to static placeholder baselines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import math


BRACKET_SIZE = 300
BRACKET_CEILING = 2400


def default_population_path() -> Path:
    # repo_root/data/population_analytics.jsonl
    return Path(__file__).resolve().parents[2] / "data" / "population_analytics.jsonl"


def get_rating_bracket(rating: int) -> str:
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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float], mean_val: float) -> float:
    if not values:
        return 0.0
    var = sum((x - mean_val) ** 2 for x in values) / len(values)
    return math.sqrt(var)


def _phase_ratio_endgame_vs_openmid(opening_cpl: float, middlegame_cpl: float, endgame_cpl: float) -> float:
    """Compute endgame CPL relative to avg(opening, middlegame).

    Lower ratio is better (endgames are *less* disproportionately worse).
    """
    denom_parts = [v for v in (opening_cpl, middlegame_cpl) if v and v > 0]
    if not denom_parts or not endgame_cpl or endgame_cpl <= 0:
        return 0.0
    denom = sum(denom_parts) / len(denom_parts)
    if denom <= 0:
        return 0.0
    return float(endgame_cpl) / float(denom)


def extract_aggregate_metrics(games_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract basic aggregate metrics needed for population baselines."""
    all_cp_losses: list[int] = []
    phase_losses: dict[str, list[int]] = {"opening": [], "middlegame": [], "endgame": []}
    blunder_count = 0
    total_moves = 0
    ratings: list[int] = []
    platforms: dict[str, int] = {}

    for game in games_data:
        gi = game.get("game_info", {}) or {}

        # rating
        for key in ("player_rating", "rating", "elo", "white_rating", "black_rating"):
            r = gi.get(key)
            if r:
                try:
                    ratings.append(int(r))
                    break
                except Exception:
                    pass

        # platform
        platform = str(gi.get("platform") or "").strip().lower()
        if platform:
            platforms[platform] = platforms.get(platform, 0) + 1

        for m in game.get("move_evals", []) or []:
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

    overall_cpl = _mean([float(x) for x in all_cp_losses]) if all_cp_losses else 0.0
    opening_cpl = _mean([float(x) for x in phase_losses["opening"]]) if phase_losses["opening"] else 0.0
    middlegame_cpl = _mean([float(x) for x in phase_losses["middlegame"]]) if phase_losses["middlegame"] else 0.0
    endgame_cpl = _mean([float(x) for x in phase_losses["endgame"]]) if phase_losses["endgame"] else 0.0

    blunder_rate = (blunder_count / total_moves * 100.0) if total_moves > 0 else 0.0

    rating = int(_mean([float(r) for r in ratings])) if ratings else 1200
    bracket = get_rating_bracket(rating)

    ratio_end_vs_openmid = _phase_ratio_endgame_vs_openmid(opening_cpl, middlegame_cpl, endgame_cpl)

    primary_platform = max(platforms.items(), key=lambda kv: kv[1])[0] if platforms else ""

    return {
        "rating": rating,
        "rating_bracket": bracket,
        "games_analyzed": len(games_data),
        "total_moves": total_moves,
        "overall_cpl": overall_cpl,
        "opening_cpl": opening_cpl,
        "middlegame_cpl": middlegame_cpl,
        "endgame_cpl": endgame_cpl,
        "blunder_rate": blunder_rate,
        "endgame_vs_openmid_ratio": ratio_end_vs_openmid,
        "platform": primary_platform,
    }


def append_population_record(
    games_data: list[dict[str, Any]],
    username: str = "",
    source: str = "cli",
    path: Path | None = None,
) -> Path:
    """Append one analysis record to the population store."""
    path = path or default_population_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    metrics = extract_aggregate_metrics(games_data)

    record: dict[str, Any] = {
        "v": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "username": username or "",
        **metrics,
    }

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return path


def load_population_records(path: Path | None = None, max_records: int | None = None) -> list[dict[str, Any]]:
    path = path or default_population_path()
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            records.append(rec)
            if max_records is not None and len(records) >= max_records:
                break
    return records


def compute_baselines_by_bracket(records: list[dict[str, Any]]) -> dict[str, dict[str, tuple[float, float, int]]]:
    """Compute mean/std/count for baseline metrics per rating bracket."""
    by_bracket: dict[str, dict[str, list[float]]] = {}

    metrics = [
        "overall_cpl",
        "opening_cpl",
        "middlegame_cpl",
        "endgame_cpl",
        "blunder_rate",
        "endgame_vs_openmid_ratio",
    ]

    for r in records:
        bracket = str(r.get("rating_bracket") or "")
        if not bracket:
            continue

        bucket = by_bracket.setdefault(bracket, {m: [] for m in metrics})
        for m in metrics:
            try:
                v = float(r.get(m) or 0.0)
            except Exception:
                v = 0.0
            if v > 0:
                bucket[m].append(v)

    baselines: dict[str, dict[str, tuple[float, float, int]]] = {}
    for bracket, vals in by_bracket.items():
        baselines[bracket] = {}
        for m, arr in vals.items():
            if not arr:
                continue
            mu = _mean(arr)
            sd = _std(arr, mu)
            baselines[bracket][m] = (mu, sd, len(arr))

    return baselines
