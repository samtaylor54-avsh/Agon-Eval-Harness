"""T11 — human review store."""

from agon.review import load_reviews, save_review
from agon.schemas import ReviewRecord


def test_review_round_trip_is_append_only(tmp_path):
    r1 = ReviewRecord(
        run_id="run-1", test_id="a", reviewer="sam",
        override_passed=False, notes="judge too lenient", timestamp="2026-06-04T00:00:00Z",
    )
    r2 = ReviewRecord(
        run_id="run-1", test_id="a", reviewer="sam",
        override_passed=True, notes="reconsidered", timestamp="2026-06-04T01:00:00Z",
    )
    save_review(r1, tmp_path)
    save_review(r2, tmp_path)
    reviews = load_reviews("run-1", tmp_path)
    # Both rows retained — overrides append, never edit.
    assert len(reviews) == 2
    assert reviews[0].override_passed is False
    assert reviews[1].override_passed is True


def test_load_reviews_empty_when_none(tmp_path):
    assert load_reviews("nope", tmp_path) == []
