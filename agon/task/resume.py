"""Harness-native run recovery (Phase 3 M8).

Inspect's ``eval_retry`` cannot reconstruct our anonymous in-process ``Task`` (it looks the
task up in the registry by name and fails), so resume is implemented here: read a prior log,
select the incomplete samples, rebuild their ``AgonCase``s from ``metadata[METADATA_CASE_KEY]``,
re-run just those, and merge with the prior run's already-passing records.
"""

from __future__ import annotations

from inspect_ai.log import EvalLog, EvalSample

from agon.analysis.logs import AGON_SCORER, RunDigest, SampleRecord, build_digest
from agon.dataset import METADATA_CASE_KEY
from agon.schemas import AgonCase, AgonDataset


def select_incomplete(log: EvalLog) -> list[EvalSample]:
    """Samples that did not finish with a clean score: errored, hit a limit, unscored, or
    scored with a scorer error.
    """
    out: list[EvalSample] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get(AGON_SCORER)
        scorer_errored = bool(score.metadata.get("errored")) if score is not None else False
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
    meta = log.eval.metadata or {}
    version = str(meta.get("dataset_version", "")) or "resume"
    return AgonDataset(name=f"{log.eval.task}__resume", dataset_version=version, test_cases=cases)


def merge_digests(prior: RunDigest, rerun: RunDigest) -> RunDigest:
    """Merge a prior run's records with a re-run, preferring the re-run per test_id.

    Aggregates are recomputed from the merged record set. Cost reflects the re-run only
    (the work resume actually performed).
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
