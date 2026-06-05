# Real-Provider Hardening — Design Spec (Phase 3 M5)

**Status:** Approved (design) · **Date:** 2026-06-05 · **Milestone:** Phase 3 M5
**Branch:** `phase-3-m5-real-provider-hardening`

## Goal

Make `agon` credible for **real-world use against real model providers** without sacrificing the
offline-first, no-API-key, sub-20-minute reproducibility guarantee. Concretely: a user can point
the harness at a real provider (Anthropic/OpenAI/etc.), have transient failures and rate limits
handled, bound run time/cost, and see **what the run actually cost** — and every bit of that is
provable offline.

## Background / why this shape

A production-readiness survey of the codebase found that resilience (retry/backoff/rate-limit/
timeout/concurrency) is **already provided by Inspect AI** as first-class knobs, but `agon` wires
only two of them. Reimplementing retry/backoff would reinvent the framework and violate
`ADR-0001` (build on Inspect). The genuinely-missing capability is **cost & token observability**:
`SUTResponse.token_usage` exists but is never populated, the Inspect log's usage stats never reach
the digest, and there is no price table or cost aggregation anywhere.

So "real-provider hardening" is scoped as **Expose + Observe**:
1. **Expose** Inspect's resilience knobs through `agon`'s config + CLI (wire & validate; Inspect executes).
2. **Observe** — build the missing cost/token observability layer end-to-end.
3. **Prove** both **offline** with a deterministic fault-injecting fake provider (no keys, CI-safe).

### Inspect knobs we are exposing (verified against installed `inspect_ai`)

- `GenerateConfig.max_retries` — request-level retry count (provider/LiteLLM backoff underneath).
- `GenerateConfig.timeout` — timeout (s) for an entire request (including retries).
- `GenerateConfig.attempt_timeout` — timeout (s) for any single attempt.
- `eval(retry_on_error=N)` — retry a whole **sample** on error.
- `eval(time_limit=N)` — per-sample wall-clock cap.
- `eval(fail_on_error=bool|float)` — fail the run only if the **error rate** exceeds a threshold
  (currently `agon` passes only a bool via `fail_fast`).
- `eval(max_connections=)` / `max_samples` — concurrency (already partly wired).

## Non-goals (deferred)

- **No hand-rolled resilience engine** (tenacity/circuit-breaker/rate-limit queue). Inspect/LiteLLM own this.
- **No pre-flight cost prediction.** We report measured **actuals** only; predicting tokens before
  a run is a separate, lower-value effort.
- **No secrets manager / `.env` integration.** Keys continue to come from the provider's env-var
  chain (e.g. `ANTHROPIC_API_KEY`). Secrets handling is a later milestone.
- **No live provider call in CI.** The real path is documented + runnable manually; CI stays offline.
- **No response caching.** Inspect offers `cache`; out of scope for this cut.

## Decisions locked

1. **Resilience = expose, not reimplement.** Knobs pass through to Inspect's `GenerateConfig` /
   `eval()`. We test our **wiring** + the behaviors we own; we do not re-test Inspect's internal
   retry/backoff.
