"""Pydantic schemas — the only types allowed to cross module boundaries.

Schema-first invariant (PRD §20.4.5): no data moves between modules except as a
validated Pydantic model. `extra="forbid"` everywhere except free-form metadata.
"""

from agon.schemas.models import (
    SAFETY_SCORER_TYPE,
    AgonCase,
    AgonDataset,
    CaseInput,
    Difficulty,
    ExpectedBehavior,
    Interval,
    JudgeConfig,
    ProportionTest,
    Recommendation,
    RegressionReport,
    ResilienceConfig,
    ReviewRecord,
    RiskLevel,
    RunConfig,
    ScoringSpec,
    SUTConfig,
)

__all__ = [
    "SAFETY_SCORER_TYPE",
    "AgonCase",
    "AgonDataset",
    "CaseInput",
    "Difficulty",
    "ExpectedBehavior",
    "Interval",
    "JudgeConfig",
    "ProportionTest",
    "Recommendation",
    "RegressionReport",
    "ResilienceConfig",
    "ReviewRecord",
    "RiskLevel",
    "RunConfig",
    "ScoringSpec",
    "SUTConfig",
]
