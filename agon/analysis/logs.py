"""Read Inspect ``EvalLog`` files into harness-friendly digests (PRD §8.7, §8.9).

Inspect's ``.eval`` log is the immutable results store. We never mutate it; we read the
epoch-reduced per-sample scores plus our scorer metadata into a ``RunDigest`` that the
reporting and regression layers consume.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log
from pydantic import BaseModel, ConfigDict, Field

from agon.analysis.errors import ErrorCategory, classify_sample
from agon.cost import CostSummary, summarize_cost
from agon.schemas import Interval
from agon.stats import small_sample as is_small_sample
from agon.stats import wilson_interval
from agon.sut.contract import TokenUsage

AGON_SCORER = "agon_scorer"


class SampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: str
    passed: bool
    composite_score: float
    category: str
    risk_level: str
    detected_failure_labels: list[str] = Field(default_factory=list)
    retrieval_scores: dict[str, float] = Field(default_factory=dict)
    errored: bool = False
    error_category: str | None = None


class RunDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task: str
    model: str | None = None
    system_version: str = "unversioned"
    dataset_version: str = ""
    created: str = ""
    records: list[SampleRecord]
    overall_pass_rate: float
    pass_rate_by_category: dict[str, float]
    pass_rate_by_risk: dict[str, float]
    top_failure_labels: list[tuple[str, int]]
    error_count: int
    error_count_by_category: dict[str, int] = Field(default_factory=dict)
    cost: CostSummary = Field(default_factory=CostSummary)
    n_cases: int = 0
    overall_pass_ci: Interval = Field(
        default_factory=lambda: Interval(point=0.0, low=0.0, high=1.0)
    )
    pass_ci_by_category: dict[str, Interval] = Field(default_factory=dict)
    small_sample: bool = False

    def record_map(self) -> dict[str, SampleRecord]:
        return {r.test_id: r for r in self.records}


def load_log(path: str | Path) -> EvalLog:
    return read_eval_log(str(path))


def _reduced_samples(log: EvalLog) -> list[tuple[str, Any, dict[str, Any]]]:
    """Return (test_id, value, metadata) per test, preferring epoch reductions."""
    out: list[tuple[str, Any, dict[str, Any]]] = []
    if log.reductions:
        reduction = next((r for r in log.reductions if r.scorer == AGON_SCORER), log.reductions[0])
        for rs in reduction.samples:
            out.append((str(rs.sample_id), rs.value, rs.metadata or {}))
        return out
    # Fallback (epochs == 1, no reductions): use raw samples.
    for sample in log.samples or []:
        score = (sample.scores or {}).get(AGON_SCORER)
        if score is not None:
            out.append((str(sample.id), score.value, score.metadata or {}))
    return out


def _record_from_score(test_id: str, value: Any, meta: dict[str, Any]) -> SampleRecord:
    """Build a SampleRecord from a scored sample's (value, scorer-metadata)."""
    passed = float(value) >= 0.5
    scorer_errored = bool(meta.get("errored", False))
    return SampleRecord(
        test_id=test_id,
        passed=passed,
        composite_score=float(meta.get("composite_score", 1.0 if passed else 0.0)),
        category=str(meta.get("category", "uncategorized")),
        risk_level=str(meta.get("risk_level", "medium")),
        detected_failure_labels=list(meta.get("detected_failure_labels", [])),
        retrieval_scores=dict(meta.get("retrieval_scores", {})),
        errored=scorer_errored,
        error_category=ErrorCategory.SCORER.value if scorer_errored else None,
    )


def _errored_samples(log: EvalLog, scored_ids: set[str]) -> list[SampleRecord]:
    """Promote samples that errored/limited *before* scoring (no AGON_SCORER score, so absent
    from the scored records) into visible, categorized records. Without this, model/SUT/timeout
    errors silently vanish from the digest.
    """
    records: list[SampleRecord] = []
    seen: set[str] = set()
    for sample in log.samples or []:
        sid = str(sample.id)
        if sid in scored_ids or sid in seen:
            continue
        category = classify_sample(sample)
        if category is None:
            continue
        seen.add(sid)
        meta = sample.metadata or {}
        records.append(
            SampleRecord(
                test_id=sid,
                passed=False,
                composite_score=0.0,
                category=str(meta.get("category", "uncategorized")),
                risk_level=str(meta.get("risk_level", "medium")),
                errored=True,
                error_category=category.value,
            )
        )
    return records


