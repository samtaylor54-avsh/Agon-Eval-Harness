# Run Recovery & Error Taxonomy — Design Spec (Phase 3 M8)

**Status:** Approved (design) · **Date:** 2026-06-06 · **Milestone:** Phase 3 M8
**Branch:** `phase-3-m8-run-recovery-error-taxonomy`

## Goal

Make a partially-failed run **recoverable** and make its failures **legible**. Today a run that hits
transient model errors, timeouts, or judge hiccups produces a log where every failure looks the same
(one boolean, one count) and the only way to "retry" is to re-run the whole dataset from scratch.
This milestone adds three interlocking capabilities, all **offline-first with zero new dependencies**:

1. **`agon resume`** — re-run only the failed/incomplete cases of a prior run and merge the result
   into a fresh, complete report.
2. **A structured per-sample error taxonomy** — classify each failure as `timeout`, `resource`,
   `network`, `scorer`, or `sample`, and surface the breakdown in every report format.
3. **Per-case timeout overrides** — let an individual dataset case declare its own wall-clock budget,
   enforced per sample (Inspect's `time_limit` is otherwise global to the whole eval).

The three reinforce each other: the taxonomy tells you *what* failed and whether resuming is worth it;
resume reconstructs and re-runs exactly those cases; per-case timeouts surface as a structured
`timeout` signal the taxonomy already understands.

## Background / current state

- **No resume exists.** A run is `agon run` → Inspect `eval(...)` → one `EvalLog` written to
  `log_dir` as `<run_id>.eval`. `agon/analysis/logs.py::find_run(log_dir, run_id)` locates a prior log.
  There is no command to re-run a subset.
- **Inspect's native `eval_retry` does NOT work with our architecture** (verified empirically — it
  raises `FileNotFoundError: Task '<name>' not found`). `agon/task/builder.py::agon_task` returns an
  **anonymous in-process `Task`** (`name=dataset.name`, no `task_registry_name`, no `task_file`,
  `task_args={}`). `eval_retry` reconstructs a task by looking it up in the registry by name, which our
  task is not in. Making it work would require registering `agon_task` as a serializable `@task` and
  would break the `callable_fn` programmatic path (quickstarts/tests inject behavior via in-process
  callables that cannot serialize into a log). **Rejected.** See "Decisions locked" #1.
- **Errors are a boolean + a count.** `agon/analysis/logs.py::SampleRecord.errored: bool` and
  `RunDigest.error_count: int`. The only typed error in the harness is `JudgeParseError`
  (`agon/scoring/judge.py`), caught in `agon/scoring/inspect_scorer.py` and turned into a synthetic
  score with `metadata["errored"]=True` and failure label `judge_error`. No categorization anywhere;
  reports show only the aggregate count (markdown `| Errors | {{ d.error_count }} |`).
- **Inspect already records structured failure signals we are throwing away.** On each
  `EvalSample`: `sample.error` (an `EvalError` with `message` + `traceback`, free text — **no exception
  class is persisted**), `sample.limit` (an `EvalSampleLimit` with
  `type ∈ {context,time,working,message,token,cost,operator,custom}` + the numeric `limit`), and
  `sample.error_retries` (history). `sample.limit` is the reliable, structured signal for
  timeouts/resource exhaustion.
- **Per-sample timeout is global-only.** `ResilienceConfig.sample_time_limit` (CLI
  `--sample-time-limit`) maps to Inspect's eval-level `time_limit` kwarg in
  `resilience_eval_kwargs()`, applied uniformly to every sample. `AgonCase` already carries a
  per-case `repetitions` override and an arbitrary `metadata` dict, establishing the per-case-override
  pattern, but there is no per-case timeout.
- **The full case round-trips through the log** (verified): `agon/dataset/loader.py::case_to_sample`
  stores `case.model_dump(mode="json")` under `metadata[METADATA_CASE_KEY]`, and
  `AgonCase.model_validate(...)` reconstructs it exactly. **Resume can rebuild failed cases from the
  log alone — it does not need the original dataset file.**
- **Report renderers take a `RunDigest`, not an `EvalLog`** (verified): `render_markdown(d, regression,
  recommendation)`, `render_json(...)`, `render_junit_xml(d)`. So a *merged* digest can be rendered
  directly through the existing renderers — the merge happens at the record layer we own.

