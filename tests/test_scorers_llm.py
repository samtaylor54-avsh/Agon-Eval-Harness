"""T5 — LLM-as-judge scorers (offline via mockllm judge)."""

import pytest
from inspect_ai.model import ModelOutput, get_model

from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
from agon.scoring import default_registry
from agon.scoring.judge import JudgeClient, JudgeParseError
from agon.sut import SUTResponse


def judge_with(*completions: str) -> JudgeClient:
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content("mockllm", c) for c in completions],
    )
    return JudgeClient(model=model)


def make_case(expected: ExpectedBehavior | None = None, scorer_type: str = "rubric") -> AgonCase:
    return AgonCase(
        test_id="t",
        name="n",
        category="c",
        input={"user_message": "What is the leave policy?"},
        expected=expected or ExpectedBehavior(),
        scoring=[
            ScoringSpec(
                type=scorer_type,
                pass_threshold=1.0 if scorer_type == "safety" else 0.5,
            )
        ],
    )


def spec(scorer_type: str, **params) -> ScoringSpec:
    threshold = 1.0 if scorer_type == "safety" else 0.5
    return ScoringSpec(type=scorer_type, pass_threshold=threshold, params=params)


async def run(scorer_type, case, response, judge, **params):
    scorer = default_registry.get(scorer_type)
    return await scorer.score(case, response, spec(scorer_type, **params), judge=judge)


# ------------------------------- rubric ------------------------------- #
async def test_rubric_normalizes_score_over_max():
    case = make_case(ExpectedBehavior(expected_answer="ref"))
    judge = judge_with('{"score": 2, "rationale": "mostly correct"}')
    rubric = {0: "bad", 1: "weak", 2: "good", 3: "perfect"}
    out = await run("rubric", case, SUTResponse(final_answer="ans"), judge, rubric=rubric)
    assert out.native_score == 2
    assert out.normalized_score == pytest.approx(2 / 3)
    assert out.rationale == "mostly correct"


async def test_rubric_parse_failure_raises_after_retry():
    case = make_case()
    judge = judge_with("not json", "still not json")  # 2 calls = initial + 1 retry
    rubric = {0: "bad", 1: "good"}
    with pytest.raises(JudgeParseError):
        await run("rubric", case, SUTResponse(final_answer="ans"), judge, rubric=rubric)


async def test_rubric_requires_judge():
    case = make_case()
    with pytest.raises(ValueError):
        await run("rubric", case, SUTResponse(final_answer="ans"), None, rubric={0: "x", 1: "y"})


# Adversarial-review pins: valid JSON with a missing/null score is a judge-output problem,
# raised as JudgeParseError (-> judge_error label), NOT a TypeError that kills the run.
async def test_rubric_null_score_is_judge_error():
    case = make_case()
    judge = judge_with('{"score": null, "rationale": "confused judge"}')
    with pytest.raises(JudgeParseError):
        await run("rubric", case, SUTResponse(final_answer="ans"), judge, rubric={0: "x", 1: "y"})


async def test_answer_relevance_missing_or_null_value_is_judge_error():
    case = make_case(scorer_type="answer_relevance")
    judge = judge_with('{"relevance": null}')
    with pytest.raises(JudgeParseError):
        await run("answer_relevance", case, SUTResponse(final_answer="ans"), judge)
    judge = judge_with('{"unexpected": 1}')
    with pytest.raises(JudgeParseError):
        await run("answer_relevance", case, SUTResponse(final_answer="ans"), judge)


# ------------------------------- safety ------------------------------- #
async def test_safety_safe_is_one():
    case = make_case(scorer_type="safety")
    judge = judge_with('{"safe": true, "violation_type": null, "rationale": "fine"}')
    out = await run("safety", case, SUTResponse(final_answer="ok"), judge)
    assert out.normalized_score == 1.0
    assert out.labels == []


async def test_safety_unsafe_is_zero_with_labels():
    case = make_case(scorer_type="safety")
    judge = judge_with('{"safe": false, "violation_type": "under_refusal", "rationale": "bad"}')
    out = await run("safety", case, SUTResponse(final_answer="harmful"), judge)
    assert out.normalized_score == 0.0
    assert "unsafe_answer" in out.labels
    assert "under_refusal" in out.labels


# ------------------------------- faithfulness ------------------------------- #
async def test_faithfulness_half_supported():
    case = make_case(scorer_type="faithfulness")
    response = SUTResponse(final_answer="a then b", retrieved_documents=["ctx"])
    judge = judge_with(
        '{"claims": ["a", "b"]}',
        '{"supported": true}',
        '{"supported": false}',
    )
    out = await run("faithfulness", case, response, judge)
    assert out.normalized_score == 0.5
    assert "unsupported_claim" in out.labels


async def test_faithfulness_empty_claims_is_one():
    case = make_case(scorer_type="faithfulness")
    judge = judge_with('{"claims": []}')
    out = await run("faithfulness", case, SUTResponse(final_answer=""), judge)
    assert out.normalized_score == 1.0


# ------------------------------- context_precision ------------------------------- #
async def test_context_precision_first_relevant():
    case = make_case(scorer_type="context_precision")
    response = SUTResponse(final_answer="x", retrieved_documents=["d1", "d2"])
    judge = judge_with('{"relevant": true}', '{"relevant": false}')
    out = await run("context_precision", case, response, judge)
    assert out.normalized_score == 1.0


async def test_context_precision_no_docs_is_miss():
    case = make_case(scorer_type="context_precision")
    judge = judge_with()  # never called
    out = await run("context_precision", case, SUTResponse(final_answer="x"), judge)
    assert out.normalized_score == 0.0
    assert "retrieval_miss" in out.labels


# ------------------------------- answer_relevance ------------------------------- #
async def test_answer_relevance_passthrough():
    case = make_case(scorer_type="answer_relevance")
    judge = judge_with('{"relevance": 0.8}')
    out = await run("answer_relevance", case, SUTResponse(final_answer="x"), judge)
    assert out.normalized_score == pytest.approx(0.8)
