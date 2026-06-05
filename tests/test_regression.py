"""T8 — regression comparison."""

from agon.analysis.logs import RunDigest, SampleRecord
from agon.analysis.regression import compare_digests


def rec(test_id, passed, score, risk="medium", category="c"):
    return SampleRecord(
        test_id=test_id,
        passed=passed,
        composite_score=score,
        category=category,
        risk_level=risk,
    )


def make_digest(run_id, records):
    passed = sum(1 for r in records if r.passed)
    cats: dict[str, list[int]] = {}
    for r in records:
        cats.setdefault(r.category, [0, 0])
        cats[r.category][0] += int(r.passed)
        cats[r.category][1] += 1
    return RunDigest(
        run_id=run_id,
        task="t",
        records=records,
        overall_pass_rate=passed / len(records),
        pass_rate_by_category={k: v[0] / v[1] for k, v in cats.items()},
        pass_rate_by_risk={},
        top_failure_labels=[],
        error_count=0,
    )


def test_detects_new_failure():
    base = make_digest("base", [rec("a", True, 0.9), rec("b", True, 0.9)])
    cur = make_digest("cur", [rec("a", True, 0.9), rec("b", False, 0.2)])
    reg = compare_digests(cur, base)
    assert reg.new_failures == ["b"]
    assert reg.regression_detected is True


def test_detects_fixed_failure():
    base = make_digest("base", [rec("a", False, 0.2)])
    cur = make_digest("cur", [rec("a", True, 0.95)])
    reg = compare_digests(cur, base)
    assert reg.fixed_failures == ["a"]
    assert reg.regression_detected is False


def test_score_drop_high_risk_triggers_regression():
    # Still passing, but a high-risk score dropped > epsilon → regression.
    base = make_digest("base", [rec("a", True, 0.95, risk="high")])
    cur = make_digest("cur", [rec("a", True, 0.80, risk="high")])
    reg = compare_digests(cur, base)
    assert ("a", 0.95, 0.80) in reg.score_drops
    assert reg.regression_detected is True


def test_low_risk_drop_no_regression():
    base = make_digest("base", [rec("a", True, 0.95, risk="low")])
    cur = make_digest("cur", [rec("a", True, 0.80, risk="low")])
    reg = compare_digests(cur, base)
    assert reg.score_drops  # recorded
    assert reg.regression_detected is False  # but low-risk → not flagged


def test_category_regression():
    base = make_digest(
        "base", [rec("a", True, 0.9, category="rag"), rec("b", True, 0.9, category="rag")]
    )
    cur = make_digest(
        "cur", [rec("a", True, 0.9, category="rag"), rec("b", False, 0.2, category="rag")]
    )
    reg = compare_digests(cur, base)
    assert "rag" in reg.category_regressions
