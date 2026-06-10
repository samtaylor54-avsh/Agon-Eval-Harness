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


async def test_citation_out_of_scope_native_keeps_ungated_signal():
    # The out-of-scope gate zeroes normalized only; native carries the raw signal.
    case = make_case(
        ExpectedBehavior(citation_required=True, allowed_sources=["hr.pdf"]),
        "citation_check",
    )
    out = await run("citation_check", case, resp(citations=["unrelated.pdf#1"]))
    assert out.normalized_score == 0.0
    assert out.native_score == 1.0  # present + (vacuously) correct, just out of scope


# ------------------------------- regex_match ------------------------------- #
async def test_regex_match_search_pass():
    case = make_case(ExpectedBehavior(), "regex_match")
    out = await run("regex_match", case, resp("Order ID: ABC-1234 confirmed"), pattern=r"abc-\d{4}")
    assert out.normalized_score == 1.0  # case-insensitive by default
    assert out.labels == []


async def test_regex_match_fail_labels_pattern_mismatch():
    case = make_case(ExpectedBehavior(), "regex_match")
    out = await run("regex_match", case, resp("no id here"), pattern=r"abc-\d{4}")
    assert out.normalized_score == 0.0
    assert "pattern_mismatch" in out.labels


async def test_regex_match_case_sensitive():
    case = make_case(ExpectedBehavior(), "regex_match")
    out = await run(
        "regex_match", case, resp("abc-1234"), pattern=r"ABC-\d{4}", case_sensitive=True
    )
    assert out.normalized_score == 0.0


async def test_regex_match_full_match():
    case = make_case(ExpectedBehavior(), "regex_match")
    out = await run("regex_match", case, resp("  yes  "), pattern=r"yes|no", full_match=True)
    assert out.normalized_score == 1.0
    out = await run(
        "regex_match", case, resp("well, yes and no"), pattern=r"yes|no", full_match=True
    )
    assert out.normalized_score == 0.0


async def test_regex_match_missing_pattern_raises_and_preflight_catches():
    case = make_case(ExpectedBehavior(), "regex_match")
    scorer = default_registry.get("regex_match")
    with pytest.raises(ValueError):
        await scorer.score(case, resp("x"), spec("regex_match"))
    assert scorer.validate_spec(spec("regex_match"))  # non-empty problem list
    assert scorer.validate_spec(spec("regex_match", pattern="[unclosed"))
    assert scorer.validate_spec(spec("regex_match", pattern=r"\d+")) == []


# ------------------------------- numeric_tolerance ------------------------------- #
async def test_numeric_tolerance_exact():
    case = make_case(ExpectedBehavior(expected_answer="42"), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("The answer is 42."))
    assert out.normalized_score == 1.0


async def test_numeric_tolerance_within_abs_tol():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("roughly 3.15"), expected=3.14159, abs_tol=0.01)
    assert out.normalized_score == 1.0


async def test_numeric_tolerance_within_rel_tol():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("about 102"), expected=100, rel_tol=0.05)
    assert out.normalized_score == 1.0


async def test_numeric_tolerance_outside_tolerance():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("the total is 99"), expected=42, abs_tol=0.5)
    assert out.normalized_score == 0.0
    assert "numeric_mismatch" in out.labels
    assert out.details["closest_abs_diff"] == pytest.approx(57.0)


async def test_numeric_tolerance_no_number_in_answer():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("I do not know"), expected=42)
    assert out.normalized_score == 0.0
    assert out.details["candidates"] == []


async def test_numeric_tolerance_no_expected_is_zero_with_rationale():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("42"))
    assert out.normalized_score == 0.0
    assert "no expected value" in (out.rationale or "")


async def test_numeric_tolerance_non_numeric_expected_is_zero():
    case = make_case(ExpectedBehavior(expected_answer="forty-two"), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("42"))
    assert out.normalized_score == 0.0
    assert "not a finite number" in (out.rationale or "")


# Adversarial-review pins: hyphen-adjacent text must not read as negative numbers.
async def test_numeric_tolerance_range_text():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("estimated 40-44 units"), expected=44)
    assert out.normalized_score == 1.0  # was wrongly 0.0: "-44" extracted instead of 44
    assert 40.0 in out.details["candidates"] and 44.0 in out.details["candidates"]


async def test_numeric_tolerance_id_suffix_is_not_negative():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("see ticket ABC-1234"), expected=-1234)
    assert out.normalized_score == 0.0  # was wrongly passing via "-1234"


async def test_numeric_tolerance_leading_negative_still_works():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("the delta is -7.5 degrees"), expected=-7.5)
    assert out.normalized_score == 1.0


async def test_numeric_tolerance_thousands_separators():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("total: $1,234.56"), expected=1234.56)
    assert out.normalized_score == 1.0  # was wrongly split into [1.0, 234.56]


async def test_numeric_tolerance_list_commas_not_merged():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    out = await run("numeric_tolerance", case, resp("options are 1,2,3"), expected=2)
    assert out.normalized_score == 1.0  # "1,2,3" must stay three numbers, not become 123


async def test_numeric_tolerance_rejects_non_finite_and_bool_expected():
    case = make_case(ExpectedBehavior(), "numeric_tolerance")
    # expected "inf" + rel_tol would make tolerance infinite -> everything passes
    out = await run(
        "numeric_tolerance", case, resp("the answer is 7"), expected="inf", rel_tol=0.01
    )
    assert out.normalized_score == 0.0
    out = await run("numeric_tolerance", case, resp("1"), expected=True)
    assert out.normalized_score == 0.0
    scorer = default_registry.get("numeric_tolerance")
    assert scorer.validate_spec(spec("numeric_tolerance", expected="inf"))
    assert scorer.validate_spec(spec("numeric_tolerance", expected="nan"))
    assert scorer.validate_spec(spec("numeric_tolerance", expected=True))
    assert scorer.validate_spec(spec("numeric_tolerance", expected=42)) == []


async def test_regex_match_non_string_pattern_is_preflight_problem_not_crash():
    case = make_case(ExpectedBehavior(), "regex_match")
    scorer = default_registry.get("regex_match")
    problems = scorer.validate_spec(spec("regex_match", pattern=404))  # YAML int, easy mistake
    assert problems and "string" in problems[0]  # was: TypeError traceback, wrong exit code
    with pytest.raises(ValueError):
        await scorer.score(case, resp("404"), spec("regex_match", pattern=404))


# ------------------------------- semantic (gated) ------------------------------- #
async def test_semantic_similarity_identical():
    pytest.importorskip("sentence_transformers")
    case = make_case(
        ExpectedBehavior(expected_answer="a cat sat on the mat"), "semantic_similarity"
    )
    out = await run("semantic_similarity", case, resp("a cat sat on the mat"))
    assert out.normalized_score == pytest.approx(1.0, abs=0.02)
