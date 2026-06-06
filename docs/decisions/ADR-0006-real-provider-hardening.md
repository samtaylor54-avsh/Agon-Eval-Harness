# ADR-0006: Real-provider hardening via Inspect's knobs + an advisory cost layer

**Status:** Accepted · **Date:** 2026-06-05 · **Milestone:** Phase 3 M5

## Context

`agon` is offline-first (no API key, no model downloads, <20-min clone-and-run). To be credible
for real-world use it must survive real providers (transient errors, rate limits, runaway runs)
and report what a run cost. A survey found Inspect AI already provides retry/backoff/timeout/
concurrency as first-class knobs; `agon` wired only two of them. Token usage was modeled but never
populated or reported, and there was no price table.

## Decision

1. **Resilience = expose, not reimplement.** `RunConfig.resilience` carries `max_retries`,
   `request_timeout`, `attempt_timeout`, `retry_on_error`, `sample_time_limit`, and `fail_on_error`
   (bool or error-rate threshold). These map directly to `inspect_ai.eval()` kwargs/params; Inspect
   and LiteLLM execute the retry/backoff. We do not add a hand-rolled retry engine (honors ADR-0001).
   The bool `fail_fast` is replaced by `resilience.fail_on_error`.
2. **Bounded default `max_retries = 5`** (Inspect's default is unlimited) -- a hardened run should
   not hang indefinitely on a long rate-limit. Fully overridable.
3. **Cost is an in-repo, dated, advisory estimate.** `agon/cost` prices the token usage Inspect
   measures (`EvalLog.stats.model_usage`) via a `DEFAULT_PRICES` table stamped `PRICES_AS_OF`.
   Prices are a point-in-time snapshot, not billing truth; unknown models degrade to unpriced + a
   note; zero usage is free; mock/offline providers (mockllm) price at $0; the table is overridable.
   Cost is surfaced at the run level in the md and json reports. Offline mockllm runs show synthetic
   tokens at $0.0000.
4. **Validation is offline-simulated.** A deterministic mockllm policy injects transient/permanent
   faults (no randomness, no wall clock) to prove `fail_on_error` and `retry_on_error` behavior;
   the generation-level knobs are covered by a wiring assertion. No live provider call in CI.

## Consequences

- A real eval can be run reliably and its cost reported, while CI stays fully offline.
- Reported cost is a dated estimate and will drift; the report says "as of <date>" and the table is
  overridable. This is observability, not billing.
- Establishes `docs/running-real-evals.md`, partially closing the onboarding-doc gap.

## Deferred

- Real-provider red-team / live smoke test; secrets-manager + `.env` integration; pre-flight cost
  *prediction* (we report actuals); response caching; Inspect's per-sample `cost_limit` /
  `token_limit` guardrails (natural follow-ons that reuse the same wiring).
