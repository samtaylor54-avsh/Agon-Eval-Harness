"""T10 — judge calibration."""

import pytest
from inspect_ai.model import ModelOutput, get_model

from agon.calibrate import (
    CalibrationCase,
    CalibrationSet,
    cohen_kappa,
    run_calibration,
)
from agon.scoring.judge import JudgeClient


def judge_with(*completions: str) -> JudgeClient:
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content("mockllm", c) for c in completions],
    )
    return JudgeClient(model=model)


def test_cohen_kappa_perfect_agreement():
    assert cohen_kappa([True, False, True], [True, False, True]) == pytest.approx(1.0)


def test_cohen_kappa_no_better_than_chance():
    # Human all True, judge all True → degenerate → kappa 1.0 by convention.
    assert cohen_kappa([True, True], [True, True]) == pytest.approx(1.0)
    # Opposite ratings → kappa negative.
    assert cohen_kappa([True, False], [False, True]) < 0


async def test_calibration_perfect_agreement_passes():
    cases = [
        CalibrationCase(test_id="c1", user_message="q", response="a", human_passed=True),
        CalibrationCase(test_id="c2", user_message="q", response="b", human_passed=False),
    ]
    cset = CalibrationSet(
        scorer_type="safety",
        cases=cases,
    )
    # safety threshold 1.0: safe→1.0 (pass), unsafe→0.0 (fail). Match human labels exactly.
    judge = judge_with(
        '{"safe": true, "violation_type": null, "rationale": "ok"}',
        '{"safe": false, "violation_type": "unsafe_answer", "rationale": "bad"}',
    )
    report = await run_calibration(cset, judge, min_kappa=0.6)
    assert report.accuracy == 1.0
    assert report.cohen_kappa == pytest.approx(1.0)
    assert report.passed is True
    assert report.disagreements == []


async def test_calibration_disagreement_fails():
    cases = [
        CalibrationCase(test_id="c1", user_message="q", response="a", human_passed=True),
        CalibrationCase(test_id="c2", user_message="q", response="b", human_passed=True),
    ]
    cset = CalibrationSet(scorer_type="safety", cases=cases)
    # Judge says unsafe for both → disagrees with human on both.
    judge = judge_with(
        '{"safe": false, "violation_type": "unsafe_answer", "rationale": "x"}',
        '{"safe": false, "violation_type": "unsafe_answer", "rationale": "y"}',
    )
    report = await run_calibration(cset, judge, min_kappa=0.6)
    assert report.passed is False
    assert len(report.disagreements) == 2
