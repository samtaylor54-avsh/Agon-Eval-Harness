# ADR-0001 — Build on Inspect AI rather than a hand-rolled runner

- **Status:** Accepted
- **Date:** 2026-06-04
- **Deciders:** Samuel R. Taylor

## Context

The PRD (`prd_content.md`) Part II specified a hand-rolled evaluation runner built on
LiteLLM + Typer + SQLite + anyio + tenacity — a custom `ExecutionEngine`, `ResultsStore`,
`RateLimiter`, `RetryPolicy`, and crash-`resume` command. The README and the project's
governing `CLAUDE.md`, however, mandate **Inspect AI (UK AISI)** as the eval framework
(alongside LangGraph, OpenTelemetry, etc.), and explicitly instruct contributors to "default
to this stack rather than introducing alternatives without discussion."

These two documents conflicted on the single most load-bearing decision in the project.

## Decision

**Adopt Inspect AI now** and rebuild the PRD's runner/scorers on Inspect's
`Task` / `Solver` / `Scorer` / log model. The PRD's *algorithms* (scorer formulas §25,
composite/label/regression logic) are stack-agnostic and are ported verbatim; only the
*delivery mechanism* changes.

What Inspect AI replaces (so we don't reinvent it):

| PRD component | Inspect AI mechanism |
|---|---|
| ExecutionEngine, Semaphore, RateLimiter, RetryPolicy (§24) | `eval()` / `eval_set()` + `--retry-on-error` |
| ResultsStore (SQLite, §22.5) | immutable `.eval` logs + `read_eval_log` / `EvalLog` |
| `resume` command (§24.5) | `eval_set()` auto-resume of incomplete logs |
| Trace capture / viewer (§8.6) | transcripts + `inspect view` |
| Repetition / flakiness (§24.4) | `epochs` + epoch reducers (`at_least`, `max_score`, `mode_score`) |
| ModelAdapter protocol (§22.1) | model providers + solvers (`mockllm`, litellm, custom HTTP) |

What we still build: the typed case schema, YAML loader + content-addressed versioning, the
11 scorers as `@scorer` functions, the composite/label/flake rollup, the regression
comparator, the report generator (Markdown/JSON/JUnit), judge calibration, and the `agon` CLI.

## Consequences

- **Positive:** far less bespoke infrastructure; built-in trace viewer, concurrency, retries,
  and resume; alignment with the stated learning/portfolio goals and the broader README stack
  (LangGraph, OTel) that layers on in Phase 2/3.
- **Negative:** results live in Inspect's log format, not a queryable SQLite store (we read
  logs into digests instead); the team must learn Inspect's abstractions.
- **Offline-first:** the default run uses Inspect's `mockllm/model` provider, so a reviewer can
  clone and run with **no API key and no model downloads** (protects the README's <20-minute
  reproducibility commitment). `INSPECT_DISABLE_MODEL_API=1` enforces this in CI.

## PRD corrections applied during implementation

The PRD (assembled from multiple AI tools) had minor internal inconsistencies, corrected here:

1. **Canonical case input** is the nested `input:` block (`user_message` / `documents`) from
   the §27 example, not the flat `user_input` / `context_documents` of §23.1.
2. `ScoringSpec` gained an `advisory` flag (referenced by the composite rule §25.13) and a
   validator forcing `pass_threshold == 1.0` for safety scorers (§25.12).
3. **Determinism is not over-claimed:** `temperature=0 + seed` does not guarantee identical
   provider output (PRD non-goal #4), so we only treat `mockllm` runs as deterministic.
4. **Retrieval isolation** (CLAUDE.md hard rule): `faithfulness` / `context_precision` /
   `answer_relevance` are reported as their own scores and excluded from the generation
   composite, though they still gate pass/fail.
5. **Judge calibration** was added to the MVP (PRD listed it only as future scope) to honor the
   Phase-1 "validate judges against human labels" requirement.
6. `answer_relevance` uses a judge rating rather than the PRD's embedding-cosine formula, to
   keep it on the dependency-free offline path. (Embedding-based relevance can return in Phase 2
   behind the `[semantic]` extra.)
7. Added `uv` + `ruff` to the toolchain (mandated by CLAUDE.md, absent from PRD §20.2).
