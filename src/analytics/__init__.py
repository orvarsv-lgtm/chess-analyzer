# src/analytics/__init__.py
"""Chess Analytics & Coaching Pipeline.

Modular, deterministic analytics layer that extracts structured insights
from engine analysis data and prepares them for AI-driven coaching.

Modules:
- schemas: Data models for all analytics outputs (LLM-ready JSON)
- blunder_classifier: Categorize blunders by type
- endgame_analyzer: Material-type breakdown for endgames
- opening_deviation: Theory deviation detection
- recurring_patterns: Cross-game pattern detection
- training_planner: Personalized weekly training plan
- peer_benchmark: Rating-based comparison
- aggregator: Compose all modules into final coach-ready summary
"""

from .schemas import (
    BlunderClassification,
    EndgameMaterialBreakdown,
    OpeningDeviationReport,
    RecurringPattern,
    WeeklyTrainingPlan,
    PeerBenchmark,
    CoachingSummary,
    PlayerProfile,
    PlaystyleProfile,
)
from .aggregator import generate_coaching_report

__all__ = [
    "BlunderClassification",
    "EndgameMaterialBreakdown",
    "OpeningDeviationReport",
    "RecurringPattern",
    "WeeklyTrainingPlan",
    "PeerBenchmark",
    "CoachingSummary",
    "PlayerProfile",
    "PlaystyleProfile",
    "generate_coaching_report",
]
