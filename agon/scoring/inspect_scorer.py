"""The single Inspect ``@scorer`` that orchestrates all of a case's scorers (T6).

For each sample it reconstructs the ``AgonCase`` from metadata, reads the normalized
``SUTResponse``, runs every configured scorer (judge-backed ones share one ``JudgeClient``),
rolls them up via :func:`agon.scoring.composite.evaluate`, and emits an Inspect ``Score`` whose
value is the binary pass (for accuracy/pass-rate metrics) with all detail in ``metadata``.
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, accuracy, scorer, stderr
from inspect_ai.solver import TaskState

from agon.dataset import METADATA_CASE_KEY
from agon.schemas import AgonCase
from agon.scoring.base import ScoreOutcome, ScorerRegistry, default_registry
from agon.scoring.composite import evaluate
from agon.scoring.judge import JudgeClient, JudgeParseError
from agon.sut import get_sut_response


@scorer(metrics=[accuracy(), stderr()])
def agon_scorer(
    judge: JudgeClient | None = None,
    registry: ScorerRegistry | None = None,
):
    judge = judge or JudgeClient()
    registry = registry or default_registry

    async def score(state: TaskState, target: Target) -> Score:
        case = AgonCase.model_validate(state.metadata[METADATA_CASE_KEY])
        response = get_sut_response(state)

        outcomes = []
        errored = False
        for spec in case.scoring:
            impl = registry.get(spec.type)
            try:
                outcome = await impl.score(case, response, spec, judge=judge)
            except JudgeParseError as exc:
                errored = True
                outcome = ScoreOutcome(
                    scorer_type=spec.type,
                    native_score=0.0,
                    normalized_score=0.0,
                    rationale=f"judge error: {exc}",
                    labels=["judge_error"],
                )
            outcomes.append((spec, outcome))

        result = evaluate(case, outcomes)
        passed = result.passed and not errored
        explanation = "; ".join(
            f"{s.scorer_type}={s.normalized_score:.2f}{'' if s.passed else ' (FAIL)'}"
            for s in result.scored
        )
        metadata = {
            "composite_score": result.composite_score,
            "passed": result.passed,
            "errored": errored,
            "category": case.category,
            "risk_level": case.risk_level.value,
            "detected_failure_labels": result.detected_failure_labels,
            "retrieval_scores": result.retrieval_scores,
            "scores": [s.model_dump() for s in result.scored],
        }
        return Score(
            value=1.0 if passed else 0.0,
            answer=response.final_answer,
            explanation=explanation,
            metadata=metadata,
        )

    return score
