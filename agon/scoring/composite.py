"""Composite scoring, failure-label derivation, and flake reducers (PRD §25.13-25.14, §24.4).

The generation composite deliberately EXCLUDES retrieval scorers (faithfulness,
context_precision, answer_relevance) — retrieval quality is reported separately so a strong
retriever can't mask weak generation, or vice versa (CLAUDE.md hard rule). Retrieval scorers
still gate pass/fail; they just don't contribute to the single generation number.
"""

from __future__ import annotations

from inspect_ai.scorer import ScoreReducer, at_least, max_score
from pydantic import BaseModel, ConfigDict, Field

from agon.schemas import AgonCase, ScoringSpec
from agon.scoring.base import ScoreOutcome
from agon.scoring.llm import RETRIEVAL_SCORERS

# Safety labels always surface, even when a case defines a failure_labels allow-list.
SAFETY_LABELS = {"unsafe_answer", "under_refusal", "over_refusal", "policy_violation"}

OutcomePair = tuple[ScoringSpec, ScoreOutcome]


class ScoredSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_type: str
    normalized_score: float
    passed: bool
    weight: float
    advisory: bool
    is_retrieval: bool
    native_score: float | str | bool
    rationale: str | None = None
    labels: list[str] = Field(default_factory=list)


class CompositeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    composite_score: float
    passed: bool
    scored: list[ScoredSpec]
    detected_failure_labels: list[str]
    retrieval_scores: dict[str, float] = Field(default_factory=dict)


def derive_labels(case: AgonCase, outcomes: list[OutcomePair]) -> list[str]:
    """Union scorer labels, intersected with the case allow-list (§25.14).

    Safety labels are always retained regardless of the allow-list.
    """
    union: set[str] = set()
    for _spec, outcome in outcomes:
        union |= set(outcome.labels)
    allow = set(case.failure_labels)
    if allow:
        kept = (union & allow) | (union & SAFETY_LABELS)
    else:
        kept = union
    return sorted(kept)


def evaluate(case: AgonCase, outcomes: list[OutcomePair]) -> CompositeResult:
    scored: list[ScoredSpec] = []
    gen_num = 0.0
    gen_den = 0.0
    retrieval: dict[str, float] = {}

    for spec, outcome in outcomes:
        is_retrieval = spec.type in RETRIEVAL_SCORERS
        passed = outcome.normalized_score >= spec.pass_threshold
        scored.append(
            ScoredSpec(
                scorer_type=spec.type,
                normalized_score=outcome.normalized_score,
                passed=passed,
                weight=spec.weight,
                advisory=spec.advisory,
                is_retrieval=is_retrieval,
                native_score=outcome.native_score,
                rationale=outcome.rationale,
                labels=outcome.labels,
            )
        )
        if is_retrieval:
            retrieval[spec.type] = outcome.normalized_score
        elif not spec.advisory:
            gen_num += spec.weight * outcome.normalized_score
            gen_den += spec.weight

    if gen_den > 0:
        composite = gen_num / gen_den
    else:
        # Only retrieval/advisory scorers present: fall back to mean of non-advisory.
        non_adv = [o.normalized_score for s, o in outcomes if not s.advisory]
        composite = sum(non_adv) / len(non_adv) if non_adv else 0.0

    # A case passes iff every required (non-advisory) scorer meets its threshold.
    required = [(s, o) for s, o in outcomes if not s.advisory]
    passed = (
        all(o.normalized_score >= s.pass_threshold for s, o in required) if required else True
    )

    return CompositeResult(
        composite_score=max(0.0, min(1.0, composite)),
        passed=passed,
        scored=scored,
        detected_failure_labels=derive_labels(case, outcomes),
        retrieval_scores=retrieval,
    )


def flake_reducer(rule: str, epochs: int) -> ScoreReducer:
    """Map a flake rule to an Inspect epoch reducer (§24.4).

    - "all"      → every repetition must pass   (at_least k=epochs)
    - "any"      → at least one passes          (max_score)
    - "majority" → more than half pass          (at_least k=epochs//2 + 1)
    """
    if rule == "any":
        return max_score()
    if rule == "majority":
        return at_least(epochs // 2 + 1)
    return at_least(epochs)  # "all" (default)
