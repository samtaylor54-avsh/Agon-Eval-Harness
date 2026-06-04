"""T4 — non-LLM scorer normalization at boundary values."""

import json

import pytest

from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
from agon.scoring import default_registry
from agon.sut import SUTResponse


def make_case(expected: ExpectedBehavior, scorer_type: str = "exact_match") -> AgonCase:
    return AgonCase(
        test_id="t",
        name="n",
        category="c",
        input={"user_message": "q"},
        expected=expected,
        scoring=[ScoringSpec(type=scorer_type)],
    )


def resp(answer: str = "", citations=None) -> SUTResponse:
    return SUTResponse(final_answer=answer, citations=citations or [])


def spec(scorer_type: str, **params) -> ScoringSpec:
    return ScoringSpec(type=scorer_type, params=params)


async def run(scorer_type: str, case: AgonCase, response: SUTResponse, **params):
    scorer = default_registry.get(scorer_type)
    return await scorer.score(case, response, spec(scorer_type, **params))


# ------------------------------- exact_match ------------------------------- #
@pytest.mark.parametrize(
    "expected,answer,want",
    [
        ("hello", "hello", 1.0),
        ("hello", "  HELLO  ", 1.0),  # case + whitespace normalized
        ("hello", "goodbye", 0.0),
    ],
)
async def test_exact_match(expected, answer, want):
    case = make_case(ExpectedBehavior(expected_answer=expected))
    out = await run("exact_match", case, resp(answer))
    assert out.normalized_score == want


async def test_exact_match_case_sensitive():
    case = make_case(ExpectedBehavior(expected_answer="Hello"))
    out = await run("exact_match", case, resp("hello"), case_sensitive=True)
    assert out.normalized_score == 0.0


async def test_exact_match_no_expected_is_zero():
    case = make_case(ExpectedBehavior())
    out = await run("exact_match", case, resp("anything"))
    assert out.normalized_score == 0.0


# ------------------------------- json_schema ------------------------------- #
SCHEMA = {"type": "object", "required": ["risk"], "properties": {"risk": {"type": "string"}}}


async def test_json_schema_valid():
    case = make_case(ExpectedBehavior(json_schema=SCHEMA), "json_schema")
    out = await run("json_schema", case, resp(json.dumps({"risk": "high"})))
    assert out.normalized_score == 1.0


async def test_json_schema_invalid_json():
    case = make_case(ExpectedBehavior(json_schema=SCHEMA), "json_schema")
    out = await run("json_schema", case, resp("not json"))
    assert out.normalized_score == 0.0
    assert "format_failure" in out.labels


async def test_json_schema_valid_json_failing_schema():
    case = make_case(ExpectedBehavior(json_schema=SCHEMA), "json_schema")
    out = await run("json_schema", case, resp(json.dumps({"wrong": 1})))
    assert out.normalized_score == 0.0
    assert out.details["validation_errors"]


# --------------------------- keyword_containment --------------------------- #
async def test_keyword_all_present():
    case = make_case(ExpectedBehavior(answer_contains=["alpha", "beta"]), "keyword_containment")
    out = await run("keyword_containment", case, resp("ALPHA and beta here"))
    assert out.normalized_score == 1.0


async def test_keyword_partial():
    case = make_case(ExpectedBehavior(answer_contains=["alpha", "beta"]), "keyword_containment")
    out = await run("keyword_containment", case, resp("only alpha"))
    assert out.normalized_score == 0.5
    assert "incomplete_answer" in out.labels


async def test_keyword_violation_zeroes_score():
    case = make_case(
        ExpectedBehavior(answer_contains=["alpha"], answer_not_contains=["secret"]),
        "keyword_containment",
    )
    out = await run("keyword_containment", case, resp("alpha but also secret"))
    assert out.normalized_score == 0.0
    assert "instruction_following_failure" in out.labels


# ------------------------------- rouge_l ------------------------------- #
async def test_rouge_identical():
    case = make_case(ExpectedBehavior(expected_answer="the quick brown fox"), "rouge_l")
    out = await run("rouge_l", case, resp("the quick brown fox"))
    assert out.normalized_score == pytest.approx(1.0)


async def test_rouge_disjoint():
    case = make_case(ExpectedBehavior(expected_answer="alpha beta gamma"), "rouge_l")
    out = await run("rouge_l", case, resp("xxxxx yyyyy zzzzz"))
    assert out.normalized_score == pytest.approx(0.0)


# ------------------------------- citation_check ------------------------------- #
async def test_citation_required_present_and_correct():
    case = make_case(
        ExpectedBehavior(
            citation_required=True,
            expected_citations=["hr.pdf#4.2"],
            allowed_sources=["hr.pdf"],
        ),
        "citation_check",
    )
    out = await run("citation_check", case, resp(citations=["hr.pdf#4.2"]))
    assert out.normalized_score == 1.0
    assert out.labels == []


async def test_citation_required_but_absent():
    case = make_case(
        ExpectedBehavior(citation_required=True, expected_citations=["hr.pdf#4.2"]),
        "citation_check",
    )
    out = await run("citation_check", case, resp(citations=[]))
    assert out.normalized_score == 0.0
    assert "missing_citation" in out.labels


async def test_citation_out_of_scope():
    case = make_case(
        ExpectedBehavior(citation_required=True, allowed_sources=["hr.pdf"]),
        "citation_check",
    )
    out = await run("citation_check", case, resp(citations=["unrelated.pdf#1"]))
    assert out.normalized_score == 0.0
    assert "wrong_citation" in out.labels


async def test_citation_not_required_no_citations_passes():
    case = make_case(ExpectedBehavior(citation_required=False), "citation_check")
    out = await run("citation_check", case, resp(citations=[]))
    assert out.normalized_score == 1.0


# ------------------------------- semantic (gated) ------------------------------- #
async def test_semantic_similarity_identical():
    pytest.importorskip("sentence_transformers")
    case = make_case(
        ExpectedBehavior(expected_answer="a cat sat on the mat"), "semantic_similarity"
    )
    out = await run("semantic_similarity", case, resp("a cat sat on the mat"))
    assert out.normalized_score == pytest.approx(1.0, abs=0.02)
