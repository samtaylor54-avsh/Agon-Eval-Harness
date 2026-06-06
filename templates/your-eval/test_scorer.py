"""Boundary test for your scorer. Run from this folder:  uv run pytest test_scorer.py
(Not collected by the agon suite -- testpaths=["tests"] -- it ships as an example to copy.)
"""

from __future__ import annotations

from scorer import MyScorer

from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
from agon.sut import SUTResponse


def _case(expected: str) -> AgonCase:
    return AgonCase(
        test_id="t1",
        name="t",
        category="c",
        input={"user_message": "q"},
        expected=ExpectedBehavior(expected_answer=expected),
        scoring=[ScoringSpec(type="my_scorer")],
    )


async def test_pass():
    out = await MyScorer().score(
        _case("paris"),
        SUTResponse(final_answer="The capital is Paris."),
        ScoringSpec(type="my_scorer"),
    )
    assert out.normalized_score == 1.0


async def test_fail():
    out = await MyScorer().score(
        _case("paris"), SUTResponse(final_answer="I don't know."), ScoringSpec(type="my_scorer")
    )
    assert out.normalized_score == 0.0
    assert out.labels == ["my_failure_label"]
