# LangSmith dashboards from Agon traces

Agon exports every stored run as an OpenTelemetry GenAI span tree, enriched with the run's
**evaluation outcomes** so you can build dashboards directly on the trace attributes. This works
against LangSmith's OTLP endpoint (or any OTLP backend); the offline `console` backend prints the same
enriched spans with no account.

## 1. Set the key (never commit it)

```bash
# .env at the repo root (gitignored)
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=agon-eval        # optional; groups runs in the LangSmith UI
```

Agon loads `.env` at startup. Confirm it is picked up (masked, never printed raw):

```bash
uv run agon doctor          # shows  LANGSMITH_API_KEY: lsv2_...xxxx
```

Install the exporter extra: `uv sync --extra otel`.

## 2. See the enriched spans offline, then export

```bash
uv run agon run examples/datasets/rag_smoke.yaml --display none   # produces a run_id
uv run agon trace <run_id> --backend console                     # enriched spans to stdout (no account)
uv run agon trace <run_id> --backend langsmith                   # same spans -> your LangSmith project
```

## 3. The span model

| Span (`gen_ai.operation.name`) | Carries |
|---|---|
| `eval <task>` (`invoke_workflow`) | `agon.overall_pass_rate`, `agon.n_cases`, `agon.error_count`, `agon.error_count.<category>`, `agon.recommendation`, `agon.cost.usd`, `agon.cost.{input,output,total}_tokens`, `agon.system_version`, `agon.dataset_version` |
| `invoke_agent <sample>` | `agon.passed`, `agon.composite_score`, `agon.category`, `agon.risk_level`, `agon.error_category` (if errored), `agon.failure_labels` |
| `chat` / `execute_tool` / `agon.score` | raw model/tool/score events (tokens, scorer, value) |

All run-level and per-sample values are scalars (chartable); `agon.failure_labels` is a string array;
known secret values are redacted.

## 4. Dashboard recipes (LangSmith)

- **Pass-rate over time:** chart run spans, metric = `agon.overall_pass_rate`, x = time. Group by
  `agon.system_version` to compare builds.
- **Errors by category:** chart run spans, series = the `agon.error_count.*` attributes
  (`timeout`/`resource`/`network`/`scorer`/`sample`).
- **Cost per run:** chart run spans, metric = `agon.cost.usd` (and `agon.cost.total_tokens`).
- **Pass-rate by category / risk:** filter to `invoke_agent` spans, group by `agon.category` (or
  `agon.risk_level`), aggregate `agon.passed`. (Per-category rates are derived here rather than
  duplicated on the run span.)
- **Failure triage:** filter `invoke_agent` spans where `agon.passed = false`, group by
  `agon.error_category` / `agon.failure_labels`.
- **Release view:** filter run spans by `agon.recommendation = FAIL`.

> **Caveat:** `agon.recommendation` is computed at export time with default thresholds. The
> authoritative release gate is the run's own report (which used the run's configured thresholds).

## 5. Other backends

`--backend otlp --endpoint <url>` sends the same enriched spans to any OTLP/HTTP collector (e.g.
Grafana Tempo); build equivalent panels there.
