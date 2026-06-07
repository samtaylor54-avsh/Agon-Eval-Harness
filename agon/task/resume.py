"""Harness-native run recovery (Phase 3 M8).

Inspect's ``eval_retry`` cannot reconstruct our anonymous in-process ``Task`` (it looks the
task up in the registry by name and fails), so resume is implemented here: read a prior log,
select the incomplete samples, rebuild their ``AgonCase``s from ``metadata[METADATA_CASE_KEY]``,
re-run just those, and merge with the prior run's already-passing records.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai.log import EvalLog, EvalSample

from agon.analysis.logs import (
    AGON_SCORER,
    RunDigest,
    SampleRecord,
    build_digest,
    digest,
    find_run,
    latest_run,
)
from agon.analysis.regression import compare_digests
from agon.dataset import METADATA_CASE_KEY
from agon.reporting.generator import recommend, render_json, render_junit_xml, render_markdown
from agon.schemas import AgonCase, AgonDataset, RunConfig
from agon.sut.solvers import SUTCallable
from agon.task.builder import run_eval


def select_incomplete(log: EvalLog) -> list[EvalSample]:
    """Samples that did not finish with a clean score: errored, hit a limit, unscored, or
    scored with a scorer error.
    """
    out: list[EvalSample] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get(AGON_SCORER)
        scorer_errored = bool((score.metadata or {}).get("errored")) if score is not None else False
        if sample.error is not None or sample.limit is not None or score is None or scorer_errored:
            out.append(sample)
    return out


def cases_from_log(log: EvalLog, samples: list[EvalSample]) -> AgonDataset:
    """Rebuild an AgonDataset from the cases embedded in the given samples' metadata."""
    cases: list[AgonCase] = []
    seen: set[str] = set()
    for sample in samples:
        dump = (sample.metadata or {}).get(METADATA_CASE_KEY)
        if dump is None:
            continue
        case = AgonCase.model_validate(dump)
        if case.test_id in seen:
            continue
        seen.add(case.test_id)
        cases.append(case)
    if not cases:
        raise ValueError(
            f"cases_from_log: no AgonCase metadata found in {len(samples)} sample(s); "
            f"the original run must have used case_to_sample (metadata key {METADATA_CASE_KEY!r})."
        )
    meta = log.eval.metadata or {}
    version = str(meta.get("dataset_version", "")) or "resume"
    return AgonDataset(name=f"{log.eval.task}__resume", dataset_version=version, test_cases=cases)


def merge_digests(prior: RunDigest, rerun: RunDigest) -> RunDigest:
    """Merge a prior run's records with a re-run, preferring the re-run per test_id.

    Aggregates are recomputed from the merged record set. Metadata sourcing:
    - run_id, created: from the rerun (the resume operation is the canonical identity)
    - task, model, system_version, dataset_version: from the prior run (config unchanged)
    - cost: rerun only -- reflects the work resume performed; callers needing a cumulative
      total should sum prior.cost + rerun.cost themselves.
    """
    by_id: dict[str, SampleRecord] = {r.test_id: r for r in prior.records}
    for r in rerun.records:
        by_id[r.test_id] = r
    return build_digest(
        list(by_id.values()),
        run_id=rerun.run_id,
        task=prior.task,
        model=prior.model,
        system_version=prior.system_version,
        dataset_version=prior.dataset_version,
        created=rerun.created,
        cost=rerun.cost,
    )


def resume_run(
    cfg: RunConfig,
    run_id: str | None,
    *,
    callable_fn: SUTCallable | None = None,
    display: str = "none",
) -> dict[str, object]:
    """Re-run a prior run's incomplete cases and write a merged report.

    ``run_id=None`` resumes the most recent run in ``cfg.log_dir``. Returns a dict with
    ``resumed`` (count of cases re-run), the merged ``digest``, the ``regression`` vs the
    prior run, the ``recommendation``, the rendered ``artifacts``, and ``written`` paths.
    """
    prior = find_run(cfg.log_dir, run_id) if run_id else latest_run(cfg.log_dir)
    prior_digest = digest(prior)

    incomplete = select_incomplete(prior)
    if not incomplete:
        rec = recommend(
            prior_digest,
            None,
            pass_threshold=cfg.pass_threshold,
            investigate_threshold=cfg.investigate_threshold,
        )
        # Nothing to recover: return the prior digest unchanged and write no new report files
        # (re-resuming a clean run should not churn the existing report on disk).
        return {
            "resumed": 0,
            "digest": prior_digest,
            "regression": None,
            "recommendation": rec,
            "artifacts": {},
            "written": {},
        }

    sub = cases_from_log(prior, incomplete)
    new_log = run_eval(sub, cfg, callable_fn=callable_fn, display=display)
    rerun_digest = digest(new_log)
    merged = merge_digests(prior_digest, rerun_digest)

    regression = compare_digests(merged, prior_digest)
    recommendation = recommend(
        merged,
        regression,
        pass_threshold=cfg.pass_threshold,
        investigate_threshold=cfg.investigate_threshold,
    )
    artifacts = {
        "report.md": render_markdown(merged, regression, recommendation),
        "report.json": render_json(merged, regression, recommendation),
        "report.junit.xml": render_junit_xml(merged),
    }
    written: dict[str, str] = {}
    if cfg.report_dir:
        out = Path(cfg.report_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            path = out / f"{merged.run_id}.{name}"
            path.write_text(content, encoding="utf-8")
            written[name] = str(path)
    return {
        "resumed": len(incomplete),
        "digest": merged,
        "regression": regression,
        "recommendation": recommendation,
        "artifacts": artifacts,
        "written": written,
    }