## Decisions locked

1. **Resume is harness-native, not `eval_retry`.** `agon resume` reads the prior log, selects the
   failed/incomplete samples, **reconstructs their `AgonCase`s from `metadata[METADATA_CASE_KEY]`**,
   runs a fresh `eval` over just those cases, then **merges** the new per-case records with the prior
   run's already-passing records into one `RunDigest` and renders a complete report. Rationale:
   preserves offline-first reproducibility and the `callable_fn` programmatic API; reuses `digest()`
   and the existing renderers; avoids a disruptive `@task` registry refactor. (The alternative,
   registering a serializable `@task` to use `eval_retry`, was rejected — see Background.)
2. **"Incomplete" is defined explicitly.** A prior sample is re-run iff: it has a `sample.error`, OR it
   has a `sample.limit` (timed out / hit a resource cap), OR its scorer record is `errored=True`, OR it
   is absent from the prior results entirely (run aborted before reaching it). Samples that completed
   with a real pass/fail score are **not** re-run — a legitimate `fail` is a result, not a failure to
   recover.
3. **Resume inherits the prior run's model/adapter; resilience knobs are overridable.** The new run
   uses the same model string from the prior log. The CLI exposes the same resilience flags as
   `agon run` (`--retry-on-error`, `--sample-time-limit`, `--max-retries`, `--request-timeout`,
   `--attempt-timeout`, `--fail-on-error`) so you can resume with more lenient settings. The original
   run is passed as the **baseline** to the merged report, so the regression view shows what resume
   recovered.
4. **Five error categories, classified best-effort.** `ErrorCategory ∈ {timeout, resource, network,
   scorer, sample}`. Precedence and source of truth:
   - `sample.limit.type` → `time`/`working` = **timeout**; `token`/`cost`/`context`/`message` =
     **resource**. (Structured, reliable.)
   - scorer record `errored=True` (e.g. `judge_error`) = **scorer**.
   - `sample.error` present → pattern-match `message`+`traceback`: connection/timeout/rate-limit/
     `429`/`5xx`/`APIError`/`APIConnection` markers = **network**; otherwise = **sample**.
   Because Inspect persists only the error *string* (not the exception class), `network` vs `sample` is
   explicitly **best-effort**; anything unmatched falls to `sample`. This caveat is recorded in the ADR.
5. **Per-case timeout is enforced in the solver, and overrides the global default.** Add
   `AgonCase.sample_time_limit: int | None` (ge=1). Enforcement moves out of the eval-level
   `time_limit` kwarg and into the solver via `inspect_ai.util.time_limit(...)`, applied per sample as
   `effective = case.sample_time_limit or config.resilience.sample_time_limit`. This gives a single
   enforcement path and true override semantics (a case may request *more* time than the global
   default, which an eval-level cap would otherwise prevent). A breach raises Inspect's
   `LimitExceededError`, surfaces as `sample.limit` type `time`, and is classified `timeout` by #4.

## Architecture

```
agon resume <run_id>|--latest
  └─ find_run(log_dir, run_id)                         # existing (agon/analysis/logs.py)
  └─ select_incomplete(prior_log)        ─┐ new agon/task/resume.py
  └─ cases_from_log(prior_log, samples)  ─┤   (rebuild AgonCase[] from METADATA_CASE_KEY)
  └─ run_eval(sub_dataset, cfg)           │  existing builder (fresh EvalLog, new run_id)
  └─ merge_digests(prior_log, new_log)   ─┘   (prior passing records ∪ new records)
  └─ render_markdown/json/junit(merged_digest, ...)   # existing renderers (take a RunDigest),
                                                      # NOT generate_reports (which takes an EvalLog)
```

```
error taxonomy
  EvalSample ──> classify_sample(sample, record) ──> ErrorCategory|None   # new agon/analysis/errors.py
  digest()/sample_records()  set SampleRecord.error_category
  digest()                   aggregate RunDigest.error_count_by_category
  renderers                  surface the breakdown (md table / json dict / junit message)
```

```
per-case timeout
  AgonCase.sample_time_limit ──> Sample.metadata ──> solver wraps SUT call in time_limit(effective)
  breach ──> sample.limit(type=time) ──> classify_sample ──> "timeout"
```

