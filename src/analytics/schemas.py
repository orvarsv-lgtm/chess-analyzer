# src/analytics/schemas.py
"""Data models for chess analytics outputs.

All models are designed to be:
- Deterministic (no LLM inference)
- JSON-serializable (LLM-ready)
- Extensible (easy to add fields)

These schemas define the contract between analytics modules and the LLM layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import json


@dataclass
class BlunderByType:
    """Breakdown of blunders by category."""
    hanging_piece: int = 0
    missed_tactic: int = 0
    endgame_technique: int = 0
    opening_error: int = 0
    king_safety: int = 0
    time_pressure: int = 0  # only if clock data exists
    overlooked_recapture: int = 0
    back_rank: int = 0
    pawn_structure: int = 0
    piece_activity: int = 0
    promotion_oversight: int = 0
    discovered_attack: int = 0
    unknown: int = 0

    def to_dict(self) -> dict[str, int]:
        return {k: v for k, v in asdict(self).items() if v > 0}


@dataclass
class BlunderExample:
    """Example blunder with context."""
    game_index: int
    move_number: int
    san: str
    blunder_type: str
    cp_loss: int
    phase: str
    fen_before: str | None = None


@dataclass
class BlunderClassification:
    """Module 1: Blunder Classification output."""
    total_blunders: int = 0
    total_mistakes: int = 0
    by_type: BlunderByType = field(default_factory=BlunderByType)
    by_phase: dict[str, int] = field(default_factory=dict)  # opening/middlegame/endgame -> count
    first_blunder_avg_move: float = 0.0
    blunder_rate_per_100_moves: float = 0.0
    examples: list[BlunderExample] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_blunders": self.total_blunders,
            "total_mistakes": self.total_mistakes,
            "by_type": self.by_type.to_dict(),
            "by_phase": self.by_phase,
            "first_blunder_avg_move": round(self.first_blunder_avg_move, 1),
            "blunder_rate_per_100_moves": round(self.blunder_rate_per_100_moves, 1),
            "examples": [asdict(e) for e in self.examples[:5]],  # limit examples
        }


@dataclass
class EndgameTypeStats:
    """Stats for a specific endgame material type."""
    games: int = 0
    positions: int = 0  # number of endgame moves/positions
    avg_cpl: int = 0  # rounded up
    blunder_count: int = 0
    blunder_rate_pct: int = 0  # blunders per 100 endgame moves, rounded
    wins_from_winning: int = 0  # converted winning positions
    losses_from_winning: int = 0  # blown winning positions
    conversion_rate_pct: int = 0  # win rate from winning positions

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v > 0 or k in ("games", "avg_cpl")}


@dataclass
class EndgameMaterialBreakdown:
    """Module 2: Endgame Material-Type Breakdown output."""
    king_pawn: EndgameTypeStats = field(default_factory=EndgameTypeStats)
    rook_endgames: EndgameTypeStats = field(default_factory=EndgameTypeStats)
    minor_piece: EndgameTypeStats = field(default_factory=EndgameTypeStats)
    queen_endgames: EndgameTypeStats = field(default_factory=EndgameTypeStats)
    mixed: EndgameTypeStats = field(default_factory=EndgameTypeStats)
    weakest_endgame_type: str = ""
    strongest_endgame_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        types = {
            "king_pawn": self.king_pawn.to_dict(),
            "rook_endgames": self.rook_endgames.to_dict(),
            "minor_piece": self.minor_piece.to_dict(),
            "queen_endgames": self.queen_endgames.to_dict(),
            "mixed": self.mixed.to_dict(),
        }
        # Filter out empty types
        types = {k: v for k, v in types.items() if v.get("games", 0) > 0 or v.get("positions", 0) > 0}
        return {
            "endgame_types": types,
            "weakest_endgame_type": self.weakest_endgame_type,
            "strongest_endgame_type": self.strongest_endgame_type,
        }


@dataclass
class OpeningDeviation:
    """Single opening deviation record."""
    opening: str
    eco: str
    games: int
    common_deviation_move: str
    deviation_move_number: float  # average
    avg_eval_loss_cp: int
    win_rate_pct: int
    draw_rate_pct: int
    loss_rate_pct: int


@dataclass
class OpeningDeviationReport:
    """Module 3: Opening Deviation + Evaluation Loss output."""
    total_games_with_deviation: int = 0
    avg_deviation_move: float = 0.0
    avg_eval_loss_on_deviation: int = 0
    deviations_by_opening: list[OpeningDeviation] = field(default_factory=list)
    most_costly_opening: str = ""
    most_accurate_opening: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_games_with_deviation": self.total_games_with_deviation,
            "avg_deviation_move": round(self.avg_deviation_move, 1),
            "avg_eval_loss_on_deviation": self.avg_eval_loss_on_deviation,
            "deviations_by_opening": [asdict(d) for d in self.deviations_by_opening[:10]],
            "most_costly_opening": self.most_costly_opening,
            "most_accurate_opening": self.most_accurate_opening,
        }


@dataclass
class RecurringPattern:
    """A detected recurring mistake pattern."""
    pattern_type: str  # e.g., "missed_tactic", "rook_passivity", "back_rank_weakness"
    description: str
    occurrences: int
    games_affected: int
    phase_concentration: str  # opening/middlegame/endgame or "all"
    severity: str  # "critical", "moderate", "minor"
    example_moves: list[str] = field(default_factory=list)


@dataclass
class RecurringPatternReport:
    """Module 4: Recurring Mistake Detection output."""
    patterns: list[RecurringPattern] = field(default_factory=list)
    most_critical_pattern: str = ""
    pattern_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recurring_patterns": [asdict(p) for p in self.patterns[:8]],
            "most_critical_pattern": self.most_critical_pattern,
            "pattern_count": self.pattern_count,
        }


@dataclass
class TrainingDay:
    """Single day in the training plan."""
    day: str
    theme: str
    focus_area: str
    suggested_exercises: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 30


@dataclass
class WeeklyTrainingPlan:
    """Module 5: Personalized Weekly Training Plan output."""
    primary_focus: str = ""
    secondary_focus: str = ""
    rationale: str = ""  # brief explanation of why this focus was chosen
    weekly_plan: list[TrainingDay] = field(default_factory=list)
    priority_endgame_types: list[str] = field(default_factory=list)
    priority_tactical_themes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_focus": self.primary_focus,
            "secondary_focus": self.secondary_focus,
            "rationale": self.rationale,
            "weekly_plan": [asdict(d) for d in self.weekly_plan],
            "priority_endgame_types": self.priority_endgame_types,
            "priority_tactical_themes": self.priority_tactical_themes,
        }


@dataclass
class PeerBenchmark:
    """Module 6: Peer Benchmarking output."""
    player_rating: int = 0
    rating_bracket: str = ""  # e.g., "1400-1600"
    sample_size: int = 0  # peer population size
    overall_cpl_percentile: int = 0
    opening_cpl_percentile: int = 0
    middlegame_cpl_percentile: int = 0
    endgame_cpl_percentile: int = 0
    blunder_rate_percentile: int = 0
    blunder_rate_vs_peers_pct: int = 0  # +34% means 34% worse than peers
    tactics_accuracy_percentile: int = 0
    strongest_vs_peers: str = ""  # phase or area
    weakest_vs_peers: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_rating": self.player_rating,
            "rating_bracket": self.rating_bracket,
            "sample_size": self.sample_size,
            "percentiles": {
                "overall_cpl": self.overall_cpl_percentile,
                "opening_cpl": self.opening_cpl_percentile,
                "middlegame_cpl": self.middlegame_cpl_percentile,
                "endgame_cpl": self.endgame_cpl_percentile,
                "blunder_rate": self.blunder_rate_percentile,
                "tactics_accuracy": self.tactics_accuracy_percentile,
            },
            "blunder_rate_vs_peers": f"{'+' if self.blunder_rate_vs_peers_pct >= 0 else ''}{self.blunder_rate_vs_peers_pct}%",
            "strongest_vs_peers": self.strongest_vs_peers,
            "weakest_vs_peers": self.weakest_vs_peers,
        }


@dataclass
class PlayerProfile:
    """Aggregated player profile for LLM context."""
    username: str = ""
    rating: int = 0
    games_analyzed: int = 0
    total_moves: int = 0
    overall_cpl: int = 0
    phase_cpls: dict[str, int] = field(default_factory=dict)  # opening/middlegame/endgame
    win_rate_pct: int = 0
    draw_rate_pct: int = 0
    loss_rate_pct: int = 0
    favorite_openings: list[str] = field(default_factory=list)
    time_control_preference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoachingSummary:
    """Final LLM-ready coaching summary.

    This is the contract between the analytics layer and the AI coach.
    The LLM receives ONLY this structure - never raw PGN or engine lines.
    """
    player_profile: PlayerProfile = field(default_factory=PlayerProfile)
    blunder_analysis: BlunderClassification = field(default_factory=BlunderClassification)
    endgame_breakdown: EndgameMaterialBreakdown = field(default_factory=EndgameMaterialBreakdown)
    opening_deviations: OpeningDeviationReport = field(default_factory=OpeningDeviationReport)
    recurring_patterns: RecurringPatternReport = field(default_factory=RecurringPatternReport)
    training_plan: WeeklyTrainingPlan = field(default_factory=WeeklyTrainingPlan)
    peer_comparison: PeerBenchmark = field(default_factory=PeerBenchmark)

    # Prioritized insights for LLM
    critical_issues: list[str] = field(default_factory=list)
    secondary_patterns: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to LLM-ready JSON structure."""
        return {
            "player_profile": self.player_profile.to_dict(),
            "blunder_analysis": self.blunder_analysis.to_dict(),
            "endgame_breakdown": self.endgame_breakdown.to_dict(),
            "opening_deviations": self.opening_deviations.to_dict(),
            "recurring_patterns": self.recurring_patterns.to_dict(),
            "training_plan": self.training_plan.to_dict(),
            "peer_comparison": self.peer_comparison.to_dict(),
            "critical_issues": self.critical_issues[:5],
            "secondary_patterns": self.secondary_patterns[:5],
            "strengths": self.strengths[:5],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
