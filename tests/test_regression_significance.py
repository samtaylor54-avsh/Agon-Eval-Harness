"""Phase 3 M6 -- regression detection gains a two-proportion test + small-sample flag."""

from agon.analysis.logs import RunDigest, SampleRecord
from agon.analysis.regression import compare_digests
from agon.schemas import ProportionTest


def _digest(run_id, passed_flags):
    records = [
        SampleRecord(
            test_id=f"t{i}",
            passed=p,
            composite_score=1.0 if p else 0.0,
            category="c",
            risk_level="medium",
        )
        for i, p in enumerate(passed_flags)
    ]
    passed = sum(passed_flags)
    total = len(passed_flags)
    return RunDigest(
        run_id=run_id,
        task="t",
        records=records,
        overall_pass_rate=passed / total,
        pass_rate_by_category={"c": passed / total},
        pass_rate_by_risk={"medium": passed / total},
        top_failure_labels=[],
        error_count=0,
    )


def test_regression_report_has_pass_rate_test():
    # 9/10 baseline vs 8/10 current -- a small, non-significant drop.
    base = _digest("base", [True] * 9 + [False])
    cur = _digest("cur", [True] * 8 + [False] * 2)
    report = compare_digests(cur, base)
    assert isinstance(report.pass_rate_test, ProportionTest)
    assert report.pass_rate_test.diff < 0  # current is lower
    assert report.small_sample is True  # n=10 < 30
    # The existing gate is unchanged: a new failure still trips it.
    assert report.regression_detected is True
    assert "t9" not in report.new_failures  # t9 failed in both -> unchanged, not new


def test_regression_significant_drop_flagged_in_test_only():
    # Large suites, a clearly significant drop, but the gate logic is the new-failure rule.
    base = _digest("base", [True] * 95 + [False] * 5)
    cur = _digest("cur", [True] * 80 + [False] * 20)
    report = compare_digests(cur, base)
    assert report.pass_rate_test.significant is True
    assert report.small_sample is False