def sample_records(log: EvalLog) -> list[SampleRecord]:
    scored = list(_reduced_samples(log))
    records = [_record_from_score(tid, value, meta) for tid, value, meta in scored]
    scored_ids = {tid for tid, _v, _m in scored}
    records.extend(_errored_samples(log, scored_ids))
    return records


def _rate(passed: int, total: int) -> float:
    return passed / total if total else 0.0


def build_digest(
    records: list[SampleRecord],
    *,
    run_id: str,
    task: str,
    model: str | None,
    system_version: str,
    dataset_version: str,
    created: str,
    cost: CostSummary,
) -> RunDigest:
    """Compute a RunDigest from a record set (shared by digest() and resume merge)."""
    total = len(records)
    passed = sum(1 for r in records if r.passed)

    cat_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    risk_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    label_counter: Counter[str] = Counter()
    error_by_cat: Counter[str] = Counter()
    for r in records:
        cat_pass[r.category][0] += int(r.passed)
        cat_pass[r.category][1] += 1
        risk_pass[r.risk_level][0] += int(r.passed)
        risk_pass[r.risk_level][1] += 1
        if not r.passed:
            label_counter.update(r.detected_failure_labels)
        if r.error_category:
            error_by_cat[r.error_category] += 1

    overall_pass_ci = wilson_interval(passed, total)
    pass_ci_by_category = {k: wilson_interval(v[0], v[1]) for k, v in sorted(cat_pass.items())}

    return RunDigest(
        run_id=run_id,
        task=task,
        model=model,
        system_version=system_version,
        dataset_version=dataset_version,
        created=created,
        records=records,
        overall_pass_rate=_rate(passed, total),
        pass_rate_by_category={k: _rate(v[0], v[1]) for k, v in sorted(cat_pass.items())},
        pass_rate_by_risk={k: _rate(v[0], v[1]) for k, v in sorted(risk_pass.items())},
        top_failure_labels=label_counter.most_common(),
        error_count=sum(1 for r in records if r.errored),
        error_count_by_category=dict(error_by_cat),
        cost=cost,
        n_cases=total,
        overall_pass_ci=overall_pass_ci,
        pass_ci_by_category=pass_ci_by_category,
        small_sample=is_small_sample(total),
    )


def digest(log: EvalLog) -> RunDigest:
    records = sample_records(log)

    stats = getattr(log, "stats", None)
    model_usage = getattr(stats, "model_usage", {}) or {}
    usage_by_model = {
        model_name: TokenUsage(
            input=mu.input_tokens, output=mu.output_tokens, total=mu.total_tokens
        )
        for model_name, mu in model_usage.items()
    }
    cost = summarize_cost(usage_by_model)

    meta = log.eval.metadata or {}
    return build_digest(
        records,
        run_id=log.eval.run_id,
        task=log.eval.task,
        model=log.eval.model,
        system_version=str(meta.get("system_version", "unversioned")),
        dataset_version=str(meta.get("dataset_version", "")),
        created=log.eval.created or "",
        cost=cost,
    )


def find_run(log_dir: str | Path, run_id: str) -> EvalLog:
    """Locate a log by run_id within a directory."""
    for info in list_eval_logs(str(log_dir)):
        log = read_eval_log(info.name)
        if log.eval.run_id == run_id:
            return log
    raise FileNotFoundError(f"no eval log with run_id={run_id!r} in {log_dir}")


def latest_run(log_dir: str | Path, task: str | None = None) -> EvalLog:
    """Most recent log in a directory, optionally filtered by task name."""
    logs = [read_eval_log(info.name) for info in list_eval_logs(str(log_dir))]
    if task is not None:
        logs = [lg for lg in logs if lg.eval.task == task]
    if not logs:
        suffix = f" for task {task}" if task else ""
        raise FileNotFoundError(f"no eval logs in {log_dir}{suffix}")
    return max(logs, key=lambda lg: lg.eval.created or "")
