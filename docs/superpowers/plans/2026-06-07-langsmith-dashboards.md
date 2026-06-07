# LangSmith Dashboards (Trace Enrichment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the OTel trace export with evaluation outcomes (pass/fail, scores, category, risk, M8 error taxonomy, cost, recommendation) so LangSmith and any OTel backend can chart them, then document the dashboard recipes.

**Architecture:** `export_eval_log` gains an optional `digest=` parameter; when provided it attaches run-level scalar attributes to the `invoke_workflow` span and per-sample scalars to each `invoke_agent` span (matched by `str(sample.id) == SampleRecord.test_id`). The `trace` CLI command computes `digest(log)` and passes it. Free-text string attributes are redacted (M9). A docs guide covers the LangSmith dashboard recipes.

**Tech Stack:** Python 3.12, OpenTelemetry SDK (`[otel]` extra), Inspect AI, Typer, pytest, ruff (line-length 100). No new dependencies.

**Conventions (from CLAUDE.md / HANDOFF):**
- **ASCII-only** in any `typer.echo` string. Span attribute *values* may be UTF-8 (they ride in spans, not the cp1252 console); redacted strings are ASCII regardless.
- **Targeted `git add` ONLY** — stage each task's own files. NEVER `git add .`/`-A` (the tree carries pre-existing `*.png` deletions and untracked `docs/*.docx`, `reports2/`, `HANDOFF.md`, `Training_Plan.txt`).
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- TDD: failing test first, then minimal code. Run `uv run ruff check agon tests` before each commit.
- The `[otel]` extra must be installed: `uv sync --extra otel --extra retrieval --extra semantic` (the suite expects 0 skips with these present).

---

## File Structure

- **Modify** `agon/observability/semconv.py` — add `AGON_*` outcome attribute-name constants.
- **Modify** `agon/observability/exporter.py` — `export_eval_log(log, tracer, *, digest=None)` + two outcome-attr helpers.
- **Modify** `agon/cli/app.py` — `trace` computes `digest(log)` and passes `digest=d`.
- **Create** `docs/langsmith-dashboards.md` — setup + dashboard recipes + offline walkthrough.
- **Modify** `README.md` and `CLAUDE.md` — one-line pointer to the guide.
- **Create** `docs/decisions/ADR-0011-langsmith-dashboards.md`.
- **Create test** `tests/test_observability_enrichment.py`; **extend** a CLI test for the `trace` smoke.

---

## Task 1: Span enrichment (semconv constants + exporter helpers)

**Files:**
- Modify: `agon/observability/semconv.py`
- Modify: `agon/observability/exporter.py`
- Test: `tests/test_observability_enrichment.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_observability_enrichment.py` exactly:

