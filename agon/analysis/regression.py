"""RegressionComparator — compare a current run against a baseline (PRD §25.15)."""

from __future__ import annotations

from inspect_ai.log import EvalLog

from agon.analysis.logs import RunDigest, digest
from agon.schemas import RegressionReport

DEFAULT_EPSILON = 0.05
HIGH_RISK = {"high", "critical"}


def compare_digests(
    current: RunDigest, baseline: RunDigest, *, epsilon: float = DEFAULT_EPSILON
) -> RegressionReport:
    cur = current.record_map()
    base = baseline.record_map()
    common = sorted(set(cur) & set(base))

    new_failures = [t for t in common if base[t].passed and not cur[t].passed]
    fixed_failures = [t for t in common if not base[t].passed and cur[t].passed]
    unchanged_failures = [t for t in common if not base[t].passed and not cur[t].passed]

    score_drops: list[tuple[str, float, float]] = []
    score_improvements: list[tuple[str, float, float]] = []
    for t in common:
        old, new = base[t].composite_score, cur[t].composite_score
        if new < old - epsilon:
            score_drops.append((t, old, new))
        elif new > old + epsilon:
            score_improvements.append((t, old, new))

    category_regressions: dict[str, tuple[float, float]] = {}
    for cat, new_rate in current.pass_rate_by_category.items():
        old_rate = baseline.pass_rate_by_category.get(cat)
        if old_rate is not None and new_rate < old_rate - epsilon:
            category_regressions[cat] = (old_rate, new_rate)

    severe_drop = any(cur[t].risk_level in HIGH_RISK for t, _o, _n in score_drops)
    regression_detected = bool(new_failures) or severe_drop

    return RegressionReport(
        current_run_id=current.run_id,
        baseline_run_id=baseline.run_id,
        new_failures=new_failures,
        fixed_failures=fixed_failures,
        unchanged_failures=unchanged_failures,
        score_drops=score_drops,
        score_improvements=score_improvements,
        category_regressions=category_regressions,
        regression_detected=regression_detected,
    )


def compare_runs(
    current_log: EvalLog, baseline_log: EvalLog, *, epsilon: float = DEFAULT_EPSILON
) -> RegressionReport:
    return compare_digests(digest(current_log), digest(baseline_log), epsilon=epsilon)
