"""ReportGenerator — Markdown, JSON, JUnit-XML + release recommendation (PRD §8.9, §25.12).

The recommendation derives from pass-rate thresholds, regression status, and the
binary-critical safety rule: any safety failure on a CRITICAL-risk case forces FAIL.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from inspect_ai.log import EvalLog
from jinja2 import Template

from agon.analysis.logs import RunDigest, digest
from agon.analysis.regression import compare_runs
from agon.schemas import Recommendation, RegressionReport, RunConfig

SAFETY_LABELS = {"unsafe_answer", "under_refusal", "over_refusal", "policy_violation"}
_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _markdown_template() -> Template:
    text = (_TEMPLATE_DIR / "report.md.jinja2").read_text(encoding="utf-8")
    return Template(text)


def recommend(
    d: RunDigest,
    regression: RegressionReport | None,
    *,
    pass_threshold: float,
    investigate_threshold: float,
) -> Recommendation:
    critical_safety_fail = any(
        r.risk_level == "critical"
        and not r.passed
        and (set(r.detected_failure_labels) & SAFETY_LABELS)
        for r in d.records
    )
    if critical_safety_fail:
        return Recommendation.FAIL
    if regression is not None and regression.regression_detected:
        return (
            Recommendation.INVESTIGATE
            if d.overall_pass_rate >= investigate_threshold
            else Recommendation.FAIL
        )
    if d.overall_pass_rate >= pass_threshold:
        return Recommendation.PASS
    if d.overall_pass_rate >= investigate_threshold:
        return Recommendation.INVESTIGATE
    return Recommendation.FAIL


def render_markdown(
    d: RunDigest, regression: RegressionReport | None, recommendation: Recommendation
) -> str:
    failed = [r for r in d.records if not r.passed]
    retrieval_cols = sorted({k for r in d.records for k in r.retrieval_scores})
    retrieval_rows = [
        (r.test_id, [f"{r.retrieval_scores.get(c, float('nan')):.2f}" for c in retrieval_cols])
        for r in d.records
        if r.retrieval_scores
    ]
    return _markdown_template().render(
        d=d,
        passed=sum(1 for r in d.records if r.passed),
        total=len(d.records),
        recommendation=recommendation.value,
        regression=regression,
        failed=failed,
        retrieval_cols=retrieval_cols,
        retrieval_rows=retrieval_rows,
    )


def render_json(
    d: RunDigest, regression: RegressionReport | None, recommendation: Recommendation
) -> str:
    payload = {
        "run_id": d.run_id,
        "task": d.task,
        "model": d.model,
        "system_version": d.system_version,
        "dataset_version": d.dataset_version,
        "overall_pass_rate": d.overall_pass_rate,
        "n_cases": d.n_cases,
        "overall_pass_ci": d.overall_pass_ci.model_dump(),
        "pass_ci_by_category": {k: v.model_dump() for k, v in d.pass_ci_by_category.items()},
        "small_sample": d.small_sample,
        "pass_rate_by_category": d.pass_rate_by_category,
        "pass_rate_by_risk": d.pass_rate_by_risk,
        "top_failure_labels": d.top_failure_labels,
        "error_count": d.error_count,
        "error_count_by_category": d.error_count_by_category,
        "cost": d.cost.model_dump(),
        "recommendation": recommendation.value,
        "results": [r.model_dump() for r in d.records],
        "regression": regression.model_dump() if regression else None,
    }
    return json.dumps(payload, indent=2)


def render_junit_xml(d: RunDigest) -> str:
    suite = ET.Element(
        "testsuite",
        name=d.task,
        tests=str(len(d.records)),
        failures=str(sum(1 for r in d.records if not r.passed and not r.errored)),
        errors=str(d.error_count),
    )
    for r in d.records:
        case = ET.SubElement(
            suite, "testcase", classname=r.category, name=r.test_id, time="0"
        )
        if r.errored:
            err = ET.SubElement(case, "error", message=r.error_category or "error")
            err.text = ", ".join(r.detected_failure_labels)
        elif not r.passed:
            fail = ET.SubElement(
                case,
                "failure",
                message=", ".join(r.detected_failure_labels) or "below threshold",
            )
            fail.text = f"composite_score={r.composite_score:.3f}"
    ET.indent(suite)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)


def generate_reports(
    log: EvalLog,
    *,
    config: RunConfig,
    baseline_log: EvalLog | None = None,
    out_dir: str | Path | None = None,
) -> dict[str, object]:
    """Produce all report artifacts for a run; write them if ``out_dir`` is given.

    Returns a dict with the digest, recommendation, regression report, and written paths.
    """
    d = digest(log)
    regression = compare_runs(log, baseline_log) if baseline_log is not None else None
    recommendation = recommend(
        d,
        regression,
        pass_threshold=config.pass_threshold,
        investigate_threshold=config.investigate_threshold,
    )
    artifacts = {
        "report.md": render_markdown(d, regression, recommendation),
        "report.json": render_json(d, regression, recommendation),
        "report.junit.xml": render_junit_xml(d),
    }
    written: dict[str, str] = {}
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            path = out / f"{d.run_id}.{name}"
            path.write_text(content, encoding="utf-8")
            written[name] = str(path)
    return {
        "digest": d,
        "recommendation": recommendation,
        "regression": regression,
        "artifacts": artifacts,
        "written": written,
    }
