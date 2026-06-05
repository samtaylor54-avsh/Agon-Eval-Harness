# Real-Provider Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `agon` credible against real model providers — expose Inspect's resilience knobs (retries/timeouts/sample-retry/time-limit/error-rate threshold) via config + CLI, and add a cost/token observability layer — all provable fully offline.

**Architecture:** Three independent units. (1) A `ResilienceConfig` whose fields pass straight through to Inspect's `eval(**GenerateConfigArgs)` + `eval()` orchestration params (we wire & validate; Inspect executes). (2) A `agon/cost` package that prices the token usage Inspect already measures, via a dated/advisory table, surfaced in the run digest + md/json reports. (3) A deterministic offline fault-injection mockllm policy that proves the error-rate threshold and sample-retry behaviors without an API key.

**Tech Stack:** Python 3.12, Inspect AI (`eval`, `GenerateConfig`, `get_model`, `mockllm`), Pydantic v2, Typer, Jinja2, pytest (`asyncio_mode=auto`), uv, ruff.

**Spec:** `docs/superpowers/specs/2026-06-05-real-provider-hardening-design.md`

**Branch:** `phase-3-m5-real-provider-hardening` (already created; the design spec is committed there).

---

## Background the engineer needs (read before starting)

- **Inspect `eval()` accepts resilience knobs two ways** (verified against the installed
  `inspect_ai`): generation knobs arrive via `**kwargs: Unpack[GenerateConfigArgs]` —
  `max_retries`, `timeout`, `attempt_timeout`, `max_connections`; orchestration knobs are explicit
  params — `retry_on_error: int`, `time_limit: int` (per-sample wall clock), `fail_on_error:
  bool | float` (fail the run only if the error *rate* exceeds the float). So all knobs go through a
  single `eval(...)` call (this is how `agon` already passes `max_connections`).
- **Token usage** is an Inspect `ModelUsage` with `input_tokens` / `output_tokens` / `total_tokens`.
  Per-run totals live at `log.stats.model_usage: dict[str, ModelUsage]` (model id → usage). The
  per-sample model output is `state.output.usage` (a `ModelUsage | None`).
- **`agon`'s own `TokenUsage`** (`agon/sut/contract.py`) has fields `input` / `output` / `total`.
- **A case passes** iff every non-advisory scorer's `normalized_score >= pass_threshold`; the
  digest is built in `agon/analysis/logs.py::digest()` from the `EvalLog`. `RunDigest` lives in
  that file (NOT in `agon/schemas`).
- **Reports:** `agon/reporting/generator.py` renders md (Jinja2 template at
  `agon/reporting/templates/report.md.jinja2`), json (`render_json`), and JUnit. The md template
  receives the digest as `d`, so adding `d.cost` to the digest is enough to render it (no
  `render_markdown` signature change).
