"""Scoring: a registry of scorers + composite rollup (PRD §25)."""

from agon.scoring.base import (
    AgonScorer,
    ScoreOutcome,
    ScorerRegistry,
    default_registry,
)
from agon.scoring.composite import (
    CompositeResult,
    ScoredSpec,
    derive_labels,
    evaluate,
    flake_reducer,
)
from agon.scoring.judge import JudgeClient, JudgeParseError

__all__ = [
    "AgonScorer",
    "CompositeResult",
    "JudgeClient",
    "JudgeParseError",
    "ScoreOutcome",
    "ScoredSpec",
    "ScorerRegistry",
    "default_registry",
    "derive_labels",
    "evaluate",
    "flake_reducer",
]

# Importing the scorer modules registers them on the default registry as a side effect.
from agon.scoring import agent, llm, non_llm  # noqa: E402,F401
