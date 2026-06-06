"""Phase 3 M6 -- regression detection gains a two-proportion test + small-sample flag."""

from agon.analysis.logs import RunDigest, SampleRecord
from agon.analysis.regression import compare_digests
from agon.schemas import ProportionTest


def _digest(run_id, passed_flags, prefix="t"):
    records = [
        SampleRecord(
            test_id=f"{prefix}{i}",
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
    # Large suites, a clearly significant drop. The gate also fires here (15 new common
    # failures); this test pins that the significance/small-sample fields populate on a large run.
    base = _digest("base", [True] * 95 + [False] * 5)
    cur = _digest("cur", [True] * 80 + [False] * 20)
    report = compare_digests(cur, base)
    assert report.pass_rate_test.significant is True
    assert report.small_sample is False


def test_significant_aggregate_drop_with_disjoint_ids_does_not_trip_gate():
    # Disjoint test_ids: there are no *common* cases that newly failed, so the gate stays
    # silent -- yet the aggregate pass-rate test sees a significant drop. This is exactly the
    # information the test adds on top of the (deliberately unchanged) new-failure gate.
    base = _digest("base", [True] * 100, prefix="b")
    cur = _digest("cur", [True] * 80 + [False] * 20, prefix="u")
    report = compare_digests(cur, base)
    assert report.new_failures == []  # no shared ids -> nothing the gate can catch
    assert report.regression_detected is False  # gate silent...
    assert report.pass_rate_test.significant is True  # ...but the aggregate drop is real
