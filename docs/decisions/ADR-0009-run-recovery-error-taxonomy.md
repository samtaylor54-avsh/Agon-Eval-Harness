# ADR-0009: Run Recovery & Error Taxonomy

**Status:** Accepted · **Date:** 2026-06-06 · **Milestone:** Phase 3 M8

## Context

A partially-failed run had no recovery path (only a full re-run) and every failure looked the
same in reports (one boolean, one count). Pre-scoring errors (`timeout`, `network`, and
`sample`-class failures that abort before the scorer runs) were in fact invisible: a sample that
errors before scoring produces no scorer score and so was dropped from the digest entirely
(`error_count` read 0).

## Decision

**1. Resume is harness-native, not Inspect `eval_retry`.** `agon resume` reads the prior log,
selects incomplete samples, reconstructs their `AgonCase`s from `metadata[METADATA_CASE_KEY]`,
re-runs only those, and merges the new records with the prior run's passing records into one
`RunDigest` rendered through the existing renderers. A case that legitimately scored `fail` is a
result, not an incomplete sample, and is not re-run. Merged-report cost reflects the re-run only.

**2. Five error categories, classified best-effort.** `timeout`/`resource` come from the
structured `sample.limit.type`; `scorer` from caught judge errors in scorer metadata;
`network`/`sample` from pattern-matching `sample.error` text. Inspect persists only the error
*string* (not the exception class), so network-vs-sample is best-effort; unmatched -> `sample`.
Pre-scoring errors are promoted to visible records (fixing the invisibility bug above).

**3. Per-case timeout is enforced in the SUT solver.** `AgonCase.sample_time_limit` overrides
the run-level default; both are applied per sample via `inspect_ai.util.time_limit`, not via
`eval()`'s global `time_limit` (so a case may request more time than the default). A breach
surfaces as `sample.limit(type="time")` and is classified `timeout`. Because Inspect catches the
limit and still scores the sample, the digest re-tags such scored-but-limited samples as errored.

## Alternatives considered

- **Inspect `eval_retry`.** Rejected: `eval_retry` reconstructs a task by registry name, but our
  `agon_task` is an anonymous in-process `Task` (no `task_registry_name`/`task_file`), so it raises
  `Task '<name>' not found` (verified empirically).
- **Register a serializable `@task` to enable `eval_retry`.** Rejected: it would break the
  `callable_fn` programmatic path (in-process callables used by quickstarts/tests do not serialize
  into a log) and force a disruptive refactor for no gain over the harness-native approach.

## Consequences

- Errors are now first-class in every report (`error_count_by_category` in md/json/junit).
- `resume` works fully offline (mockllm / callable adapter), preserving the reproducibility bar.
- `resume` loads `--plugin` scorers (like `run`) so a resumed custom-scorer run still scores.

## Known limitations

- Per-case timeouts do not apply to the native ReAct agent path (`agent_task`), which builds its
  own solver via `react_sut` and never receives `default_time_limit`. Acceptable for now; a future
  milestone can extend it if needed.
- With `epochs > 1`, if a single epoch of a case hits a per-case `time_limit` while the flake
  reducer still reduces the case to a pass, the digest currently re-tags that sample as a
  `timeout` error (it surfaces any per-epoch limit). Per-case timeouts are intended for the
  common `epochs = 1` path; reconciling per-epoch limits with the reduced outcome is left to a
  future milestone.
- `agon resume` cannot *loosen* a per-case `sample_time_limit`: the case's own value wins over
  the run-level `--sample-time-limit` (by design, "per-case overrides the default"), so a case
  that timed out under its own tight limit will time out again on resume unless the dataset's
  per-case value is changed. The run-level default can still be loosened for cases that have none.