```python
"""Phase 3 M10 - eval-outcome enrichment of OTel spans."""

from types import SimpleNamespace as NS

import pytest

pytest.importorskip("opentelemetry.sdk")

from agon.analysis.logs import digest  # noqa: E402
from agon.observability import export_eval_log, in_memory_tracer  # noqa: E402
from agon.observability.semconv import (  # noqa: E402
    AGON_CATEGORY,
    AGON_COMPOSITE_SCORE,
    AGON_COST_TOTAL_TOKENS,
    AGON_COST_USD,
    AGON_ERROR_CATEGORY,
    AGON_ERROR_COUNT,
    AGON_N_CASES,
    AGON_OVERALL_PASS_RATE,
    AGON_PASSED,
    AGON_RECOMMENDATION,
    AGON_RISK_LEVEL,
    AGON_SYSTEM_VERSION,
)
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig  # noqa: E402
from agon.sut.contract import SUTResponse  # noqa: E402
from agon.task.builder import run_eval  # noqa: E402


async def _fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _ds(messages):
    cases = [
        AgonCase(
            test_id=tid, name=tid, category="c", input={"user_message": msg},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        )
        for tid, msg in messages.items()
    ]
    return AgonDataset(name="m10", dataset_version="v0", test_cases=cases)


def _run(tmp_path, messages, **cfg_kwargs):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"), **cfg_kwargs)
    log = run_eval(_ds(messages), cfg, callable_fn=_fn, display="none")
    return log, digest(log)


def test_run_span_carries_outcome_scalars(tmp_path):
    log, d = _run(tmp_path, {"a": "hi", "b": "hello"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert run.attributes[AGON_OVERALL_PASS_RATE] == d.overall_pass_rate
    assert run.attributes[AGON_N_CASES] == 2
    assert run.attributes[AGON_ERROR_COUNT] == 0
    assert run.attributes[AGON_RECOMMENDATION] in ("PASS", "INVESTIGATE", "FAIL")
    assert AGON_COST_USD in run.attributes
    assert AGON_COST_TOTAL_TOKENS in run.attributes


def test_sample_spans_carry_per_case_outcomes(tmp_path):
    log, d = _run(tmp_path, {"a": "hi"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    sample = next(s for s in exporter.get_finished_spans() if s.name.startswith("invoke_agent "))
    assert sample.attributes[AGON_PASSED] is True
    assert sample.attributes[AGON_COMPOSITE_SCORE] == 1.0
    assert sample.attributes[AGON_CATEGORY] == "c"
    assert sample.attributes[AGON_RISK_LEVEL] == "medium"


def test_no_digest_means_no_enrichment_backward_compat():
    ev = NS(event="score", timestamp="2026-01-01T00:00:00", scorer="agon_scorer", score=NS(value=1.0))
    sample = NS(id="s1", events=[ev])
    log = NS(
        eval=NS(run_id="r1", task="demo", model=None, created="2026-01-01T00:00:00"),
        samples=[sample],
    )
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)  # no digest -> no outcome attrs
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert AGON_OVERALL_PASS_RATE not in run.attributes
    sample_span = next(
        s for s in exporter.get_finished_spans() if s.name.startswith("invoke_agent ")
    )
    assert AGON_PASSED not in sample_span.attributes


def test_system_version_is_redacted_on_run_span(tmp_path):
    log, d = _run(tmp_path, {"a": "hi"}, system_version="build-sk-ant-ABCDEFGHIJKLMNOP1234")
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert "sk-ant-ABCDEFGHIJKLMNOP1234" not in run.attributes[AGON_SYSTEM_VERSION]
    assert "sk-ant-...1234" in run.attributes[AGON_SYSTEM_VERSION]


def test_error_taxonomy_on_run_and_sample_spans(tmp_path):
    log, d = _run(tmp_path, {"good": "hi", "bad": "boom"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    spans = exporter.get_finished_spans()
    run = next(s for s in spans if s.name.startswith("eval "))
    assert run.attributes[AGON_ERROR_COUNT] >= 1
    cat_attrs = {k: v for k, v in run.attributes.items() if k.startswith("agon.error_count.")}
    assert cat_attrs  # e.g. agon.error_count.network == 1
    bad = next(s for s in spans if s.name == "invoke_agent bad")
    assert AGON_ERROR_CATEGORY in bad.attributes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability_enrichment.py -v`
Expected: FAIL on import (`cannot import name 'AGON_PASSED'` from semconv).

- [ ] **Step 3: Add the attribute constants**

In `agon/observability/semconv.py`, append after the existing `AGON_SAMPLE_ID` line:

```python

# Agon eval-outcome attributes (M10 - dashboard enrichment)
AGON_PASSED = "agon.passed"
AGON_COMPOSITE_SCORE = "agon.composite_score"
AGON_CATEGORY = "agon.category"
AGON_RISK_LEVEL = "agon.risk_level"
AGON_ERROR_CATEGORY = "agon.error_category"
AGON_FAILURE_LABELS = "agon.failure_labels"
AGON_OVERALL_PASS_RATE = "agon.overall_pass_rate"
AGON_N_CASES = "agon.n_cases"
AGON_ERROR_COUNT = "agon.error_count"
AGON_ERROR_COUNT_PREFIX = "agon.error_count."  # + <category>
AGON_RECOMMENDATION = "agon.recommendation"
AGON_COST_USD = "agon.cost.usd"
AGON_COST_INPUT_TOKENS = "agon.cost.input_tokens"
AGON_COST_OUTPUT_TOKENS = "agon.cost.output_tokens"
AGON_COST_TOTAL_TOKENS = "agon.cost.total_tokens"
AGON_SYSTEM_VERSION = "agon.system_version"
AGON_DATASET_VERSION = "agon.dataset_version"
```

