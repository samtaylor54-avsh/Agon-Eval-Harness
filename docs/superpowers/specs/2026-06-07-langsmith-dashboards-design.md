# LangSmith Dashboards (Trace Enrichment) — Design Spec (Phase 3 M10)

**Status:** Approved (design) · **Date:** 2026-06-07 · **Milestone:** Phase 3 M10
**Branch:** `phase-3-m10-langsmith-dashboards`

## Goal

Make every eval run produce a **rich, queryable trace** so LangSmith (or any OpenTelemetry backend)
can chart pass-rate over time, errors by category, and cost per run. Today the trace export emits raw
GenAI events (model/tool/score) but **none of the evaluation outcomes** that make a dashboard useful.
This milestone enriches the spans with those outcomes, then documents how to build LangSmith dashboards
on them.

The engineering core (span enrichment) is **offline-first and fully offline-testable**. The dashboard
guide + worked walkthrough use the live LangSmith account but are kept off the reproducibility path.
**No new dependencies.**

## Background / current state (verified against the code)

- `agon/observability/exporter.py::export_eval_log(log, tracer)` walks an Inspect `EvalLog` into a span
  tree: a run span (`invoke_workflow`, attrs `agon.run_id`/`agon.task`/`gen_ai.request.model`), one
  `invoke_agent` span per sample (attrs `agon.sample_id`/`gen_ai.agent.name`), and `chat`/
  `execute_tool`/`agon.score` child spans (tokens, raw score value). M9 added `redact()` to the score
  value (`_strval`) and tool-error status.
- `agon/observability/semconv.py` pins the attribute-name strings (`GEN_AI_*`, `AGON_*`).
- The `trace` CLI command (`agon/cli/app.py`) loads a stored run via `find_run` and calls
  `export_eval_log(log, tracer)` for `console | langsmith | otlp` backends. It does **not** load a
  `RunConfig`.
- The **`RunDigest`** (`agon/analysis/logs.py`, via `digest(log)`) holds the outcomes absent from
  spans. **Verified** field access:
  - Per sample (`SampleRecord`): `test_id`, `passed` (bool), `composite_score` (float), `category`
    (str), `risk_level` (str), `error_category` (str | None), `detected_failure_labels` (list[str]).
  - Run level: `overall_pass_rate` (float), `n_cases` (int), `error_count` (int),
    `error_count_by_category` (dict[str, int]), `system_version`, `dataset_version`, and `cost`
    (`total_usd`, `usage.input/output/total`).
- **Verified mapping:** `str(sample.id) == SampleRecord.test_id` (e.g. `rag_001`, `smoke_002`), so a
  sample span maps to its record by `str(sample.id)`.
- **Verified wrinkle 1:** `recommendation` is NOT a `RunDigest` field — it is computed by
  `recommend(digest, regression, pass_threshold, investigate_threshold)` in
  `agon/reporting/generator.py`. The `trace` command has no config, so recommendation must be computed
  with `RunConfig()` **default thresholds** at export time.
- **Verified wrinkle 2:** `digest(log)` needs a real `EvalLog`; the existing `tests/test_observability.py`
  passes fake `SimpleNamespace` logs. Calling `digest()` unconditionally inside `export_eval_log` would
  break those tests — so enrichment is gated behind an optional `digest` parameter.

## Decisions locked

1. **Enrichment is opt-in via an optional `digest` parameter.** `export_eval_log(log, tracer, *,
   digest=None)`. When `digest` is provided, outcome attributes are attached; when omitted, the
   function behaves exactly as today (backward compatible with the fake-NS structural tests). The
   `trace` command computes `digest(log)` and passes it. Raw event spans are always emitted regardless.
2. **Per-sample scalars + run-level headline scalars; no JSON blobs.** Every emitted attribute is a
   primitive (bool/int/float/str). Per-category error counts are flat (`agon.error_count.<category>`,
   only for categories present). Per-category *pass-rate* breakdowns are NOT emitted — they are derived
   in the dashboard by grouping sample spans on `agon.category`.
3. **`recommendation` is computed with `RunConfig()` default thresholds**, emitted as
   `agon.recommendation` alongside the raw chartable `agon.overall_pass_rate`. The default-thresholds
   caveat is documented (the authoritative gate is the run's own report, which used the run's config).
