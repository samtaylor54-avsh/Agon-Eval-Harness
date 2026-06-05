# ADR-0003 — Export observability from the EvalLog, not via live hooks

- **Status:** Accepted
- **Date:** 2026-06-05
- **Deciders:** Samuel R. Taylor
- **Context:** Phase 2 M3 (observability)

## Context

M3 emits OpenTelemetry **GenAI** spans for eval runs so they're inspectable in LangSmith / Grafana
Tempo. Inspect AI emits no OpenTelemetry of its own, so we bridge it. Two designs were considered:

1. **Live hooks** — register `inspect_ai.hooks` callbacks (`on_before_model_generate`,
   `on_sample_event`, …) and translate events into spans *during* the run.
2. **Post-hoc log export** — walk the immutable `EvalLog`'s `model` / `tool` / `score` events
   *after* the run and emit the span tree.

## Decision

**Export post-hoc from the EvalLog.** The Phase 2 scope sketched a hooks bridge; on inspection the
log-export approach is materially better here:

- **Deterministic + testable:** a pure `EvalLog → spans` function is asserted with an in-memory
  span exporter, no live-async context juggling. (Hooks fire inside Inspect's concurrent run loop,
  where managing parent/child span context across callbacks is fiddly and hard to test.)
- **Complete + accurate:** the log already carries every model event (model, token usage) and tool
  event with **both** `timestamp` and `completed`, so spans get real durations and a correct tree.
- **Right fit for an eval harness:** you run an eval, then export its trace — there's no need for
  live streaming. It also means *any* stored run (including historical ones) can be exported.

The span tree: `eval <task>` (invoke_workflow) → `invoke_agent <sample>` → `chat <model>` /
`execute_tool <name>` / `agon.score <scorer>`.

## Consequences

- **Positive:** robust, testable, works on any stored log; offline `console` backend needs no
  account; LangSmith (`/otel`) and Grafana Tempo (OTLP collector) are config-only.
- **Negative:** not *live* tracing — spans appear after the run completes. Acceptable for an eval
  harness; a hooks-based live path can be added later if streaming is ever needed.
- **Experimental attributes:** the `gen_ai.*` conventions are still OTel "Development". We pin the
  attribute name strings ourselves (`agon/observability/semconv.py`) and document the
  `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` opt-in. Tool/grader spans carry
  `gen_ai.tool.name` / `agon.scorer`, keeping the trace legible.
- **Opt-in only:** observability requires the `[otel]` extra and an explicit `agon trace`; it is
  never on the offline default eval path, and CI's offline gate runs with it off.