- [ ] **Step 4: Implement the enrichment in `agon/observability/exporter.py`**

(a) Extend the semconv import block to add the new names. Find the existing
`from agon.observability.semconv import (` block and add these names (keep alphabetical/grouped, ruff
will sort with `--fix`):

```python
    AGON_CATEGORY,
    AGON_COMPOSITE_SCORE,
    AGON_COST_INPUT_TOKENS,
    AGON_COST_OUTPUT_TOKENS,
    AGON_COST_TOTAL_TOKENS,
    AGON_COST_USD,
    AGON_DATASET_VERSION,
    AGON_ERROR_CATEGORY,
    AGON_ERROR_COUNT,
    AGON_ERROR_COUNT_PREFIX,
    AGON_FAILURE_LABELS,
    AGON_N_CASES,
    AGON_OVERALL_PASS_RATE,
    AGON_PASSED,
    AGON_RECOMMENDATION,
    AGON_RISK_LEVEL,
    AGON_SYSTEM_VERSION,
```

(`redact` is already imported in this file from M9.)

(b) Add the two helper functions (place them just above `def export_eval_log`):

```python
def _run_outcome_attrs(d: Any) -> dict[str, Any]:
    """Run-level scalar attributes from a RunDigest. recommendation uses default thresholds."""
    from agon.reporting.generator import recommend
    from agon.schemas import RunConfig

    cfg = RunConfig()
    rec = recommend(
        d, None, pass_threshold=cfg.pass_threshold, investigate_threshold=cfg.investigate_threshold
    )
    attrs: dict[str, Any] = {
        AGON_OVERALL_PASS_RATE: float(d.overall_pass_rate),
        AGON_N_CASES: int(d.n_cases),
        AGON_ERROR_COUNT: int(d.error_count),
        AGON_RECOMMENDATION: rec.value,
        AGON_COST_USD: float(d.cost.total_usd),
        AGON_COST_INPUT_TOKENS: int(d.cost.usage.input),
        AGON_COST_OUTPUT_TOKENS: int(d.cost.usage.output),
        AGON_COST_TOTAL_TOKENS: int(d.cost.usage.total),
    }
    for category, count in d.error_count_by_category.items():
        attrs[AGON_ERROR_COUNT_PREFIX + category] = int(count)
    if d.system_version:
        attrs[AGON_SYSTEM_VERSION] = redact(str(d.system_version))
    if d.dataset_version:
        attrs[AGON_DATASET_VERSION] = redact(str(d.dataset_version))
    return attrs


def _sample_outcome_attrs(rec: Any) -> dict[str, Any]:
    """Per-sample scalar attributes from a SampleRecord. Free-text strings are redacted."""
    attrs: dict[str, Any] = {
        AGON_PASSED: bool(rec.passed),
        AGON_COMPOSITE_SCORE: float(rec.composite_score),
        AGON_CATEGORY: redact(str(rec.category)),
        AGON_RISK_LEVEL: str(rec.risk_level),
    }
    if rec.error_category:
        attrs[AGON_ERROR_CATEGORY] = str(rec.error_category)
    if rec.detected_failure_labels:
        attrs[AGON_FAILURE_LABELS] = redact(",".join(rec.detected_failure_labels))
    return attrs
```

(c) Change the `export_eval_log` signature and wire the helpers in. The current signature is
`def export_eval_log(log: Any, tracer: Any) -> int:` — change it to:

```python
def export_eval_log(log: Any, tracer: Any, *, digest: Any = None) -> int:
```

After the `run_attrs = { ... }` dict is built (and after the `if log.eval.model:` block that may add
`GEN_AI_REQUEST_MODEL`), and BEFORE `run_span = tracer.start_span(`, insert:

```python
    if digest is not None:
        run_attrs.update(_run_outcome_attrs(digest))
    records = {r.test_id: r for r in digest.records} if digest is not None else {}
```

Then in the per-sample loop, the sample span is currently created with an inline `attributes={...}`
dict. Replace that inline dict construction so outcome attrs merge in. Change:

```python
        sample_span = tracer.start_span(
            f"invoke_agent {sample.id}",
            context=run_ctx,
            start_time=s_start,
            attributes={
                GEN_AI_OPERATION_NAME: OP_INVOKE_AGENT,
                GEN_AI_AGENT_NAME: str(sample.id),
                AGON_SAMPLE_ID: str(sample.id),
            },
        )
```

