"""Scorer protocol, normalized outcome, and registry (PRD §22.2, §25).

A scorer maps ``(AgonCase, SUTResponse, ScoringSpec)`` to a normalized ``ScoreOutcome`` in
``[0.0, 1.0]``. Judge-backed scorers additionally receive a ``JudgeClient``. Keeping this
logic independent of Inspect makes every normalization formula unit-testable at its boundaries;
the composite Inspect ``@scorer`` (T6) simply orchestrates these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agon.schemas import AgonCase, ScoringSpec
from agon.sut import SUTResponse

if TYPE_CHECKING:
    from agon.scoring.judge import JudgeClient


class ScoreOutcome(BaseModel):
    """Normalized result of a single scorer applied to a single response."""

    model_config = ConfigDict(extra="forbid")

    scorer_type: str
    native_score: float | str | bool
    normalized_score: float = Field(ge=0.0, le=1.0)
    labels: list[str] = Field(default_factory=list)
    rationale: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class AgonScorer(Protocol):
    scorer_type: str
    requires_judge: bool

    async def score(
        self,
        case: AgonCase,
        response: SUTResponse,
        spec: ScoringSpec,
        *,
        judge: JudgeClient | None = None,
    ) -> ScoreOutcome: ...


class ScorerRegistry:
    """Maps a scorer_type string to a scorer instance."""

    def __init__(self) -> None:
        self._scorers: dict[str, AgonScorer] = {}

    def register(self, scorer: AgonScorer) -> AgonScorer:
        self._scorers[scorer.scorer_type] = scorer
        return scorer

    def get(self, scorer_type: str) -> AgonScorer:
        if scorer_type not in self._scorers:
            raise KeyError(
                f"unknown scorer_type {scorer_type!r}; "
                f"registered: {sorted(self._scorers)}"
            )
        return self._scorers[scorer_type]

    def has(self, scorer_type: str) -> bool:
        return scorer_type in self._scorers

    def keys(self) -> list[str]:
        return sorted(self._scorers)


default_registry = ScorerRegistry()


def register(cls: type) -> type:
    """Class decorator: instantiate and register on the default registry."""
    default_registry.register(cls())
    return cls


# Helper used by several scorers.
def collapse_ws(text: str) -> str:
    return " ".join(text.split())
