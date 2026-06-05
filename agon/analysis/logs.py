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


def sample_records(log: EvalLog) -> list[SampleRecord]:
    records: list[SampleRecord] = []
    for test_id, value, meta in _reduced_samples(log):
        passed = float(value) >= 0.5
        records.append(
            SampleRecord(
                test_id=test_id,
                passed=passed,
                composite_score=float(meta.get("composite_score", 1.0 if passed else 0.0)),
                category=str(meta.get("category", "uncategorized")),
                risk_level=str(meta.get("risk_level", "medium")),
                detected_failure_labels=list(meta.get("detected_failure_labels", [])),
                retrieval_scores=dict(meta.get("retrieval_scores", {})),
                errored=bool(meta.get("errored", False)),
            )
        )
    return records


def _rate(passed: int, total: int) -> float:
    return passed / total if total else 0.0


def digest(log: EvalLog) -> RunDigest:
    records = sample_records(log)
    total = len(records)
    passed = sum(1 for r in records if r.passed)

    cat_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    risk_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    label_counter: Counter[str] = Counter()
    for r in records:
        cat_pass[r.category][0] += int(r.passed)
        cat_pass[r.category][1] += 1
        risk_pass[r.risk_level][0] += int(r.passed)
        risk_pass[r.risk_level][1] += 1
        if not r.passed:
            label_counter.update(r.detected_failure_labels)

    meta = log.eval.metadata or {}
    return RunDigest(
        run_id=log.eval.run_id,
        task=log.eval.task,
        model=log.eval.model,
        system_version=str(meta.get("system_version", "unversioned")),
        dataset_version=str(meta.get("dataset_version", "")),
        created=log.eval.created or "",
        records=records,
        overall_pass_rate=_rate(passed, total),
        pass_rate_by_category={k: _rate(v[0], v[1]) for k, v in sorted(cat_pass.items())},
        pass_rate_by_risk={k: _rate(v[0], v[1]) for k, v in sorted(risk_pass.items())},
        top_failure_labels=label_counter.most_common(),
        error_count=sum(1 for r in records if r.errored),
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