2. **Bounded default `max_retries = 5`** (Inspect's default is *unlimited*). The "hardened" posture
   prefers a bounded run over an unbounded hang on a long rate-limit. Fully overridable.
3. **Price table lives in-repo as a dated snapshot** (`agon/cost/prices.py`), is **advisory**
   (point-in-time, not billing truth), and is **overridable** via config. Unknown model → cost
   omitted + a note (never an error). `mockllm` → `$0`.
4. **Cost is post-run actuals**, surfaced at the run (digest) level, rendered in md + json reports
   (JUnit unchanged).
5. **Validation is offline-simulated only** (per user choice): a deterministic fault-injection
   provider, no env-gated live test in this milestone.

## Architecture

Three independent units, each with one responsibility and its own tests; offline-first preserved
(`mockllm` default, no keys in CI).

```
RunConfig.resilience ──► run_eval/run_agent_eval ──► eval(..., generate-config + eval knobs) ──► Inspect
                                                          │
agon_generate_solver ──► SUTResponse.token_usage ◄────────┘ (state.output.usage)
EvalLog.stats.model_usage ──► analysis/logs (digest) ──► UsageSummary + CostSummary ──► reporting (md/json)
                                              ▲
                                   agon/cost (price table + estimate)
```

### Unit A — Resilience config surface

- **New** `ResilienceConfig` (Pydantic, `extra="forbid"`) on `RunConfig` as `resilience:`
  (mirrors `sut:` / `judge:`):

  | Field | Type / default | Maps to |
  |---|---|---|
  | `max_retries` | `int = 5` (`ge=0`) | `GenerateConfig.max_retries` |
  | `request_timeout` | `int \| None = None` (`ge=1`) | `GenerateConfig.timeout` |
  | `attempt_timeout` | `int \| None = None` (`ge=1`) | `GenerateConfig.attempt_timeout` |
  | `retry_on_error` | `int = 0` (`ge=0`) | `eval(retry_on_error=)` |
  | `sample_time_limit` | `int \| None = None` (`ge=1`) | `eval(time_limit=)` |
  | `fail_on_error` | `bool \| float = False` (float in `0..1`) | `eval(fail_on_error=)` |

- **Migrate** `RunConfig.fail_fast: bool` → `resilience.fail_on_error`. Update the two call sites
  in `agon/task/builder.py` and any configs/tests that reference `fail_fast`. (`RunConfig` is
  `extra="forbid"`; this is a clean break — acceptable pre-1.0, internal only.)
- **Wire** in `run_eval` and `run_agent_eval`: pass the GenerateConfig knobs to the model
  (via `eval(...)` generate kwargs or `get_model(..., config=GenerateConfig(...))` — implementer
  picks whichever Inspect supports cleanly and documents it) and the eval knobs
  (`retry_on_error`, `time_limit`, `fail_on_error`) to `eval()`.
- **CLI** (`agon run`): `--max-retries`, `--request-timeout`, `--attempt-timeout`,
  `--retry-on-error`, `--sample-time-limit`, `--fail-on-error` (parses `true/false` or a float).
  Config-file fields already flow through the TOML/YAML loader.

### Unit B — Cost & token observability

- **Populate usage:** in `agon_generate_solver`, read `state.output.usage` into
  `SUTResponse.token_usage` (input/output/total). Leave zeros when usage is absent (e.g. some
  mock paths). Optionally set `latency_ms` if cheaply available; tokens are the requirement.
- **`agon/cost/` package:**
  - `prices.py` — a **dated** (`PRICES_AS_OF = "2026-06-05"`) dict: model-id → `(usd_per_mtok_in,
    usd_per_mtok_out)`, covering a handful of current models (Claude Opus/Sonnet/Haiku,
    GPT-4o/-mini, and similar). A normalization step strips provider prefixes (`anthropic/`,
    `openai/`) for lookup. `mockllm` and unknown ids → not priced.
  - `estimate.py` — `estimate_cost(model, usage, table=DEFAULT_PRICES) -> CostEstimate`
    with `input_usd`, `output_usd`, `total_usd`, `priced: bool`, `note: str | None`. Unknown
    model → `priced=False`, `total_usd=0.0`, `note="no price for <model>"`.
- **Aggregate into the digest:** extend the digest builder (`agon/analysis/logs.py`) to read
  run/per-model usage from `EvalLog.stats.model_usage`, and add to `RunDigest`:
  - `UsageSummary` — per-model and total `TokenUsage`.
  - `CostSummary` — per-model + total `CostEstimate`, plus an `as_of` date and a `priced` flag,
    and any `notes` (unknown-model list). Overridable price source via config (a `cost`
    config field or an explicit prices override is acceptable; keep it simple).
- **Report:** `agon/reporting/generator.py` adds a **"Cost & usage"** section to the md + json
  reports. Offline shows `0 tokens / $0.00 (offline mockllm)`. JUnit unchanged.

### Unit C — Offline fault-injection provider & testing

- **Fault-injection fake** in `tests/support/` (e.g. `fault_injection.py`): a deterministic
  Inspect `modelapi` provider (or a callable-SUT shim) that errors / sleeps based on a **sample
  tag or call-counter** — **no randomness, no wall-clock dependence** (respects the
  no-`random`/no-`Date.now` reproducibility rule). It can: (a) raise a transient error for the
  first *k* calls to a sample then succeed; (b) always error for samples tagged to fail; (c) sleep
  to trip `sample_time_limit`.
- **Tests split by ownership:**
  - **Ours (behavioral):** `fail_on_error` float threshold trips iff error-rate exceeds it;
    `retry_on_error` recovers a once-failing sample; `sample_time_limit` trips a slow sample;
    cost math + price lookup + unknown-model handling + `mockllm → $0`; usage populated from output;
    report renders the Cost & usage section.
  - **Inspect's (wiring only):** the configured `max_retries` / `request_timeout` /
    `attempt_timeout` reach `eval()` / `GenerateConfig` with the right values (spy/assert), not a
    re-test of Inspect's retry internals.
- All offline; full suite stays green and inside the reproducibility budget.

## File structure (planned)

- **Modify** `agon/schemas/models.py` — add `ResilienceConfig`; add `resilience:` to `RunConfig`;
  remove `fail_fast`; add `UsageSummary` / `CostSummary` to the digest models (or co-locate with
  `RunDigest`).
- **Modify** `agon/task/builder.py` — wire resilience knobs into both `run_eval` / `run_agent_eval`.
- **Modify** `agon/sut/solvers.py` — populate `SUTResponse.token_usage` in `agon_generate_solver`.
- **Create** `agon/cost/__init__.py`, `agon/cost/prices.py`, `agon/cost/estimate.py`.
- **Modify** `agon/analysis/logs.py` — read usage from the log; build `UsageSummary` / `CostSummary`.
- **Modify** `agon/reporting/generator.py` — render the "Cost & usage" section (md + json).
- **Modify** `agon/cli/app.py` — new resilience flags + `--fail-on-error` parsing.
- **Create** `tests/support/fault_injection.py`, `tests/test_resilience.py`, `tests/test_cost.py`;
  extend reporting/digest tests for the usage/cost section.
- **Create** `docs/decisions/ADR-0006-real-provider-hardening.md`,
  `docs/running-real-evals.md`.
- **Modify** `README.md` (roadmap + quickstart) and `CLAUDE.md` (commands/notes).

## Testing strategy

- TDD throughout: scorer-style boundary tests for cost math (0 tokens, known model, unknown model,
  multi-model aggregate); behavioral tests for the resilience knobs via the fault-injection fake;
  wiring assertions for the GenerateConfig pass-through.
- Offline-only; `mockllm` default; no env keys. Keep printed/CLI output **ASCII** (cp1252 console).
- Definition of done: full suite green (+ the new tests), `ruff` clean, an offline demo/CLI run
  shows a Cost & usage section reading `$0.00 (offline mockllm)`, and a fault-injection test
  demonstrates a run failing on an error-rate threshold and recovering with `retry_on_error`.

## Open implementation details (decided during the plan, not re-litigated here)

- Exact mechanism for passing `GenerateConfig` to the run (`eval()` generate kwargs vs.
  `get_model(config=...)`) — implementer verifies against Inspect and documents the chosen path.
- Whether per-sample usage (vs. run-level only) is surfaced — run-level is the requirement;
  per-sample is optional if cheap.
- The precise set of models seeded in the price table — a small, current, dated set; unknowns
  degrade gracefully.

## Consequences

- Proves `agon` can run a **real** eval reliably and report its cost, while CI stays fully offline.
- The cost table is a **dated estimate**, not billing truth — documented in `ADR-0006` and the
  report ("as of <date>; advisory"). Drift is expected and the table is overridable.
- Establishes `docs/running-real-evals.md`, partially closing the onboarding-doc gap the README
  still lists as pending.