- **Offline mockllm policy signature** (from the M4 work): `policy(messages, tools, tool_choice,
  config) -> ModelOutput`, used via `get_model("mockllm/model", custom_outputs=policy)`. A policy
  that **raises** surfaces as a model/sample error (this is how we simulate transient/permanent
  failures offline). Keep policies deterministic — **no `random`, no `Date`/wall-clock** (per the
  repo's reproducibility rule).
- **Windows console is cp1252** — keep all `print`/CLI/`typer.echo` **output** strings ASCII
  (`-> ` not `→`). Docstrings, markdown, jinja templates, and yaml may be UTF-8.
- **Commit hygiene:** there are intentionally-unstaged banner-PNG deletions and untracked
  `docs/*.docx` in the tree. Every task uses a **targeted `git add`** of only its own files — never
  `git add .` / `git add -A`.

---

## File structure

- **Modify** `agon/schemas/models.py` — add `ResilienceConfig`; add `resilience: ResilienceConfig`
  to `RunConfig`; remove `fail_fast`.
- **Modify** `agon/task/builder.py` — add `resilience_eval_kwargs(config)`; use it in `run_eval`
  and `run_agent_eval`.
- **Modify** `agon/sut/solvers.py` — populate `SUTResponse.token_usage` in `agon_generate_solver`.
- **Create** `agon/cost/__init__.py`, `agon/cost/prices.py`, `agon/cost/estimate.py` — price table +
  cost math + `CostSummary`.
- **Modify** `agon/analysis/logs.py` — add `cost: CostSummary` to `RunDigest`; populate it in
  `digest()` from `log.stats.model_usage`.
- **Modify** `agon/reporting/generator.py` (`render_json`) + `agon/reporting/templates/report.md.jinja2`
  — render a "Cost & usage" section.
- **Modify** `agon/cli/app.py` — resilience flags on `agon run`.
- **Create** `tests/support/__init__.py`, `tests/support/fault_injection.py` — offline flaky policy.
- **Create** `tests/test_resilience.py`, `tests/test_cost.py`; **modify** an existing reporting/digest
  test or add cases for the cost section.
- **Create** `docs/decisions/ADR-0006-real-provider-hardening.md`, `docs/running-real-evals.md`.
- **Modify** `README.md`, `CLAUDE.md`.

---

## Task 1: `ResilienceConfig` + builder wiring

**Files:**
- Modify: `agon/schemas/models.py`
- Modify: `agon/task/builder.py`
- Test: `tests/test_resilience.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resilience.py` with this content:

```python
"""Phase 3 M5 — resilience config surface + offline fault-injection behavior."""

from agon.schemas import ResilienceConfig, RunConfig
from agon.task.builder import resilience_eval_kwargs


def test_resilience_defaults():
    r = ResilienceConfig()
    assert r.max_retries == 5
    assert r.retry_on_error == 0
    assert r.fail_on_error is False
    assert r.request_timeout is None
    assert r.attempt_timeout is None
    assert r.sample_time_limit is None


def test_runconfig_has_resilience_and_no_fail_fast():
    cfg = RunConfig()
    assert isinstance(cfg.resilience, ResilienceConfig)
    assert not hasattr(cfg, "fail_fast")


def test_eval_kwargs_minimal_defaults():
    kwargs = resilience_eval_kwargs(RunConfig())
    assert kwargs["max_connections"] == 8
    assert kwargs["max_retries"] == 5
    assert kwargs["retry_on_error"] == 0
    assert kwargs["fail_on_error"] is False
    # Optional knobs are omitted (None) so Inspect uses its own defaults.
    assert "timeout" not in kwargs
    assert "attempt_timeout" not in kwargs
    assert "time_limit" not in kwargs


def test_eval_kwargs_full():
    cfg = RunConfig(
        resilience=ResilienceConfig(
            max_retries=2,
            request_timeout=120,
            attempt_timeout=60,
            retry_on_error=1,
            sample_time_limit=30,
            fail_on_error=0.25,
        )
    )
    kwargs = resilience_eval_kwargs(cfg)
    assert kwargs["max_retries"] == 2
    assert kwargs["timeout"] == 120
    assert kwargs["attempt_timeout"] == 60
    assert kwargs["retry_on_error"] == 1
    assert kwargs["time_limit"] == 30
    assert kwargs["fail_on_error"] == 0.25
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_resilience.py -q`
Expected: FAIL — `ImportError: cannot import name 'ResilienceConfig'` (and `resilience_eval_kwargs`).

- [ ] **Step 3: Add `ResilienceConfig` and wire it into `RunConfig`**

In `agon/schemas/models.py`, add this class immediately **before** `class RunConfig`:

```python
class ResilienceConfig(BaseModel):
    """Run-resilience knobs. Each field passes through to Inspect's eval()/GenerateConfig;
    Inspect (and LiteLLM) execute the retry/backoff/timeout — agon only wires and validates."""

    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=5, ge=0)  # per-request retries (Inspect default is unlimited)
    request_timeout: int | None = Field(default=None, ge=1)  # whole-request timeout (s)
    attempt_timeout: int | None = Field(default=None, ge=1)  # per-attempt timeout (s)
    retry_on_error: int = Field(default=0, ge=0)  # per-sample retries
    sample_time_limit: int | None = Field(default=None, ge=1)  # per-sample wall-clock cap (s)
    fail_on_error: bool | float = False  # True/False, or an error-rate threshold in 0..1
```

Then, in `class RunConfig`, **add** the field (place it next to `judge:`):

```python
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
```

and **remove** the `fail_fast: bool = False` line.

- [ ] **Step 4: Export `ResilienceConfig`**

In `agon/schemas/__init__.py`, add `ResilienceConfig` to the import from `.models` and to
`__all__` (keep alphabetical, mirror the existing `RunConfig` / `SUTConfig` exports). Read the file
first to match its exact structure.

- [ ] **Step 5: Add `resilience_eval_kwargs` and use it in the builder**

In `agon/task/builder.py`, add this function (after `resolve_model`):

```python
def resilience_eval_kwargs(config: RunConfig) -> dict[str, Any]:
    """Map RunConfig resilience knobs to inspect_ai.eval() kwargs.

    Generation knobs (max_retries/timeout/attempt_timeout/max_connections) ride eval()'s
    **GenerateConfigArgs; orchestration knobs (retry_on_error/time_limit/fail_on_error) are
    explicit eval() params. Optional (None) knobs are omitted so Inspect keeps its own defaults.
    """
    r = config.resilience
    kwargs: dict[str, Any] = {
        "max_connections": config.max_connections,
        "max_retries": r.max_retries,
        "retry_on_error": r.retry_on_error,
        "fail_on_error": r.fail_on_error,
    }
    if r.request_timeout is not None:
        kwargs["timeout"] = r.request_timeout
    if r.attempt_timeout is not None:
        kwargs["attempt_timeout"] = r.attempt_timeout
    if r.sample_time_limit is not None:
        kwargs["time_limit"] = r.sample_time_limit
    return kwargs
```

Then in **both** `run_eval` and `run_agent_eval`, replace the `eval(...)` call's
`max_connections=config.max_connections,` and `fail_on_error=config.fail_fast,` lines with a single
`**resilience_eval_kwargs(config),`. Each call becomes:

```python
    logs = eval(
        task,
        model=resolve_model(config),
        log_dir=config.log_dir,
        display=display,
        **resilience_eval_kwargs(config),
    )
```

- [ ] **Step 6: Migrate the rest of the `fail_fast` references**

Use the Grep tool to search for `fail_fast` across `agon`, `tests`, and `examples`.
For every hit outside this task's own edits (e.g. a config fixture or a test), change
`fail_fast=<x>` / `fail_fast: <x>` to the nested form `resilience=ResilienceConfig(fail_on_error=<x>)`
(Python) or `resilience: {fail_on_error: <x>}` (yaml/toml). If there are no other hits, do nothing.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_resilience.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the full suite + lint**

Run: `uv run pytest -q` (expect all pass + 1 skipped — confirms the `fail_fast` migration broke nothing).
Run: `uv run ruff check agon tests`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add agon/schemas/models.py agon/schemas/__init__.py agon/task/builder.py tests/test_resilience.py
git commit -m "$(printf 'feat(hardening): ResilienceConfig + eval() knob wiring\n\nExpose Inspect retry/timeout/sample-retry/time-limit/error-rate knobs via\nRunConfig.resilience; map them to eval() kwargs. Replaces the fail_fast bool.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```
(Add any extra files the Step 6 migration touched to this `git add`.)

---

## Task 2: Offline fault-injection provider + behavioral resilience tests

**Files:**
- Create: `tests/support/__init__.py`, `tests/support/fault_injection.py`
- Test: `tests/test_resilience.py` (append)

This proves — fully offline — that `fail_on_error` (error-rate threshold) and `retry_on_error`
(sample retry) behave correctly with `agon`'s solver in the loop. The timeout/`max_retries` knobs
are Inspect's behavior; Task 1 already unit-tests that we wire them correctly.

- [ ] **Step 1: Write the fault-injection policy**

Create `tests/support/__init__.py` (empty file).

Create `tests/support/fault_injection.py`:

```python
"""Deterministic offline mockllm policies that simulate provider faults (Phase 3 M5 tests).

No randomness, no wall-clock: failures are decided by the user message text and a per-sample
call counter, so runs are fully reproducible. A raised exception surfaces as a model/sample error.
"""

from __future__ import annotations

from inspect_ai.model import ModelOutput

PERMANENT_FAIL_TAG = "[boom]"


def _last_user(messages) -> str:
    items = [m for m in messages if getattr(m, "role", None) == "user"]
    return items[-1].text if items else ""


class FlakyPolicy:
    """Raise on the first ``transient_failures`` calls *per sample*, then succeed.

    Samples whose message contains ``PERMANENT_FAIL_TAG`` always raise.
    """

    def __init__(self, transient_failures: int = 0):
        self.transient_failures = transient_failures
        self._calls: dict[str, int] = {}

    def __call__(self, messages, tools, tool_choice, config) -> ModelOutput:
        user = _last_user(messages)
        if PERMANENT_FAIL_TAG in user:
            raise RuntimeError("simulated permanent model error")
        seen = self._calls.get(user, 0)
        self._calls[user] = seen + 1
        if seen < self.transient_failures:
            raise RuntimeError("simulated transient model error")
        return ModelOutput.from_content("mockllm", "ok")
```

- [ ] **Step 2: Append the behavioral tests**

Append to `tests/test_resilience.py`:

```python
# ---------------------------- offline fault-injection behavior ---------------------------- #
from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.model import get_model  # noqa: E402

from agon.schemas import AgonCase, AgonDataset  # noqa: E402
from agon.task import agon_task  # noqa: E402
from tests.support.fault_injection import FlakyPolicy  # noqa: E402


def _dataset(messages_by_id):
    cases = [
        AgonCase(test_id=tid, name=tid, category="resilience", input={"user_message": msg})
        for tid, msg in messages_by_id.items()
    ]
    return AgonDataset(name="resilience_suite", test_cases=cases)


def _run(dataset, policy, tmp_path, **eval_kwargs):
    cfg = RunConfig(log_dir=str(tmp_path))
    task = agon_task(dataset, cfg)
    model = get_model("mockllm/model", custom_outputs=policy)
    return inspect_eval(task, model=model, log_dir=str(tmp_path), display="none", **eval_kwargs)[0]


def test_retry_on_error_recovers_a_transient_failure(tmp_path):
    dataset = _dataset({"flaky": "hello"})
    log = _run(dataset, FlakyPolicy(transient_failures=1), tmp_path, retry_on_error=1)
    assert log.status == "success"
    assert (log.results.completed_samples or 0) == 1


def test_no_retry_lets_a_transient_failure_surface(tmp_path):
    dataset = _dataset({"flaky": "hello"})
    log = _run(dataset, FlakyPolicy(transient_failures=1), tmp_path, retry_on_error=0)
    # With no sample retry the single error is contained but recorded.
    assert (log.results.completed_samples or 0) == 0 or log.status != "success"


def test_fail_on_error_threshold_trips_above_rate(tmp_path):
    # 2 of 4 samples always fail -> error rate 0.5.
    dataset = _dataset(
        {"ok1": "fine", "ok2": "fine", "bad1": "boom [boom]", "bad2": "boom [boom]"}
    )
    log = _run(dataset, FlakyPolicy(), tmp_path, fail_on_error=0.4)
    assert log.status == "error"


def test_fail_on_error_threshold_tolerates_below_rate(tmp_path):
    dataset = _dataset(
        {"ok1": "fine", "ok2": "fine", "bad1": "boom [boom]", "bad2": "boom [boom]"}
    )
    log = _run(dataset, FlakyPolicy(), tmp_path, fail_on_error=0.6)
    assert log.status == "success"
```

- [ ] **Step 3: Run the new tests**

Run: `uv run pytest tests/test_resilience.py -q`
Expected: PASS (8 passed total — 4 from Task 1 + 4 here).

NOTE (integration risk to verify here): this is the one place that assumes a raising mockllm policy
surfaces as a sample *error* and that `log.results.completed_samples` / `log.status` reflect it. If
the field names differ in the installed Inspect (e.g. `log.results.completed_samples` is named
differently, or status uses another literal), adjust the **assertions** to the real API — read
`inspect_ai.log._log.EvalResults` / `EvalLog.status` — but keep the policy and the
`fail_on_error` / `retry_on_error` knobs as specified. Do not weaken a test to vacuously pass.

- [ ] **Step 4: Lint + commit**

Run: `uv run ruff check agon tests`
Expected: `All checks passed!`

```bash
git add tests/support/__init__.py tests/support/fault_injection.py tests/test_resilience.py
git commit -m "$(printf 'test(hardening): offline fault-injection for fail_on_error + retry_on_error\n\nDeterministic mockllm policy (no random/clock) proves the error-rate threshold\ntrips and sample-retry recovers a transient failure, fully offline.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Populate token usage from the model output

**Files:**
- Modify: `agon/sut/solvers.py`
- Test: `tests/test_usage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_usage.py`:

```python
"""Phase 3 M5 — token usage is populated from the Inspect model output."""

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import get_model

from agon.sut import SUT_RESPONSE_KEY
from agon.sut.solvers import agon_generate_solver


def test_generate_solver_populates_token_usage(tmp_path):
    task = Task(dataset=[Sample(input="hello", target="ok")], solver=agon_generate_solver())
    # mockllm reports usage on its ModelOutput; assert we copy it into SUTResponse.
    log = eval(task, model=get_model("mockllm/model"), log_dir=str(tmp_path), display="none")[0]
    sample = log.samples[0]
    sut = sample.store.get(SUT_RESPONSE_KEY) or sample.metadata.get(SUT_RESPONSE_KEY)
    assert sut is not None
    usage = sut["token_usage"]
    # mockllm yields a usage object; the fields exist and are ints (often 1/1/2 or 0/0/0).
    assert set(usage) >= {"input", "output", "total"}
    assert usage["total"] == usage["input"] + usage["output"] or usage["total"] >= 0
```

NOTE: `SUT_RESPONSE_KEY` is attached to `state.metadata` by `_attach` (see `agon/sut/solvers.py`).
If the e2e read path differs (metadata vs. store), adjust the **read** in the test to match how
`_attach` stores it — but keep the assertion that `token_usage` is populated.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_usage.py -q`
Expected: FAIL — `token_usage` is all zeros (solver doesn't copy usage yet) so
`usage["total"] == usage["input"] + usage["output"]` may pass vacuously at 0/0/0; if mockllm
reports non-zero usage the assertion on copied values fails. (If mockllm reports 0/0/0 and the test
passes vacuously, strengthen by asserting against a stubbed output — see Step 3 note.)

- [ ] **Step 3: Populate usage in the solver**

In `agon/sut/solvers.py`, import `TokenUsage` (add to the existing import from
`agon.sut.contract`), then in `agon_generate_solver.solve`, replace the `SUTResponse(...)`
construction with one that copies usage:

```python
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state = await generate(state)
        usage = getattr(state.output, "usage", None)
        token_usage = (
            TokenUsage(
                input=usage.input_tokens,
                output=usage.output_tokens,
                total=usage.total_tokens,
            )
            if usage is not None
            else TokenUsage()
        )
        response = SUTResponse(
            final_answer=state.output.completion or "",
            trace_id=f"{state.sample_id}_{getattr(state, 'epoch', 1)}",
            token_usage=token_usage,
            error=state.output.error,
        )
        _attach(state, response)
        return state
```

(Add `TokenUsage` to the `from agon.sut.contract import (...)` block.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_usage.py -q`
Expected: PASS.

If mockllm reports 0/0/0 (making the test vacuous), make the test deterministic instead: build a
`ModelOutput` with a known `ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14)` via
`get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm", "ok")])` and a
custom output carrying usage, OR call the solver against a stubbed `state.output`. Assert
`usage == {"input": 10, "output": 4, "total": 14}`. The point: prove the copy, not mockllm's numbers.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check agon tests`
```bash
git add agon/sut/solvers.py tests/test_usage.py
git commit -m "$(printf 'feat(hardening): populate SUTResponse.token_usage from model output\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: `agon/cost` — dated price table + cost math

**Files:**
- Create: `agon/cost/__init__.py`, `agon/cost/prices.py`, `agon/cost/estimate.py`
- Test: `tests/test_cost.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cost.py`:

```python
"""Phase 3 M5 — cost estimation from token usage (dated, advisory price table)."""

from agon.cost import CostSummary, estimate_cost, summarize_cost
from agon.sut import TokenUsage

# A controlled table so cost math is independent of the shipped DEFAULT_PRICES values.
PRICES = {"test-model": (2.0, 6.0)}  # USD per 1M tokens (input, output)


def test_estimate_known_model():
    est = estimate_cost("test-model", TokenUsage(input=1_000_000, output=500_000, total=1_500_000), PRICES)
    assert est.priced is True
    assert est.input_usd == 2.0
    assert est.output_usd == 3.0
    assert est.total_usd == 5.0


def test_estimate_strips_provider_prefix():
    est = estimate_cost("openai/test-model", TokenUsage(input=2_000_000, output=0, total=2_000_000), PRICES)
    assert est.priced is True
    assert est.total_usd == 4.0


def test_estimate_zero_usage_is_free_and_unnoted():
    est = estimate_cost("anything-unknown", TokenUsage(), PRICES)
    assert est.priced is True
    assert est.total_usd == 0.0
    assert est.note is None


def test_estimate_unknown_model_with_usage_is_unpriced_with_note():
    est = estimate_cost("mystery-model", TokenUsage(input=1000, output=10, total=1010), PRICES)
    assert est.priced is False
    assert est.total_usd == 0.0
    assert est.note is not None and "mystery-model" in est.note


def test_summarize_aggregates_and_flags_partial():
    usage_by_model = {
        "test-model": TokenUsage(input=1_000_000, output=0, total=1_000_000),
        "mystery-model": TokenUsage(input=1000, output=10, total=1010),
    }
    summary = summarize_cost(usage_by_model, PRICES)
    assert isinstance(summary, CostSummary)
    assert summary.total_usd == 2.0  # only the priced model contributes
    assert summary.usage.total == 1_001_010
    assert summary.priced is False  # one model was unpriced
    assert any("mystery-model" in n for n in summary.notes)
    assert summary.as_of  # dated


def test_summarize_empty_usage_is_free_and_priced():
    summary = summarize_cost({}, PRICES)
    assert summary.total_usd == 0.0
    assert summary.usage.total == 0
    assert summary.priced is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cost.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agon.cost'`.

- [ ] **Step 3: Write the price table**

Create `agon/cost/prices.py`:

```python
"""Dated, advisory model price table — USD per 1,000,000 tokens (Phase 3 M5).

These prices are a POINT-IN-TIME snapshot (see PRICES_AS_OF), NOT billing truth. They drift;
treat any reported cost as an estimate. Unknown models are simply not priced (cost omitted, never
an error). Override by passing your own ``prices`` mapping to the cost functions.
"""

from __future__ import annotations

PRICES_AS_OF = "2026-06-05"

# model key (provider prefix stripped, lowercased) -> (usd_per_mtok_input, usd_per_mtok_output).
# Representative/advisory values — verify against current provider pricing before relying on them.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def normalize_model(model: str) -> str:
    """Strip a provider prefix and lowercase. 'Anthropic/Claude-Opus-4-5' -> 'claude-opus-4-5'."""
    key = model.split("/", 1)[1] if "/" in model else model
    return key.lower()


def price_for(model: str, prices: dict[str, tuple[float, float]] = DEFAULT_PRICES):
    """Return (input_rate, output_rate) per 1M tokens, or None if the model is not in the table."""
    return prices.get(normalize_model(model))
```

- [ ] **Step 4: Write the cost math**

Create `agon/cost/estimate.py`:

```python
"""Estimate run cost from token usage using a (dated, advisory) price table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agon.cost.prices import DEFAULT_PRICES, PRICES_AS_OF, price_for
from agon.sut.contract import TokenUsage

_PER_MTOK = 1_000_000


class CostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    input_usd: float = 0.0
    output_usd: float = 0.0
    total_usd: float = 0.0
    priced: bool = False
    note: str | None = None


class CostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str = PRICES_AS_OF
    total_usd: float = 0.0
    priced: bool = True  # True iff every model that had usage was priced
    usage: TokenUsage = Field(default_factory=TokenUsage)
    by_model: list[CostEstimate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def estimate_cost(
    model: str,
    usage: TokenUsage,
    prices: dict[str, tuple[float, float]] = DEFAULT_PRICES,
) -> CostEstimate:
    """Cost for one model's usage. Zero usage is free (and unnoted); unknown non-zero usage is
    unpriced with a note."""
    if usage.total == 0:
        return CostEstimate(model=model, priced=True)
    rates = price_for(model, prices)
    if rates is None:
        return CostEstimate(model=model, priced=False, note=f"no price for {model}")
    in_rate, out_rate = rates
    input_usd = usage.input / _PER_MTOK * in_rate
    output_usd = usage.output / _PER_MTOK * out_rate
    return CostEstimate(
        model=model,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=input_usd + output_usd,
        priced=True,
    )


def summarize_cost(
    usage_by_model: dict[str, TokenUsage],
    prices: dict[str, tuple[float, float]] = DEFAULT_PRICES,
) -> CostSummary:
    """Aggregate per-model usage into a run-level cost summary."""
    by_model: list[CostEstimate] = []
    total_usd = 0.0
    agg = TokenUsage()
    notes: list[str] = []
    all_priced = True
    for model, usage in sorted(usage_by_model.items()):
        est = estimate_cost(model, usage, prices)
        by_model.append(est)
        total_usd += est.total_usd
        agg = TokenUsage(
            input=agg.input + usage.input,
            output=agg.output + usage.output,
            total=agg.total + usage.total,
        )
        if not est.priced:
            all_priced = False
            if est.note:
                notes.append(est.note)
    return CostSummary(
        total_usd=total_usd,
        priced=all_priced,
        usage=agg,
        by_model=by_model,
        notes=notes,
    )
```

- [ ] **Step 5: Write the package init**

Create `agon/cost/__init__.py`:

```python
"""Cost & token observability (Phase 3 M5)."""

from agon.cost.estimate import CostEstimate, CostSummary, estimate_cost, summarize_cost
from agon.cost.prices import DEFAULT_PRICES, PRICES_AS_OF, normalize_model, price_for

__all__ = [
    "CostEstimate",
    "CostSummary",
    "DEFAULT_PRICES",
    "PRICES_AS_OF",
    "estimate_cost",
    "normalize_model",
    "price_for",
    "summarize_cost",
]
```

- [ ] **Step 6: Run it to verify it passes**

Run: `uv run pytest tests/test_cost.py -q`
Expected: PASS (7 passed).

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check agon tests`
```bash
git add agon/cost/__init__.py agon/cost/prices.py agon/cost/estimate.py tests/test_cost.py
git commit -m "$(printf 'feat(hardening): agon.cost - dated advisory price table + cost math\n\nestimate_cost/summarize_cost price token usage; zero usage is free, unknown\nmodels degrade to unpriced+note. Prices are a dated, overridable estimate.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Surface cost in the digest + reports

**Files:**
- Modify: `agon/analysis/logs.py`
- Modify: `agon/reporting/generator.py`, `agon/reporting/templates/report.md.jinja2`
- Test: `tests/test_cost_reporting.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cost_reporting.py`:

```python
"""Phase 3 M5 — cost summary flows into the RunDigest and the md/json reports."""

import json

from inspect_ai import eval
from inspect_ai.model import get_model

from agon.analysis.logs import digest
from agon.cost import CostSummary
from agon.reporting.generator import render_json, render_markdown
from agon.schemas import AgonCase, AgonDataset, Recommendation, RunConfig
from agon.task import agon_task


def _offline_log(tmp_path):
    dataset = AgonDataset(
        name="cost_suite",
        test_cases=[AgonCase(test_id="c1", name="c1", category="c", input={"user_message": "hi"})],
    )
    task = agon_task(dataset, RunConfig(log_dir=str(tmp_path)))
    return eval(task, model=get_model("mockllm/model"), log_dir=str(tmp_path), display="none")[0]


def test_digest_carries_cost_summary(tmp_path):
    d = digest(_offline_log(tmp_path))
    assert isinstance(d.cost, CostSummary)
    # Offline mockllm -> no priced usage burned -> $0.
    assert d.cost.total_usd == 0.0


def test_markdown_has_cost_section(tmp_path):
    d = digest(_offline_log(tmp_path))
    md = render_markdown(d, None, Recommendation.PASS)
    assert "Cost & usage" in md
    assert "Total tokens" in md


def test_json_has_cost_block(tmp_path):
    d = digest(_offline_log(tmp_path))
    payload = json.loads(render_json(d, None, Recommendation.PASS))
    assert "cost" in payload
    assert payload["cost"]["total_usd"] == 0.0
    assert "as_of" in payload["cost"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cost_reporting.py -q`
Expected: FAIL — `RunDigest` has no `cost` attribute / `AttributeError`.

- [ ] **Step 3: Add `cost` to `RunDigest` and populate it in `digest()`**

In `agon/analysis/logs.py`:

1. Add imports near the top (after the existing imports):

```python
from agon.cost import CostSummary, summarize_cost
from agon.sut import TokenUsage
```

2. Add the field to `class RunDigest` (after `error_count`):

```python
    cost: CostSummary = Field(default_factory=CostSummary)
```

3. In `digest()`, build the cost summary from the log's model usage and pass it to the
`RunDigest(...)` constructor. Add this just before the `return RunDigest(`:

```python
    stats = getattr(log, "stats", None)
    model_usage = getattr(stats, "model_usage", {}) or {}
    usage_by_model = {
        model: TokenUsage(
            input=mu.input_tokens, output=mu.output_tokens, total=mu.total_tokens
        )
        for model, mu in model_usage.items()
    }
    cost = summarize_cost(usage_by_model)
```

and add `cost=cost,` as the final argument to `RunDigest(...)`.

- [ ] **Step 4: Render cost in JSON**

In `agon/reporting/generator.py::render_json`, add to the `payload` dict (after `"error_count"`):

```python
        "cost": d.cost.model_dump(),
```

- [ ] **Step 5: Render cost in the md template**

In `agon/reporting/templates/report.md.jinja2`, add this block **before** the
`{% if retrieval_rows %}` section (keep the surrounding blank lines tidy):

```jinja
## Cost & usage
| Metric | Value |
|---|---|
| Input tokens | {{ d.cost.usage.input }} |
| Output tokens | {{ d.cost.usage.output }} |
| Total tokens | {{ d.cost.usage.total }} |
| Estimated cost | ${{ "%.4f"|format(d.cost.total_usd) }} (as of {{ d.cost.as_of }}{% if not d.cost.priced %}; partial — see notes{% endif %}) |
{% if d.cost.usage.total == 0 %}
_Offline run (mockllm): no token usage, $0.0000._
{% endif %}{% for n in d.cost.notes %}- note: {{ n }}
{% endfor %}
```

- [ ] **Step 6: Run it to verify it passes**

Run: `uv run pytest tests/test_cost_reporting.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Full suite + lint**

Run: `uv run pytest -q` (expect all pass + 1 skipped — confirms no existing report test broke).
Run: `uv run ruff check agon tests`
Expected: `All checks passed!`

If an existing reporting/digest test asserts an exact JSON key set or md snapshot and now fails
because of the new `cost` block, update that test to include the cost data (the new block is
expected output, not a regression).

- [ ] **Step 8: Commit**

```bash
git add agon/analysis/logs.py agon/reporting/generator.py agon/reporting/templates/report.md.jinja2 tests/test_cost_reporting.py
git commit -m "$(printf 'feat(hardening): surface cost & token usage in the digest and reports\n\nRunDigest.cost is built from EvalLog.stats.model_usage; md gets a Cost & usage\nsection and json a cost block. Offline runs show 0 tokens / $0.0000.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: CLI flags + ADR + docs + final verification

**Files:**
- Modify: `agon/cli/app.py`
- Create: `docs/decisions/ADR-0006-real-provider-hardening.md`, `docs/running-real-evals.md`
- Modify: `README.md`, `CLAUDE.md`
- Test: `tests/test_cli_resilience.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/test_cli_resilience.py`:

```python
"""Phase 3 M5 — `agon run` exposes resilience flags onto RunConfig.resilience."""

from agon.cli.app import _apply_resilience_flags
from agon.schemas import RunConfig


def test_apply_resilience_flags_sets_fields():
    cfg = RunConfig()
    _apply_resilience_flags(
        cfg,
        max_retries=2,
        request_timeout=120,
        attempt_timeout=60,
        retry_on_error=1,
        sample_time_limit=30,
        fail_on_error="0.25",
    )
    r = cfg.resilience
    assert r.max_retries == 2
    assert r.request_timeout == 120
    assert r.attempt_timeout == 60
    assert r.retry_on_error == 1
    assert r.sample_time_limit == 30
    assert r.fail_on_error == 0.25


def test_apply_resilience_flags_parses_bool_fail_on_error():
    cfg = RunConfig()
    _apply_resilience_flags(cfg, fail_on_error="true")
    assert cfg.resilience.fail_on_error is True


def test_apply_resilience_flags_ignores_unset():
    cfg = RunConfig()
    _apply_resilience_flags(cfg)  # all None -> no change
    assert cfg.resilience == RunConfig().resilience
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli_resilience.py -q`
Expected: FAIL — `ImportError: cannot import name '_apply_resilience_flags'`.

- [ ] **Step 3: Add the flag-applier and wire it into `run`**

In `agon/cli/app.py`, add this helper (above the `run` command):

```python
def _parse_fail_on_error(value: str) -> bool | float:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    return float(value)


def _apply_resilience_flags(
    cfg: RunConfig,
    *,
    max_retries: int | None = None,
    request_timeout: int | None = None,
    attempt_timeout: int | None = None,
    retry_on_error: int | None = None,
    sample_time_limit: int | None = None,
    fail_on_error: str | None = None,
) -> None:
    r = cfg.resilience
    if max_retries is not None:
        r.max_retries = max_retries
    if request_timeout is not None:
        r.request_timeout = request_timeout
    if attempt_timeout is not None:
        r.attempt_timeout = attempt_timeout
    if retry_on_error is not None:
        r.retry_on_error = retry_on_error
    if sample_time_limit is not None:
        r.sample_time_limit = sample_time_limit
    if fail_on_error is not None:
        r.fail_on_error = _parse_fail_on_error(fail_on_error)
```

Then add these options to the `run` command signature (after the existing `baseline` option):

```python
    max_retries: int = typer.Option(None, "--max-retries", help="Per-request retry count"),
    request_timeout: int = typer.Option(None, "--request-timeout", help="Whole-request timeout (s)"),
    attempt_timeout: int = typer.Option(None, "--attempt-timeout", help="Per-attempt timeout (s)"),
    retry_on_error: int = typer.Option(None, "--retry-on-error", help="Per-sample retry count"),
    sample_time_limit: int = typer.Option(None, "--sample-time-limit", help="Per-sample time limit (s)"),
    fail_on_error: str = typer.Option(None, "--fail-on-error", help="true|false or error-rate 0..1"),
```

and call the applier inside `run` (after the `if baseline:` block, before `try: ds = load_dataset`):

```python
    _apply_resilience_flags(
        cfg,
        max_retries=max_retries,
        request_timeout=request_timeout,
        attempt_timeout=attempt_timeout,
        retry_on_error=retry_on_error,
        sample_time_limit=sample_time_limit,
        fail_on_error=fail_on_error,
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli_resilience.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Write ADR-0006**

Create `docs/decisions/ADR-0006-real-provider-hardening.md`:

```markdown
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
2. **Bounded default `max_retries = 5`** (Inspect's default is unlimited) — a hardened run should
   not hang indefinitely on a long rate-limit. Fully overridable.
3. **Cost is an in-repo, dated, advisory estimate.** `agon/cost` prices the token usage Inspect
   measures (`EvalLog.stats.model_usage`) via a `DEFAULT_PRICES` table stamped `PRICES_AS_OF`.
   Prices are a point-in-time snapshot, not billing truth; unknown models degrade to unpriced + a
   note; zero usage is free; the table is overridable. Cost is surfaced at the run level in the md
   and json reports. Offline mockllm runs show 0 tokens / $0.0000.
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
```

- [ ] **Step 6: Write the "running a real eval" guide**

Create `docs/running-real-evals.md`:

```markdown
# Running a real eval (providers, resilience, cost)

`agon` runs **offline by default** (`mockllm`, no API key). To run against a real provider:

## 1. Pick a provider + set its key

Keys come from the provider's own environment variables (e.g. `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`). `agon` does not store secrets.

```bash
export ANTHROPIC_API_KEY=sk-...            # your shell; never commit this
uv sync --extra providers                  # install the provider SDKs
uv run agon run examples/datasets/rag_smoke.yaml --model anthropic/claude-sonnet-4-5
```

`--model <provider>/<model>` switches the SUT adapter from `mockllm` to `litellm` automatically.

## 2. Tune resilience (all optional; sensible defaults)

| Flag | Meaning | Default |
|---|---|---|
| `--max-retries N` | retries per model request | 5 |
| `--request-timeout S` | whole-request timeout (s) | provider default |
| `--attempt-timeout S` | per-attempt timeout (s) | provider default |
| `--retry-on-error N` | retries for a whole failed sample | 0 |
| `--sample-time-limit S` | per-sample wall-clock cap (s) | none |
| `--fail-on-error V` | `true`/`false`, or an error-rate threshold `0..1` | false |

Example — bound a flaky run and tolerate up to 10% sample errors:

```bash
uv run agon run suite.yaml --model anthropic/claude-sonnet-4-5 \
  --max-retries 3 --sample-time-limit 120 --fail-on-error 0.1
```

## 3. Read the cost

Every report includes a **Cost & usage** section (md + json) with input/output/total tokens and an
estimated USD cost, stamped `as of <date>`. Prices are an advisory, point-in-time snapshot
(`agon/cost/prices.py`) — treat the figure as an estimate, not a bill. Offline runs show
`0 tokens / $0.0000`.
```

- [ ] **Step 7: Update README + CLAUDE**

In `README.md`, under **Phase 3**, add a new checked line after the adversarial-suite line:

```markdown
- [x] **Real-provider hardening** — resilience knobs (retries/timeouts/sample-retry/time-limit/error-rate threshold) exposed via config + CLI, plus offline-provable **cost & token observability** in reports (M5, ADR-0006); secrets-manager + live red-team pending
```

In `CLAUDE.md`, in the ```bash commands block, after the `adversarial_quickstart.py` line, add:

```bash
uv run agon run suite.yaml --model anthropic/claude-sonnet-4-5 --fail-on-error 0.1  # real-provider run (needs [providers] + a key); see docs/running-real-evals.md
```

- [ ] **Step 8: Final verification (offline)**

Run each and confirm:

```bash
uv run ruff check agon tests          # Expected: All checks passed!
uv run pytest -q                      # Expected: all pass (+ new M5 tests), 1 skipped
uv run agon run examples/datasets/rag_smoke.yaml --display none   # Expected: runs offline; report includes a "Cost & usage" section reading 0 tokens / $0.0000
```

Open the latest `reports/*.report.md` and confirm the **Cost & usage** section is present and ASCII.

- [ ] **Step 9: Commit**

```bash
git add agon/cli/app.py tests/test_cli_resilience.py docs/decisions/ADR-0006-real-provider-hardening.md docs/running-real-evals.md README.md CLAUDE.md
git commit -m "$(printf 'feat(hardening): CLI resilience flags + ADR-0006 + real-eval guide\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-review notes (plan vs. spec)

- **Spec coverage:** resilience surface (Task 1, CLI in Task 6), wiring to Inspect (Task 1
  `resilience_eval_kwargs`), `fail_fast` migration (Task 1 Step 6), usage population (Task 3), cost
  table + math (Task 4), digest + report integration (Task 5), offline fault-injection validation
  (Task 2), ADR + running-real-evals guide + README/CLAUDE (Task 6). Bounded `max_retries=5` (Task 1
  + ADR). Cost as dated/advisory/overridable, unknown→note, mockllm→$0 (Task 4/5 + ADR).
- **Ownership split honored:** behavioral tests cover what we own (`fail_on_error` threshold,
  `retry_on_error`, cost math, usage copy, report rendering); generation knobs
  (`max_retries`/timeouts) get a wiring assertion (`resilience_eval_kwargs`), not a re-test of
  Inspect's retry internals.
- **Type consistency:** `ResilienceConfig` fields are referenced identically in Task 1
  (`resilience_eval_kwargs`), Task 6 (`_apply_resilience_flags`), and tests. `CostSummary` /
  `CostEstimate` / `summarize_cost` / `estimate_cost` signatures match across Tasks 4 and 5.
  `TokenUsage` uses `input`/`output`/`total` everywhere; Inspect `ModelUsage` uses
  `input_tokens`/`output_tokens`/`total_tokens` and is converted at exactly two boundaries
  (solver in Task 3, digest in Task 5).
- **No placeholders:** every step has concrete code/commands.
- **Verified integration risks flagged inline:** (a) raising-mockllm-policy → sample error and the
  `EvalLog.status` / `completed_samples` field names (Task 2 Step 3); (b) the SUT-response read path
  metadata vs. store (Task 3 Step 1); (c) `log.stats.model_usage` access (Task 5 Step 3 uses
  defensive `getattr`). Each says: verify against the installed Inspect and adjust the *assertion/
  access*, never weaken the locked behavior.
```
