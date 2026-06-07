# ADR-0011: LangSmith Dashboards (Trace Enrichment)

**Status:** Accepted · **Date:** 2026-06-07 · **Milestone:** Phase 3 M10

## Context

Agon exports stored runs as OpenTelemetry GenAI spans (M3), but those spans carried only raw
model/tool/score events — none of the evaluation outcomes (pass/fail, scores, category, risk, the M8
error taxonomy, cost) that make a dashboard useful. Building a LangSmith dashboard required reverse-
engineering outcomes from raw events, which is not possible for most of them.

## Decision

Enrich the span tree with evaluation outcomes, sourced from the `RunDigest`.

1. **Opt-in via an optional `digest=` parameter** on `export_eval_log`. When provided, outcome
   attributes are attached; when omitted, behavior is unchanged (backward compatible with the
   fake-`SimpleNamespace` structural tests). The `trace` command computes `digest(log)` and passes it.
2. **Per-sample scalars + run-level headline scalars; no JSON blobs.** Sample spans carry
   `agon.passed`/`composite_score`/`category`/`risk_level`/`error_category`/`failure_labels`; the run
   span carries `overall_pass_rate`/`n_cases`/`error_count` + flat `error_count.<category>`/cost
   USD+tokens/`system_version`/`dataset_version`/`recommendation`. Per-category pass-rate breakdowns are
   derived in the dashboard by grouping sample spans, not duplicated on the run span. Every attribute
   is a scalar (or a string array for `failure_labels`) so it is chartable/filterable.
3. **`recommendation` is computed with default thresholds at export time** (the `trace` command has no
   config). The authoritative gate remains the run's report.
4. **Free-text string attributes are redacted** (`system_version`, `dataset_version`, `failure_labels`,
   `category`, `risk_level`) via M9's `redact()`.

## Consequences

- LangSmith (or any OTLP backend) can chart pass-rate over time, errors by category, and cost per run
  directly from trace attributes; the offline `console` backend shows the same enriched spans with no
  account.
- A documented dashboard guide (`docs/langsmith-dashboards.md`) provides concrete recipes.

## Known limitations

- **`recommendation` uses default thresholds** at export time; not the authoritative gate.
- **The raw Inspect `.eval` log is still not redacted** (ADR-0010) — unchanged here.
- **No production trace-harvesting loop** and **no automated monitor/alert provisioning** — out of
  scope; the guide is manual dashboard setup.
