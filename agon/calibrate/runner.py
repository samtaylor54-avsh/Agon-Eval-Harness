"""Run a judge scorer over human-labeled cases and measure agreement (T10)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agon.schemas import SAFETY_SCORER_TYPE, AgonCase, ExpectedBehavior, ScoringSpec
from agon.scoring import default_registry
from agon.scoring.base import ScorerRegistry
from agon.scoring.judge import JudgeClient
from agon.sut import SUTResponse

DEFAULT_MIN_KAPPA = 0.6  # "substantial" agreement (Landis & Koch)


class CalibrationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: str
    user_message: str
    response: str  # the answer the judge must evaluate
    expected_answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    retrieved_documents: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    human_passed: bool  # the gold judgment


class CalibrationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_type: str
    pass_threshold: float | None = None
    cases: list[CalibrationCase] = Field(min_length=1)

    def threshold(self) -> float:
        if self.pass_threshold is not None:
            return self.pass_threshold
        return 1.0 if self.scorer_type == SAFETY_SCORER_TYPE else 0.5


class CalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_type: str
    n: int
    accuracy: float
    cohen_kappa: float
    min_kappa: float
    passed: bool
    disagreements: list[tuple[str, bool, bool]]  # (test_id, human, judge)


def cohen_kappa(human: list[bool], judge: list[bool]) -> float:
    """Cohen's kappa for two binary raters."""
    n = len(human)
    if n == 0:
        return 0.0
    po = sum(h == j for h, j in zip(human, judge, strict=True)) / n
    p_h = sum(human) / n
    p_j = sum(judge) / n
    pe = p_h * p_j + (1 - p_h) * (1 - p_j)
    if pe >= 1.0:
        return 1.0  # perfect, degenerate agreement
    return (po - pe) / (1 - pe)


def load_calibration_set(path: str | Path) -> CalibrationSet:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return CalibrationSet.model_validate(data)


async def run_calibration(
    cset: CalibrationSet,
    judge: JudgeClient,
    *,
    min_kappa: float = DEFAULT_MIN_KAPPA,
    registry: ScorerRegistry | None = None,
) -> CalibrationReport:
    registry = registry or default_registry
    scorer = registry.get(cset.scorer_type)
    threshold = cset.threshold()

    human_labels: list[bool] = []
    judge_labels: list[bool] = []
    disagreements: list[tuple[str, bool, bool]] = []

    for case in cset.cases:
        agon_case = AgonCase(
            test_id=case.test_id,
            name=case.test_id,
            category="calibration",
            input={"user_message": case.user_message},
            expected=ExpectedBehavior(expected_answer=case.expected_answer),
            scoring=[
                ScoringSpec(type=cset.scorer_type, pass_threshold=threshold, params=case.params)
            ],
        )
        response = SUTResponse(
            final_answer=case.response,
            citations=case.citations,
            retrieved_documents=case.retrieved_documents,
        )
        outcome = await scorer.score(agon_case, response, agon_case.scoring[0], judge=judge)
        judge_passed = outcome.normalized_score >= threshold
        human_labels.append(case.human_passed)
        judge_labels.append(judge_passed)
        if case.human_passed != judge_passed:
            disagreements.append((case.test_id, case.human_passed, judge_passed))

    n = len(cset.cases)
    accuracy = sum(h == j for h, j in zip(human_labels, judge_labels, strict=True)) / n
    kappa = cohen_kappa(human_labels, judge_labels)
    return CalibrationReport(
        scorer_type=cset.scorer_type,
        n=n,
        accuracy=accuracy,
        cohen_kappa=kappa,
        min_kappa=min_kappa,
        passed=kappa >= min_kappa,
        disagreements=disagreements,
    )