4. **Free-text string attributes are redacted** (`system_version`, `dataset_version`, `failure_labels`,
   `category`) via M9's `redact()` before being set. Scalars are not redacted.
5. **Worked example is an offline-runnable documented walkthrough**, not a live-account script in
   `examples/`. This keeps the milestone inside the 20-minute reproducibility budget (the offline
   `--backend console` path shows the enriched spans without an account).
6. **No new dependencies; LangSmith focus.** The existing `otel`/`langsmith`/`console` backends are
   unchanged. Grafana/Tempo dashboards are out of scope (the OTLP backend already exists; the guide
   targets LangSmith).

## Architecture

### Component 1 — attribute constants (`agon/observability/semconv.py`)

Add `AGON_*` name strings (no logic):

```
AGON_PASSED            = "agon.passed"
AGON_COMPOSITE_SCORE   = "agon.composite_score"
AGON_CATEGORY          = "agon.category"
AGON_RISK_LEVEL        = "agon.risk_level"
AGON_ERROR_CATEGORY    = "agon.error_category"
AGON_FAILURE_LABELS    = "agon.failure_labels"
AGON_OVERALL_PASS_RATE = "agon.overall_pass_rate"
AGON_N_CASES           = "agon.n_cases"
AGON_ERROR_COUNT       = "agon.error_count"
AGON_ERROR_COUNT_PREFIX= "agon.error_count."     # + <category>
AGON_RECOMMENDATION    = "agon.recommendation"
AGON_COST_USD          = "agon.cost.usd"
AGON_COST_INPUT_TOKENS = "agon.cost.input_tokens"
AGON_COST_OUTPUT_TOKENS= "agon.cost.output_tokens"
AGON_COST_TOTAL_TOKENS = "agon.cost.total_tokens"
AGON_SYSTEM_VERSION    = "agon.system_version"
AGON_DATASET_VERSION   = "agon.dataset_version"
```

### Component 2 — enrichment in `export_eval_log` (`agon/observability/exporter.py`)

Signature becomes `export_eval_log(log, tracer, *, digest=None)`. Two small helpers:

- `_run_outcome_attrs(d) -> dict[str, Any]`: builds the run-level scalar attributes from a `RunDigest`
  `d`, including one `agon.error_count.<cat>` per entry in `d.error_count_by_category`, the cost
  scalars, redacted `system_version`/`dataset_version`, and `agon.recommendation` computed via
  `recommend(d, None, pass_threshold=RunConfig().pass_threshold,
  investigate_threshold=RunConfig().investigate_threshold)`.
- `_sample_outcome_attrs(rec) -> dict[str, Any]`: builds per-sample scalars from a `SampleRecord`;
  omits `agon.error_category` when `rec.error_category is None`; `agon.failure_labels` is
  `redact(",".join(rec.detected_failure_labels))`; `agon.category` redacted.

When `digest` is provided: merge `_run_outcome_attrs(digest)` into the run span's `attributes`, and
build a `{rec.test_id: rec}` map so each sample span merges `_sample_outcome_attrs(map[str(sample.id)])`
(skip if no match). When `digest is None`: unchanged.

Import `redact` (already used in this file), `digest`/`recommend`/`RunConfig` lazily or at top as the
file's convention dictates.

### Component 3 — `trace` command passes the digest (`agon/cli/app.py`)

After `log = find_run(...)`, compute `d = digest(log)` and call
`export_eval_log(log, tracer, digest=d)`. (Import `digest` from `agon.analysis`.) No new flags. All
three backends benefit; `--backend console` shows the enriched spans offline.

### Component 4 — dashboard guide (`docs/langsmith-dashboards.md`)

- **Setup:** `.env` with `LANGSMITH_API_KEY` (+ optional `LANGSMITH_PROJECT`), `uv sync --extra otel`,
  `agon trace <run_id> --backend langsmith`. Note `agon doctor` confirms the key (masked).
- **Span model:** the run span (`invoke_workflow`) carries run-level scalars; sample spans
  (`invoke_agent`) carry per-sample scalars; chat/tool/score children carry the raw events.
