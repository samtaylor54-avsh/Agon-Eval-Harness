# Observability — exporting eval runs as OpenTelemetry GenAI traces

Agon exports any stored eval run as an OpenTelemetry **GenAI** span tree (ADR-0003). Inspect AI
doesn't emit OTel itself, so this reads the immutable `.eval` log and emits spans post-hoc.

```
eval <task>                 invoke_workflow   (agon.run_id, agon.task)
  └─ invoke_agent <sample>                    (one per sample)
       ├─ chat <model>      chat              (gen_ai.request.model, gen_ai.usage.*_tokens)
       ├─ execute_tool <t>  execute_tool      (gen_ai.tool.name; ERROR status on tool errors)
       └─ agon.score <s>                       (agon.scorer, agon.score.value)
```

Install the extra: `uv sync --extra otel`.

## 1. Offline (console) — no account

```bash
uv run agon run examples/datasets/rag_smoke.yaml --log-dir logs --display none
uv run agon trace <run_id> --backend console      # prints gen_ai.* spans to stdout
```

## 2. LangSmith (OTLP, no LangChain SDK)

LangSmith ingests OTLP traces directly at its `/otel` endpoint.

```bash
export LANGSMITH_API_KEY=ls_...
# optional: export LANGSMITH_PROJECT=agon-evals
#           export OTEL_EXPORTER_OTLP_ENDPOINT=https://eu.api.smith.langchain.com/otel
uv run agon trace <run_id> --backend langsmith
```

The exporter posts to `<endpoint>/v1/traces` with an `x-api-key` header. Because the spans follow
the `gen_ai.*` conventions, LangSmith maps them into its native fields. Set
`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` if your collector gates experimental
attributes.

## 3. Grafana + Tempo (self-hosted, OTLP collector)

Same OTLP spans, no external account. Stand up Tempo + Grafana, then point `agon trace` at the
collector's OTLP/HTTP traces endpoint:

```bash
docker compose -f docs/observability/docker-compose.tempo.yml up -d
uv run agon trace <run_id> --backend otlp --endpoint http://localhost:4318/v1/traces
# open Grafana at http://localhost:3000 (Tempo datasource), search service "agon-eval-harness"
```

See `docs/observability/docker-compose.tempo.yml` for a minimal Tempo+Grafana stack.

> Observability is **opt-in** and never on the offline default eval path. CI's offline gate runs
> with it off.