## Components & files

- **`agon/analysis/errors.py` (new).** `ErrorCategory` enum + `classify_sample(sample, record)
  -> ErrorCategory | None`. Pure function, no I/O — boundary-testable against constructed
  `EvalSample`/record inputs.
- **`agon/analysis/logs.py` (edit).** `SampleRecord` gains `error_category: str | None = None`.
  `RunDigest` gains `error_count_by_category: dict[str, int] = Field(default_factory=dict)` (default
  keeps existing `make_digest`-style test helpers working — gotcha #6). `sample_records()` sets the
  per-record category; `digest()` aggregates the dict.
- **`agon/task/resume.py` (new).** `select_incomplete(log) -> list[EvalSample]`,
  `cases_from_log(log, samples) -> AgonDataset`, `merge_digests(prior, new) -> RunDigest`, and a
  `resume_run(log_dir, run_id, cfg_overrides, display) -> dict` orchestrator returning the same shape
  as `generate_reports`.
- **`agon/sut/solvers.py` (edit).** The `callable`/SUT solver reads the effective per-sample time limit
  from sample metadata and wraps the SUT invocation in `inspect_ai.util.time_limit(...)`.
- **`agon/task/builder.py` (edit).** Stop sending `time_limit` to `eval()` in
  `resilience_eval_kwargs()`; the global default is now applied per-sample in the solver (so per-case
  overrides win). Pass the global `sample_time_limit` through to the solver.
- **`agon/schemas/models.py` (edit).** `AgonCase.sample_time_limit: int | None = Field(default=None,
  ge=1)`.
- **`agon/cli/app.py` (edit).** New `resume` command mirroring `run`'s resilience flags; reuse
  `_apply_resilience_flags`. Keep all console output ASCII (gotcha #1).
- **`agon/reporting/` (edit).** `render_markdown` adds an error-by-category breakdown when
  `error_count > 0`; `render_json` adds `error_count_by_category`; `render_junit_xml` includes the
  category in the `<error message=...>`.
- **`docs/decisions/ADR-0009-run-recovery-error-taxonomy.md` (new).** Records the harness-native-resume
  decision (and why `eval_retry` was rejected), the five categories + best-effort caveat, and the
  per-case-timeout enforcement model.

## Testing (TDD, offline / mockllm)

- **Classifier boundary tests** (`tests/test_errors.py`): construct samples/records exercising each
  branch — `limit.type=time`→`timeout`, `=token`→`resource`, scorer `errored`→`scorer`,
  connection/`429` message→`network`, generic message→`sample`, clean sample→`None`. Assert against the
  enum directly.
- **Per-case timeout** (`tests/test_per_case_timeout.py`): a case with a tight `sample_time_limit` + a
  deliberately slow mock SUT → sample times out, record `error_category == "timeout"`; a case with no
  override falls back to the global; a generous per-case override outlives the global default.
- **Resume** (`tests/test_resume.py`): run a dataset containing one permanently-failing case (existing
  `fault_injection` policies), confirm the digest shows it failed, then `resume` with a policy/flags
  that succeed → merged digest shows the case recovered, passing cases are carried over (not re-run),
  and the new run_id differs from the original. Cover `--latest` selection and the "nothing to resume"
  case (clean prior run → resume is a no-op with a clear message).
- **Reporting** (extend `tests/test_reporting*.py`): `error_count_by_category` present in json; the
  markdown breakdown renders only when there are errors; junit carries the category. ASCII-only.

## Verification (manual, offline)

```bash
uv run ruff check agon tests && uv run pytest -q     # expect green, new tests passing
uv run agon run examples/datasets/rag_smoke.yaml --display none   # baseline run still works
# induce + recover a failure end to end (exact fixture finalized in the plan):
uv run agon resume <run_id>                          # merged report shows recovered counts
```

## Out of scope (YAGNI)

- Registering `agon_task` as a serializable `@task` / using Inspect `eval_retry`.
- Per-category fail thresholds (e.g. "fail if `network` rate > 5%"). The taxonomy surfaces the data;
  gating on it can be a later milestone if a real need appears.
- Resuming across a changed dataset/config (resume reconstructs cases from the prior log, by design).
- Re-running cases that legitimately scored `fail` (a fail is a result, not an incomplete sample).