- **Dashboard recipes** (against the attribute names): pass-rate over time (chart run-span
  `agon.overall_pass_rate`); errors by category (`agon.error_count.*`); cost per run (`agon.cost.usd`);
  group/filter sample spans by `agon.category` / `agon.risk_level` / `agon.error_category` /
  `agon.passed` for breakdowns; filter by `agon.recommendation`.
- **Caveat:** `agon.recommendation` uses default thresholds at export time; the authoritative gate is
  the run's report.
- **Worked walkthrough:** run an offline eval -> `agon trace <id> --backend console` (see enriched
  spans, no account) -> swap `--backend langsmith` -> build the recipes above.
- **README + CLAUDE.md pointer** to the guide.

## Data flow

```
agon trace <run_id> --backend langsmith
  -> find_run -> log
  -> d = digest(log)
  -> export_eval_log(log, tracer, digest=d)
       run span     += _run_outcome_attrs(d)        (redacted strings; default-threshold recommendation)
       sample spans += _sample_outcome_attrs(rec)   (matched by str(sample.id) == rec.test_id)
       chat/tool/score children unchanged
  -> spans posted to the backend
```

## Error handling

- `digest=None` -> no enrichment, no error (backward compatible).
- A sample span with no matching record -> keep the raw span, skip outcome attrs (no crash).
- `agon.error_category` omitted when the sample did not error.
- Redaction failures impossible (redact is str-in/str-out and None-safe at call sites).

## Testing strategy (offline, in-memory tracer)

- **Enrichment, run level:** run a tiny real offline eval (mini fixture) -> real `EvalLog` + `digest`;
  `export_eval_log(log, tracer, digest=d)`; assert the run span carries `agon.overall_pass_rate`,
  `agon.n_cases`, `agon.error_count`, `agon.cost.usd`, `agon.cost.total_tokens`, `agon.recommendation`.
- **Enrichment, sample level:** assert each `invoke_agent` span carries `agon.passed`,
  `agon.composite_score`, `agon.category`, `agon.risk_level`, matched to the right `test_id`.
- **Backward compat:** `export_eval_log(fake_ns_log, tracer)` (no digest) still emits the existing
  structural spans — the current `tests/test_observability.py` cases stay green unchanged.
- **Redaction:** plant an `sk-ant-...` token in the run's `--system-version`; assert the run span's
  `agon.system_version` is masked.
- **Error taxonomy:** a run with an errored sample emits `agon.error_count.<category>` on the run span
  and `agon.error_category` on that sample span. (Reuse an existing taxonomy-producing fixture/path.)
- **CLI:** `agon trace <id> --backend console` exits 0 and prints the enriched spans (smoke).

## Out of scope (YAGNI)

Production trace-harvesting loop (`evals/production/`), Grafana/Tempo-specific dashboards, automated
monitor/alert provisioning, a live-account example script, any new dependency, per-category pass-rate
attributes (derived in-dashboard).

## Deliverables

- `agon/observability/semconv.py` (new attribute constants).
- `agon/observability/exporter.py` (`digest=` param + the two outcome-attr helpers).
- `agon/cli/app.py` (`trace` computes + passes the digest).
- `docs/langsmith-dashboards.md` + README/CLAUDE pointer.
- `docs/decisions/ADR-0011-langsmith-dashboards.md`.
- Offline tests above; `ruff` clean; reproducibility budget unchanged.

## Known constraints / gotchas

1. **ASCII console output** — the `trace` command's `typer.echo` strings stay ASCII; attribute *values*
   may be UTF-8 (they ride in spans, not the cp1252 console), but redacted strings are ASCII anyway.
2. **Targeted `git add` only** — pre-existing `*.png` deletions and untracked `docs/*.docx`,
   `reports2/`, `HANDOFF.md`, `Training_Plan.txt` must never be staged.
3. **OTel attribute typing** — only primitives/arrays; every emitted value is a scalar (no dicts).
4. **`recommendation` at export time uses default thresholds** — documented; not the authoritative gate.
5. **`digest(log)` requires a real `EvalLog`** — never call it on the fake-NS test logs; that is why
   enrichment is gated behind the `digest=` parameter.