to:

```python
        sample_attrs = {
            GEN_AI_OPERATION_NAME: OP_INVOKE_AGENT,
            GEN_AI_AGENT_NAME: str(sample.id),
            AGON_SAMPLE_ID: str(sample.id),
        }
        rec = records.get(str(sample.id))
        if rec is not None:
            sample_attrs.update(_sample_outcome_attrs(rec))
        sample_span = tracer.start_span(
            f"invoke_agent {sample.id}",
            context=run_ctx,
            start_time=s_start,
            attributes=sample_attrs,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_observability_enrichment.py -v`
Expected: 5 passed.

- [ ] **Step 6: Regression — existing observability tests unchanged**

Run: `uv run pytest tests/test_observability.py -v`
Expected: all pass (they call `export_eval_log(log, tracer)` with no `digest` → unchanged behavior).

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/observability/semconv.py agon/observability/exporter.py tests/test_observability_enrichment.py
git commit -m "feat(observability): enrich run/sample spans with eval outcomes (digest=)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `trace` command passes the digest

**Files:**
- Modify: `agon/cli/app.py`
- Test: `tests/test_observability_enrichment.py` (append a CLI smoke test)

- [ ] **Step 1: Write the failing test (append to `tests/test_observability_enrichment.py`)**

```python
def test_trace_command_exports_enriched_console(tmp_path):
    from typer.testing import CliRunner

    from agon.cli import app

    runner = CliRunner()
    logs = tmp_path / "logs"
    run = runner.invoke(
        app,
        ["run", str(_FIXTURE_MINI), "--log-dir", str(logs),
         "--report-dir", str(tmp_path / "r"), "--display", "none"],
    )
    assert run.exit_code in (0, 1), run.output
    from agon.analysis import latest_run

    run_id = latest_run(str(logs)).eval.run_id
    result = runner.invoke(app, ["trace", run_id, "--log-dir", str(logs), "--backend", "console"])
    assert result.exit_code == 0, result.output
    assert "exported" in result.output
```

Also add this constant near the top of the test file (after the imports):

```python
from pathlib import Path  # noqa: E402

_FIXTURE_MINI = Path(__file__).parent / "fixtures" / "mini.yaml"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability_enrichment.py::test_trace_command_exports_enriched_console -v`
Expected: FAIL — currently the `trace` command calls `export_eval_log(log, tracer)` with no digest; the
test passes only after the digest is wired (it will still "export" but we want the digest path
exercised). To make the test meaningfully gate the change, FIRST confirm it fails by temporarily
asserting enrichment: if it already passes (console export works without digest), proceed — the real
verification of enrichment is Task 1's in-memory tests; this CLI test guards that wiring the digest
does not break the command. Expected after Step 2: the test may PASS trivially (console export already
works). That is acceptable; its purpose is regression protection for Step 3.

- [ ] **Step 3: Wire the digest into the `trace` command**

In `agon/cli/app.py`, find the top-level import `from agon.analysis import compare_runs, find_run` and
change it to include `digest`:

```python
from agon.analysis import compare_runs, digest, find_run
```

In the `trace` command body, after the `try: log = find_run(log_dir, run_id) ... except` block and
before the backend selection (`if backend == "console":`), add:

```python
    d = digest(log)
```

Then change the export call from:

```python
    count = export_eval_log(log, tracer)
```

to:

```python
    count = export_eval_log(log, tracer, digest=d)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_observability_enrichment.py -v`
Expected: 6 passed (5 from Task 1 + the CLI smoke).

- [ ] **Step 5: Regression — CLI + observability**

Run: `uv run pytest tests/test_cli.py tests/test_observability.py -q`
Expected: all pass.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/cli/app.py tests/test_observability_enrichment.py
git commit -m "feat(cli): trace computes + passes the digest for enriched spans" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Dashboard guide + ADR-0011 + pointers

**Files:**
- Create: `docs/langsmith-dashboards.md`
- Modify: `README.md`, `CLAUDE.md`
- Create: `docs/decisions/ADR-0011-langsmith-dashboards.md`

- [ ] **Step 1: Create `docs/langsmith-dashboards.md`**

````markdown
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

All values are scalars (chartable); known secret values are redacted.

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
````

- [ ] **Step 2: Add a pointer in `README.md`**

Find where the README mentions observability / OpenTelemetry (search for "OpenTelemetry" or "trace").
Add this sentence in that area (adapt to the surrounding prose; if no such section exists, add it under
the observability/traces heading):

```markdown
See [docs/langsmith-dashboards.md](docs/langsmith-dashboards.md) for building LangSmith dashboards from enriched eval traces.
```

- [ ] **Step 3: Add a pointer in `CLAUDE.md`**

In `CLAUDE.md`, find the `uv run agon trace ...` line in the Commands block and append a note after it
(or add a new bullet near it):

```markdown
uv run agon trace <run_id> --backend langsmith   # enriched spans -> LangSmith dashboards (see docs/langsmith-dashboards.md)
```

(Keep the existing `--backend console` line; this adds the langsmith/dashboard pointer.)

- [ ] **Step 4: Create `docs/decisions/ADR-0011-langsmith-dashboards.md`**

```markdown
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
   is a scalar so it is chartable.
3. **`recommendation` is computed with default thresholds at export time** (the `trace` command has no
   config). The authoritative gate remains the run's report.
4. **Free-text string attributes are redacted** (`system_version`, `dataset_version`, `failure_labels`,
   `category`) via M9's `redact()`.

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
```

- [ ] **Step 5: Commit**

```bash
git add docs/langsmith-dashboards.md docs/decisions/ADR-0011-langsmith-dashboards.md README.md CLAUDE.md
git commit -m "docs(adr): ADR-0011 + LangSmith dashboard guide; README/CLAUDE pointers" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Lint**

Run: `uv run ruff check agon tests`
Expected: `All checks passed!`

- [ ] **Step 2: Full offline suite (with extras)**

Run: `uv run pytest -q`
Expected: all passed, 0 skipped (prior 258 + 6 new M10 tests = 264). No failures.

- [ ] **Step 3: Offline enriched-trace smoke**

```bash
uv run agon run examples/datasets/rag_smoke.yaml --log-dir _m10logs --report-dir _m10reports --display none
uv run agon trace $(uv run python -c "from agon.analysis import latest_run; print(latest_run('_m10logs').eval.run_id)") --log-dir _m10logs --backend console | grep -E "agon.overall_pass_rate|agon.passed|exported" | head
rm -rf _m10logs _m10reports
```
Expected: the console span output includes `agon.overall_pass_rate` (run span) and `agon.passed`
(sample spans), and an `exported N spans to console` line.

- [ ] **Step 4: Confirm no unintended files staged**

Run: `git status --short`
Expected: only M10 files committed across Tasks 1-3; the pre-existing `*.png` deletions and untracked
`docs/*.docx`, `reports2/`, `HANDOFF.md`, `Training_Plan.txt` remain untouched and unstaged.

---

## Self-Review Notes (completed by plan author)

- **Spec coverage:** enrichment attrs (T1), `digest=` backward-compat (T1), trace wiring (T2),
  redaction of string attrs (T1 test + helpers), error-taxonomy attrs (T1), recommendation via default
  thresholds (T1 helper), dashboard guide + recipes + offline walkthrough (T3), ADR-0011 (T3),
  README/CLAUDE pointers (T3), verification (T4). All spec deliverables mapped.
- **De-risked against live code:** `str(sample.id) == SampleRecord.test_id` (verified), cost access
  `d.cost.total_usd` / `d.cost.usage.{input,output,total}` (verified), `recommend(d, None,
  pass_threshold=..., investigate_threshold=...).value` (verified), `system_version`/`dataset_version`
  propagate to the digest via the callable run path (verified), errored-run via `callable_fn=_boom_fn`
  (reused from `tests/test_taxonomy_reporting.py`).
- **Type consistency:** `export_eval_log(log, tracer, *, digest=None) -> int`;
  `_run_outcome_attrs(d) -> dict`; `_sample_outcome_attrs(rec) -> dict`; attribute constant names match
  between `semconv.py`, the exporter, and the tests.
- **ASCII:** `trace` `typer.echo` strings unchanged (ASCII); redacted string attrs are ASCII.
- **No placeholders:** every code/test step shows complete content.
