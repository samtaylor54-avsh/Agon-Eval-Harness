# Run Recovery & Error Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a partially-failed run recoverable (`agon resume`), classify every failure into a 5-category taxonomy surfaced in all reports, and let individual cases declare their own timeout.

**Architecture:** Three interlocking features on the existing Inspect-AI build. (1) A pure classifier (`agon/analysis/errors.py`) maps Inspect's structured `sample.limit` and free-text `sample.error` to `ErrorCategory`. (2) The digest layer (`agon/analysis/logs.py`) promotes pre-scoring errors to visible records (fixing a latent bug where solver/model/timeout errors vanish) and tags each record's category. (3) Resume (`agon/task/resume.py`) is harness-native — Inspect's `eval_retry` cannot reconstruct our anonymous in-process `Task` (verified), so we read the prior log, rebuild failed cases from `metadata[METADATA_CASE_KEY]`, re-run only those, and merge digests. Per-case timeout is enforced in the SUT solver via `inspect_ai.util.time_limit`, surfacing as a `timeout` the taxonomy reads.

**Tech Stack:** Python 3.12, Inspect AI, Pydantic, Typer, pytest, ruff. All offline via `mockllm` / the `callable` adapter — zero new dependencies.

**Conventions (do not skip):**
- Run everything with `uv run ...`. Lint with `uv run ruff check agon tests` (line-length 100; it auto-sorts imports).
- **Targeted `git add` ONLY** — list explicit paths in every commit. The working tree always shows unrelated `*.png` deletions and untracked `docs/*.docx`, `reports2/`, `HANDOFF.md`. NEVER `git add .` / `-A`.
- Keep CLI/`typer.echo`/`print` **output** strings ASCII (no `->` becomes `→`, no `+-`). Docstrings / markdown / jinja may be UTF-8.
- Commit message trailer (apostrophe-free body to keep bash happy):
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Branch is already `phase-3-m8-run-recovery-error-taxonomy`. Do not push / open a PR (Sam does that).

---

## Task 1: Error taxonomy classifier (pure functions)

**Files:**
- Create: `agon/analysis/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_errors.py`:

```python
"""Phase 3 M8 - per-sample error taxonomy classifier (pure functions)."""

from types import SimpleNamespace

import pytest

from agon.analysis.errors import (
    ErrorCategory,
    classify_error_text,
    classify_limit_type,
    classify_sample,
)


@pytest.mark.parametrize(
    "limit_type, expected",
    [
        ("time", ErrorCategory.TIMEOUT),
        ("working", ErrorCategory.TIMEOUT),
        ("token", ErrorCategory.RESOURCE),
        ("cost", ErrorCategory.RESOURCE),
        ("context", ErrorCategory.RESOURCE),
        ("message", ErrorCategory.RESOURCE),
        ("operator", ErrorCategory.SAMPLE),
        ("custom", ErrorCategory.SAMPLE),
    ],
)
def test_classify_limit_type(limit_type, expected):
    assert classify_limit_type(limit_type) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ConnectionError: connection refused", ErrorCategory.NETWORK),
        ("openai.APITimeoutError: request timed out", ErrorCategory.NETWORK),
        ("HTTP 429 Too Many Requests", ErrorCategory.NETWORK),
        ("HTTP 503 Service Unavailable", ErrorCategory.NETWORK),
        ("ValueError: bad case input", ErrorCategory.SAMPLE),
        ("KeyError: 'missing'", ErrorCategory.SAMPLE),
        ("", ErrorCategory.SAMPLE),
    ],
)
def test_classify_error_text(text, expected):
    assert classify_error_text(text) == expected


def test_classify_sample_prefers_limit_over_error():
    sample = SimpleNamespace(
        limit=SimpleNamespace(type="time", limit=30.0),
        error=SimpleNamespace(message="connection refused", traceback=""),
    )
    assert classify_sample(sample) == ErrorCategory.TIMEOUT


def test_classify_sample_from_error_text():
    sample = SimpleNamespace(
        limit=None,
        error=SimpleNamespace(message="ConnectionError", traceback="... connect ..."),
    )
    assert classify_sample(sample) == ErrorCategory.NETWORK


def test_classify_sample_clean_returns_none():
    assert classify_sample(SimpleNamespace(limit=None, error=None)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agon.analysis.errors'`.

- [ ] **Step 3: Write the implementation**

Create `agon/analysis/errors.py`:

```python
"""Per-sample error taxonomy (Phase 3 M8).

Classify *why* a sample failed into a small, stable category set so reports show the kind of
failure, not just a count. Inspect persists structured limit info (``sample.limit``) but only
free text for errors (``sample.error.message``/``traceback``), so network-vs-sample is
best-effort string matching; anything unrecognized falls to ``sample``.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    NETWORK = "network"
    SCORER = "scorer"
    SAMPLE = "sample"


# inspect EvalSampleLimit.type is one of: context, time, working, message, token, cost,
# operator, custom. Wall-clock ones -> TIMEOUT; budget ones -> RESOURCE; rest -> SAMPLE.
_TIMEOUT_LIMITS = frozenset({"time", "working"})
_RESOURCE_LIMITS = frozenset({"token", "cost", "context", "message"})

# Best-effort transport/provider failure markers in an error message + traceback.
_NETWORK_MARKERS = re.compile(
    r"(connection|connect\b|timeout|timed out|rate.?limit|\b429\b|\b50\d\b|"
    r"bad gateway|service unavailable|apierror|apiconnection|apitimeout|"
    r"readtimeout|econnreset|broken pipe|\bssl\b)",
    re.IGNORECASE,
)


def classify_limit_type(limit_type: str) -> ErrorCategory:
    """Map an inspect ``EvalSampleLimit.type`` to a category."""
    if limit_type in _TIMEOUT_LIMITS:
        return ErrorCategory.TIMEOUT
    if limit_type in _RESOURCE_LIMITS:
        return ErrorCategory.RESOURCE
    return ErrorCategory.SAMPLE  # operator / custom -> generic


def classify_error_text(text: str) -> ErrorCategory:
    """Best-effort: NETWORK if transport markers are present, else SAMPLE."""
    return ErrorCategory.NETWORK if _NETWORK_MARKERS.search(text or "") else ErrorCategory.SAMPLE


def classify_sample(sample: Any) -> ErrorCategory | None:
    """Classify a sample's pre-scoring failure, or ``None`` if it did not error/limit.

    Precedence: a structured ``sample.limit`` wins (timeout/resource); otherwise a
    ``sample.error`` is classified from its text. Scorer errors are NOT handled here -- they
    live in scorer metadata and are tagged ``scorer`` by the digest layer.
    """
    limit = getattr(sample, "limit", None)
    if limit is not None:
        return classify_limit_type(limit.type)
    error = getattr(sample, "error", None)
    if error is not None:
        text = f"{getattr(error, 'message', '')} {getattr(error, 'traceback', '')}"
        return classify_error_text(text)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_errors.py -q`
Expected: PASS (all parametrized cases green).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check agon/analysis/errors.py tests/test_errors.py
git add agon/analysis/errors.py tests/test_errors.py
git commit -m "$(printf 'feat(taxonomy): ErrorCategory classifier for sample limits and errors\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Promote and categorize errors in the digest

This fixes a latent bug: a sample that errors in the solver (model/SUT/timeout) never reaches the scorer, so today it is **absent** from the digest entirely (`error_count` reads 0). We promote such samples to visible records and tag every record with `error_category`.

**Files:**
- Modify: `agon/analysis/logs.py`
- Test: `tests/test_error_taxonomy.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_error_taxonomy.py`:

```python
"""Phase 3 M8 - error visibility + categorization in the digest."""

from agon.analysis.logs import _record_from_score, digest
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval


def test_record_from_score_tags_scorer_error():
    rec = _record_from_score("t1", 0.0, {"errored": True, "category": "c", "risk_level": "low"})
    assert rec.errored is True
    assert rec.error_category == "scorer"


def test_record_from_score_clean_has_no_category():
    rec = _record_from_score("t1", 1.0, {"category": "c"})
    assert rec.errored is False
    assert rec.error_category is None


async def _boom_fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _two_case_ds():
    cases = [
        AgonCase(
            test_id="good", name="good", category="c", input={"user_message": "hi"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
        AgonCase(
            test_id="bad", name="bad", category="c", input={"user_message": "boom"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
    ]
    return AgonDataset(name="tax", dataset_version="v0", test_cases=cases)


def test_solver_error_is_visible_and_categorized(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_two_case_ds(), cfg, callable_fn=_boom_fn, display="none")
    d = digest(log)
    assert {r.test_id for r in d.records} == {"good", "bad"}  # "bad" no longer vanishes
    bad = d.record_map()["bad"]
    assert bad.errored is True
    assert bad.error_category == "network"
    assert d.error_count == 1
    assert d.error_count_by_category == {"network": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_error_taxonomy.py -q`
Expected: FAIL — `_record_from_score` does not exist (ImportError) and/or `error_count_by_category` missing.

- [ ] **Step 3: Add the new schema fields**

In `agon/analysis/logs.py`, add `error_category` to `SampleRecord` (after the `errored` field, ~line 36):

```python
    errored: bool = False
    error_category: str | None = None
```

And add `error_count_by_category` to `RunDigest` (immediately after `error_count: int`, ~line 53):

```python
    error_count: int
    error_count_by_category: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Add the import**

At the top of `agon/analysis/logs.py`, add (ruff will order it):

```python
from agon.analysis.errors import ErrorCategory, classify_sample
```

- [ ] **Step 5: Refactor record-building into testable helpers**

Replace the existing `sample_records` function (the whole `def sample_records(log): ...` block, ~lines 86-102) with:

```python
def _record_from_score(test_id: str, value: Any, meta: dict[str, Any]) -> SampleRecord:
    """Build a SampleRecord from a scored sample's (value, scorer-metadata)."""
    passed = float(value) >= 0.5
    scorer_errored = bool(meta.get("errored", False))
    return SampleRecord(
        test_id=test_id,
        passed=passed,
        composite_score=float(meta.get("composite_score", 1.0 if passed else 0.0)),
        category=str(meta.get("category", "uncategorized")),
        risk_level=str(meta.get("risk_level", "medium")),
        detected_failure_labels=list(meta.get("detected_failure_labels", [])),
        retrieval_scores=dict(meta.get("retrieval_scores", {})),
        errored=scorer_errored,
        error_category=ErrorCategory.SCORER.value if scorer_errored else None,
    )


def _errored_samples(log: EvalLog, scored_ids: set[str]) -> list[SampleRecord]:
    """Promote samples that errored/limited *before* scoring (no AGON_SCORER score, so absent
    from the scored records) into visible, categorized records. Without this, model/SUT/timeout
    errors silently vanish from the digest.
    """
    records: list[SampleRecord] = []
    seen: set[str] = set()
    for sample in log.samples or []:
        sid = str(sample.id)
        if sid in scored_ids or sid in seen:
            continue
        category = classify_sample(sample)
        if category is None:
            continue
        seen.add(sid)
        meta = sample.metadata or {}
        records.append(
            SampleRecord(
                test_id=sid,
                passed=False,
                composite_score=0.0,
                category=str(meta.get("category", "uncategorized")),
                risk_level=str(meta.get("risk_level", "medium")),
                errored=True,
                error_category=category.value,
            )
        )
    return records


def sample_records(log: EvalLog) -> list[SampleRecord]:
    scored = list(_reduced_samples(log))
    records = [_record_from_score(tid, value, meta) for tid, value, meta in scored]
    scored_ids = {tid for tid, _v, _m in scored}
    records.extend(_errored_samples(log, scored_ids))
    return records
```

- [ ] **Step 6: Extract `build_digest` and aggregate the categories**

Replace the existing `def digest(log): ...` block (~lines 109-157) with this pair (a reusable `build_digest` plus a thin `digest`):

```python
def build_digest(
    records: list[SampleRecord],
    *,
    run_id: str,
    task: str,
    model: str | None,
    system_version: str,
    dataset_version: str,
    created: str,
    cost: CostSummary,
) -> RunDigest:
    """Compute a RunDigest from a record set (shared by digest() and resume merge)."""
    total = len(records)
    passed = sum(1 for r in records if r.passed)

    cat_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    risk_pass: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    label_counter: Counter[str] = Counter()
    error_by_cat: Counter[str] = Counter()
    for r in records:
        cat_pass[r.category][0] += int(r.passed)
        cat_pass[r.category][1] += 1
        risk_pass[r.risk_level][0] += int(r.passed)
        risk_pass[r.risk_level][1] += 1
        if not r.passed:
            label_counter.update(r.detected_failure_labels)
        if r.error_category:
            error_by_cat[r.error_category] += 1

    overall_pass_ci = wilson_interval(passed, total)
    pass_ci_by_category = {k: wilson_interval(v[0], v[1]) for k, v in sorted(cat_pass.items())}

    return RunDigest(
        run_id=run_id,
        task=task,
        model=model,
        system_version=system_version,
        dataset_version=dataset_version,
        created=created,
        records=records,
        overall_pass_rate=_rate(passed, total),
        pass_rate_by_category={k: _rate(v[0], v[1]) for k, v in sorted(cat_pass.items())},
        pass_rate_by_risk={k: _rate(v[0], v[1]) for k, v in sorted(risk_pass.items())},
        top_failure_labels=label_counter.most_common(),
        error_count=sum(1 for r in records if r.errored),
        error_count_by_category=dict(error_by_cat),
        cost=cost,
        n_cases=total,
        overall_pass_ci=overall_pass_ci,
        pass_ci_by_category=pass_ci_by_category,
        small_sample=is_small_sample(total),
    )


def digest(log: EvalLog) -> RunDigest:
    records = sample_records(log)

    stats = getattr(log, "stats", None)
    model_usage = getattr(stats, "model_usage", {}) or {}
    usage_by_model = {
        model_name: TokenUsage(
            input=mu.input_tokens, output=mu.output_tokens, total=mu.total_tokens
        )
        for model_name, mu in model_usage.items()
    }
    cost = summarize_cost(usage_by_model)

    meta = log.eval.metadata or {}
    return build_digest(
        records,
        run_id=log.eval.run_id,
        task=log.eval.task,
        model=log.eval.model,
        system_version=str(meta.get("system_version", "unversioned")),
        dataset_version=str(meta.get("dataset_version", "")),
        created=log.eval.created or "",
        cost=cost,
    )
```

- [ ] **Step 7: Run the new test + the full suite (watch for regressions)**

Run: `uv run pytest tests/test_error_taxonomy.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass (the refactor preserves `digest()` output; `make_digest` test helpers pass `error_count` explicitly so the new defaulted field is fine).

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check agon/analysis/logs.py tests/test_error_taxonomy.py
git add agon/analysis/logs.py tests/test_error_taxonomy.py
git commit -m "$(printf 'feat(taxonomy): promote pre-scoring errors to visible categorized records\n\nFixes a latent bug where solver/model/timeout errors vanished from the\ndigest. Adds SampleRecord.error_category and RunDigest.error_count_by_category.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Surface the taxonomy in all report formats

**Files:**
- Modify: `agon/reporting/generator.py`
- Modify: `agon/reporting/templates/report.md.jinja2`
- Test: `tests/test_taxonomy_reporting.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_taxonomy_reporting.py`:

```python
"""Phase 3 M8 - error taxonomy in markdown / json / junit reports."""

import json

from agon.analysis.logs import digest
from agon.reporting.generator import render_json, render_markdown, render_junit_xml
from agon.schemas import AgonCase, AgonDataset, Recommendation, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval


async def _boom_fn(req):
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
    return AgonDataset(name="tax", dataset_version="v0", test_cases=cases)


def _digest_with_error(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds({"good": "hi", "bad": "boom"}), cfg, callable_fn=_boom_fn, display="none")
    return digest(log)


def _digest_clean(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds({"good": "hi"}), cfg, callable_fn=_boom_fn, display="none")
    return digest(log)


def test_json_has_error_by_category(tmp_path):
    d = _digest_with_error(tmp_path)
    payload = json.loads(render_json(d, None, Recommendation.FAIL))
    assert payload["error_count_by_category"] == {"network": 1}


def test_markdown_breakdown_present_when_errors(tmp_path):
    d = _digest_with_error(tmp_path)
    md = render_markdown(d, None, Recommendation.FAIL)
    assert "Errors by category" in md
    assert "network: 1" in md


def test_markdown_breakdown_absent_when_clean(tmp_path):
    d = _digest_clean(tmp_path)
    md = render_markdown(d, None, Recommendation.PASS)
    assert "Errors by category" not in md


def test_junit_error_message_uses_category(tmp_path):
    d = _digest_with_error(tmp_path)
    xml = render_junit_xml(d)
    assert 'message="network"' in xml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_taxonomy_reporting.py -q`
Expected: FAIL (`error_count_by_category` not in JSON; markdown section missing; junit message is `"scorer error"`).

- [ ] **Step 3: Add the JSON field**

In `agon/reporting/generator.py`, in `render_json`'s payload dict, add the line directly after `"error_count": d.error_count,` (~line 98):

```python
        "error_count": d.error_count,
        "error_count_by_category": d.error_count_by_category,
```

- [ ] **Step 4: Use the category in JUnit and fix the failures count**

In `render_junit_xml`, change the `testsuite` `failures=` attribute and the per-case `errored` branch. Replace the `failures=` line (~line 112) so errored cases are not double-counted as failures:

```python
        failures=str(sum(1 for r in d.records if not r.passed and not r.errored)),
```

Replace the `if r.errored:` block (~lines 119-121) with:

```python
        if r.errored:
            err = ET.SubElement(case, "error", message=r.error_category or "error")
            err.text = ", ".join(r.detected_failure_labels)
```

- [ ] **Step 5: Add the markdown breakdown section**

In `agon/reporting/templates/report.md.jinja2`, insert this block immediately after the "Top failure modes" block (after line 25, the `{% endif %}` that closes `top_failure_labels`, and before the `{% if regression %}` line):

```jinja
{% if d.error_count_by_category %}## Errors by category
{% for cat, count in d.error_count_by_category.items() %}- {{ cat }}: {{ count }}
{% endfor %}{% endif %}
```

- [ ] **Step 6: Run the new test + full suite**

Run: `uv run pytest tests/test_taxonomy_reporting.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check agon/reporting/generator.py tests/test_taxonomy_reporting.py
git add agon/reporting/generator.py agon/reporting/templates/report.md.jinja2 tests/test_taxonomy_reporting.py
git commit -m "$(printf 'feat(reporting): surface error_count_by_category in md/json/junit\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: Per-case timeout overrides (solver-enforced)

Move per-sample time-limit enforcement out of `eval()`'s global `time_limit` kwarg and into the SUT solver, so a case can override the global default. A breach raises `LimitExceededError`, surfaces as `sample.limit(type="time")`, and is classified `timeout` by Task 1/2.

**Files:**
- Modify: `agon/schemas/models.py` (add `AgonCase.sample_time_limit`)
- Modify: `agon/sut/solvers.py` (enforce per-sample limit)
- Modify: `agon/task/builder.py` (pass global default to solver; stop sending eval-level `time_limit`)
- Modify: `tests/test_resilience.py` (update the now-obsolete `time_limit` kwarg assertion)
- Test: `tests/test_per_case_timeout.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_per_case_timeout.py`:

```python
"""Phase 3 M8 - per-case timeout overrides, enforced in the SUT solver."""

import asyncio

from agon.analysis.logs import digest
from agon.schemas import (
    AgonCase,
    AgonDataset,
    ResilienceConfig,
    RunConfig,
    ScoringSpec,
    SUTConfig,
)
from agon.sut.contract import SUTResponse
from agon.task.builder import resilience_eval_kwargs, run_eval


async def _slow_fn(req):
    await asyncio.sleep(3)
    return SUTResponse(final_answer="the answer")


def _case(tid, msg, time_limit=None):
    return AgonCase(
        test_id=tid, name=tid, category="c", input={"user_message": msg},
        expected={"expected_answer": "the answer"},
        scoring=[ScoringSpec(type="exact_match")], sample_time_limit=time_limit,
    )


def test_schema_accepts_per_case_time_limit():
    assert _case("x", "hi", time_limit=5).sample_time_limit == 5


def test_eval_kwargs_no_longer_sets_global_time_limit():
    cfg = RunConfig(resilience=ResilienceConfig(sample_time_limit=30))
    assert "time_limit" not in resilience_eval_kwargs(cfg)


def test_per_case_timeout_trips_and_is_categorized(tmp_path):
    ds = AgonDataset(name="t", dataset_version="v0", test_cases=[_case("slow", "hi", time_limit=1)])
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(ds, cfg, callable_fn=_slow_fn, display="none")
    d = digest(log)
    rec = d.record_map()["slow"]
    assert rec.errored is True
    assert rec.error_category == "timeout"
    assert d.error_count_by_category == {"timeout": 1}


def test_global_default_applies_without_per_case_override(tmp_path):
    ds = AgonDataset(name="t", dataset_version="v0", test_cases=[_case("slow", "hi")])
    cfg = RunConfig(
        log_dir=str(tmp_path),
        sut=SUTConfig(adapter="callable"),
        resilience=ResilienceConfig(sample_time_limit=1),
    )
    log = run_eval(ds, cfg, callable_fn=_slow_fn, display="none")
    assert digest(log).record_map()["slow"].error_category == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_per_case_timeout.py -q`
Expected: FAIL — `AgonCase` rejects `sample_time_limit` (extra="forbid"); and `resilience_eval_kwargs` still sets `time_limit`.

- [ ] **Step 3: Add the schema field**

In `agon/schemas/models.py`, in `AgonCase`, add the field directly after the `repetitions` line (~line 112):

```python
    repetitions: int | None = Field(default=None, ge=1)  # overrides RunConfig.epochs
    sample_time_limit: int | None = Field(default=None, ge=1)  # per-case wall-clock cap (s)
```

- [ ] **Step 4: Enforce the limit in the solvers**

In `agon/sut/solvers.py`, add imports near the top (ruff will order them):

```python
from contextlib import AbstractContextManager, nullcontext

from inspect_ai.util import time_limit

from agon.dataset import METADATA_CASE_KEY
```

Add this helper after the `_attach` function (~line 47):

```python
def _time_limit_ctx(state: TaskState, default_time_limit: float | None) -> AbstractContextManager:
    """Per-sample wall-clock guard: the case's override wins, else the run-level default.

    A breach raises inspect's LimitExceededError, which surfaces as sample.limit(type="time").
    """
    case = (state.metadata or {}).get(METADATA_CASE_KEY) or {}
    effective = case.get("sample_time_limit") or default_time_limit
    return time_limit(effective) if effective else nullcontext()
```

Change the three solver factories to accept `default_time_limit` and wrap their SUT call.

`agon_generate_solver` (replace its signature + the `state = await generate(state)` line):

```python
@solver
def agon_generate_solver(default_time_limit: float | None = None) -> Solver:
    """Default solver: generate with the configured model, then normalize the output."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        with _time_limit_ctx(state, default_time_limit):
            state = await generate(state)
        usage = getattr(state.output, "usage", None)
```

`callable_solver` (replace its signature + the `response = await fn(request)` line):

```python
@solver
def callable_solver(fn: SUTCallable, default_time_limit: float | None = None) -> Solver:
    """Wrap an in-process async callable as the SUT."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        request = _build_request(state)
        with _time_limit_ctx(state, default_time_limit):
            response = await fn(request)
        if not response.trace_id:
```

`http_solver` (replace its signature + wrap the request/response block). Change the signature line and wrap from `async with httpx...` through `payload = resp.json()`:

```python
@solver
def http_solver(config: SUTConfig, default_time_limit: float | None = None) -> Solver:
    """POST the normalized request to an external service and field-map the response."""

    if not config.endpoint_url:
        raise ValueError("http adapter requires endpoint_url")

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        import httpx  # transitive dep via inspect-ai; imported lazily (opt-in path)

        request = _build_request(state)
        with _time_limit_ctx(state, default_time_limit):
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    config.endpoint_url,
                    json=request.model_dump(),
                    headers=config.headers,
                )
                resp.raise_for_status()
                payload = resp.json()
        response = map_http_response(payload, config.field_map)
```

Update `build_solver` to thread the default through (replace the whole function body):

```python
def build_solver(
    config: SUTConfig,
    *,
    callable_fn: SUTCallable | None = None,
    default_time_limit: float | None = None,
) -> Solver:
    """Construct the solver for a given SUT configuration."""
    adapter = config.adapter
    if adapter in ("mockllm", "litellm"):
        return agon_generate_solver(default_time_limit)
    if adapter == "callable":
        if callable_fn is None:
            raise ValueError("callable adapter requires a callable_fn")
        return callable_solver(callable_fn, default_time_limit)
    if adapter == "http":
        return http_solver(config, default_time_limit)
    raise ValueError(f"unknown SUT adapter: {adapter!r}")
```

- [ ] **Step 5: Wire the default in the task builder and stop sending eval-level `time_limit`**

In `agon/task/builder.py`, in `resilience_eval_kwargs`, delete the three lines that set `kwargs["time_limit"]` from `r.sample_time_limit` (~lines 37-38) and replace the trailing comment so the function ends:

```python
    if r.request_timeout is not None:
        kwargs["timeout"] = r.request_timeout
    if r.attempt_timeout is not None:
        kwargs["attempt_timeout"] = r.attempt_timeout
    # sample_time_limit is enforced per-sample in the solver (so per-case overrides win),
    # not via eval()'s global time_limit.
    return kwargs
```

In `agon_task`, pass the default into `build_solver` (replace the `solver = build_solver(...)` line, ~line 64):

```python
    solver = build_solver(
        config.sut,
        callable_fn=callable_fn,
        default_time_limit=config.resilience.sample_time_limit,
    )
```

- [ ] **Step 6: Update the obsolete resilience kwarg test**

In `tests/test_resilience.py`, in `test_eval_kwargs_full`, the run now enforces `sample_time_limit` in the solver, so it is no longer an eval kwarg. Replace the assertion line `assert kwargs["time_limit"] == 30` with:

```python
    assert "time_limit" not in kwargs  # sample_time_limit is solver-enforced (M8), not an eval kwarg
```

- [ ] **Step 7: Run the new test + full suite**

Run: `uv run pytest tests/test_per_case_timeout.py tests/test_resilience.py -q`
Expected: PASS (timeout test takes ~1s due to the 1s limit).

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check agon/schemas/models.py agon/sut/solvers.py agon/task/builder.py tests/test_per_case_timeout.py tests/test_resilience.py
git add agon/schemas/models.py agon/sut/solvers.py agon/task/builder.py tests/test_per_case_timeout.py tests/test_resilience.py
git commit -m "$(printf 'feat(timeout): per-case sample_time_limit enforced in the SUT solver\n\nMoves time-limit enforcement out of eval() global time_limit so per-case\noverrides win; breaches surface as sample.limit(time) -> timeout category.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Resume building blocks

Pure-ish helpers for harness-native resume. No CLI yet.

**Files:**
- Create: `agon/task/resume.py`
- Test: `tests/test_resume_units.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_resume_units.py`:

```python
"""Phase 3 M8 - resume building blocks (select / reconstruct / merge)."""

from agon.analysis.logs import SampleRecord, build_digest, digest
from agon.cost import CostSummary
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval
from agon.task.resume import cases_from_log, merge_digests, select_incomplete


async def _boom_fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _ds():
    cases = [
        AgonCase(
            test_id="good", name="good", category="c", input={"user_message": "hi"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
        AgonCase(
            test_id="bad", name="bad", category="c", input={"user_message": "boom"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
    ]
    return AgonDataset(name="resume_suite", dataset_version="v0", test_cases=cases)


def _record(test_id, passed, errored=False, category=None):
    return SampleRecord(
        test_id=test_id, passed=passed, composite_score=1.0 if passed else 0.0,
        category="c", risk_level="medium", errored=errored, error_category=category,
    )


def test_select_incomplete_picks_only_errored(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds(), cfg, callable_fn=_boom_fn, display="none")
    incomplete = select_incomplete(log)
    assert [str(s.id) for s in incomplete] == ["bad"]


def test_cases_from_log_rebuilds_failed_cases(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds(), cfg, callable_fn=_boom_fn, display="none")
    sub = cases_from_log(log, select_incomplete(log))
    assert [c.test_id for c in sub.test_cases] == ["bad"]


def test_merge_digests_prefers_rerun_and_recomputes():
    prior = build_digest(
        [_record("good", True), _record("bad", False, errored=True, category="network")],
        run_id="r0", task="t", model="m", system_version="v", dataset_version="d",
        created="t0", cost=CostSummary(),
    )
    rerun = build_digest(
        [_record("bad", True)],
        run_id="r1", task="t", model="m", system_version="v", dataset_version="d",
        created="t1", cost=CostSummary(),
    )
    merged = merge_digests(prior, rerun)
    assert merged.run_id == "r1"
    assert merged.record_map()["bad"].passed is True
    assert merged.overall_pass_rate == 1.0
    assert merged.error_count == 0
    assert merged.error_count_by_category == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume_units.py -q`
Expected: FAIL — `agon.task.resume` does not exist.

- [ ] **Step 3: Write the implementation**

Create `agon/task/resume.py`:

```python
"""Harness-native run recovery (Phase 3 M8).

Inspect's ``eval_retry`` cannot reconstruct our anonymous in-process ``Task`` (it looks the
task up in the registry by name and fails), so resume is implemented here: read a prior log,
select the incomplete samples, rebuild their ``AgonCase``s from ``metadata[METADATA_CASE_KEY]``,
re-run just those, and merge with the prior run's already-passing records.
"""

from __future__ import annotations

from inspect_ai.log import EvalLog, EvalSample

from agon.analysis.logs import AGON_SCORER, RunDigest, SampleRecord, build_digest
from agon.dataset import METADATA_CASE_KEY
from agon.schemas import AgonCase, AgonDataset


def select_incomplete(log: EvalLog) -> list[EvalSample]:
    """Samples that did not finish with a clean score: errored, hit a limit, unscored, or
    scored with a scorer error.
    """
    out: list[EvalSample] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get(AGON_SCORER)
        scorer_errored = bool(score.metadata.get("errored")) if score is not None else False
        if sample.error is not None or sample.limit is not None or score is None or scorer_errored:
            out.append(sample)
    return out


def cases_from_log(log: EvalLog, samples: list[EvalSample]) -> AgonDataset:
    """Rebuild an AgonDataset from the cases embedded in the given samples' metadata."""
    cases: list[AgonCase] = []
    seen: set[str] = set()
    for sample in samples:
        dump = (sample.metadata or {}).get(METADATA_CASE_KEY)
        if dump is None:
            continue
        case = AgonCase.model_validate(dump)
        if case.test_id in seen:
            continue
        seen.add(case.test_id)
        cases.append(case)
    meta = log.eval.metadata or {}
    version = str(meta.get("dataset_version", "")) or "resume"
    return AgonDataset(name=f"{log.eval.task}__resume", dataset_version=version, test_cases=cases)


def merge_digests(prior: RunDigest, rerun: RunDigest) -> RunDigest:
    """Merge a prior run's records with a re-run, preferring the re-run per test_id.

    Aggregates are recomputed from the merged record set. Cost reflects the re-run only
    (the work resume actually performed).
    """
    by_id: dict[str, SampleRecord] = {r.test_id: r for r in prior.records}
    for r in rerun.records:
        by_id[r.test_id] = r
    return build_digest(
        list(by_id.values()),
        run_id=rerun.run_id,
        task=prior.task,
        model=prior.model,
        system_version=prior.system_version,
        dataset_version=prior.dataset_version,
        created=rerun.created,
        cost=rerun.cost,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resume_units.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check agon/task/resume.py tests/test_resume_units.py
git add agon/task/resume.py tests/test_resume_units.py
git commit -m "$(printf 'feat(resume): select/reconstruct/merge building blocks for run recovery\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: Resume orchestrator + `agon resume` CLI command

**Files:**
- Modify: `agon/task/resume.py` (add `resume_run`)
- Modify: `agon/cli/app.py` (add the `resume` command)
- Test: `tests/test_resume.py` (create)
- Test: `tests/test_cli_resume.py` (create)

- [ ] **Step 1: Write the failing test (orchestrator)**

Create `tests/test_resume.py`:

```python
"""Phase 3 M8 - resume orchestrator (end to end, offline via the callable adapter)."""

from agon.analysis.logs import digest
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval
from agon.task.resume import resume_run


async def _failing(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


async def _healthy(req):
    return SUTResponse(final_answer="the answer")


def _ds():
    cases = [
        AgonCase(
            test_id="good", name="good", category="c", input={"user_message": "hi"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
        AgonCase(
            test_id="bad", name="bad", category="c", input={"user_message": "boom"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
    ]
    return AgonDataset(name="resume_suite", dataset_version="v0", test_cases=cases)


def _cfg(tmp_path):
    return RunConfig(
        log_dir=str(tmp_path),
        report_dir=str(tmp_path / "reports"),
        sut=SUTConfig(adapter="callable"),
    )


def test_resume_recovers_errored_case(tmp_path):
    cfg = _cfg(tmp_path)
    first = run_eval(_ds(), cfg, callable_fn=_failing, display="none")
    assert digest(first).record_map()["bad"].errored is True
    run_id = first.eval.run_id

    result = resume_run(cfg, run_id, callable_fn=_healthy, display="none")
    assert result["resumed"] == 1
    merged = result["digest"]
    assert merged.record_map()["bad"].passed is True   # recovered
    assert merged.record_map()["good"].passed is True   # carried over from the prior run
    assert merged.error_count == 0
    assert merged.run_id != run_id
    assert result["written"]  # merged report files were written


def test_resume_latest_when_no_run_id(tmp_path):
    cfg = _cfg(tmp_path)
    run_eval(_ds(), cfg, callable_fn=_failing, display="none")
    result = resume_run(cfg, None, callable_fn=_healthy, display="none")
    assert result["resumed"] == 1
    assert result["digest"].record_map()["bad"].passed is True


def test_resume_nothing_to_resume(tmp_path):
    cfg = _cfg(tmp_path)
    run_eval(_ds(), cfg, callable_fn=_healthy, display="none")  # all complete
    result = resume_run(cfg, None, callable_fn=_healthy, display="none")
    assert result["resumed"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume.py -q`
Expected: FAIL — `resume_run` does not exist.

- [ ] **Step 3: Implement the orchestrator**

First, replace the **entire top import block** of `agon/task/resume.py` (everything from the first `from inspect_ai...` through `from agon.schemas import AgonCase, AgonDataset`) with this single consolidated block:

```python
from pathlib import Path

from inspect_ai.log import EvalLog, EvalSample

from agon.analysis.logs import (
    AGON_SCORER,
    RunDigest,
    SampleRecord,
    build_digest,
    digest,
    find_run,
    latest_run,
)
from agon.analysis.regression import compare_digests
from agon.dataset import METADATA_CASE_KEY
from agon.reporting.generator import recommend, render_json, render_junit_xml, render_markdown
from agon.schemas import AgonCase, AgonDataset, RunConfig
from agon.sut.solvers import SUTCallable
from agon.task.builder import run_eval
```

Then add the function at the end of the file:

```python
def resume_run(
    cfg: RunConfig,
    run_id: str | None,
    *,
    callable_fn: SUTCallable | None = None,
    display: str = "none",
) -> dict:
    """Re-run a prior run's incomplete cases and write a merged report.

    ``run_id=None`` resumes the most recent run in ``cfg.log_dir``. Returns a dict with
    ``resumed`` (count), the merged ``digest``, the ``regression`` vs the prior run, the
    ``recommendation``, the rendered ``artifacts``, and ``written`` paths.
    """
    prior = find_run(cfg.log_dir, run_id) if run_id else latest_run(cfg.log_dir)
    prior_digest = digest(prior)

    incomplete = select_incomplete(prior)
    if not incomplete:
        rec = recommend(
            prior_digest,
            None,
            pass_threshold=cfg.pass_threshold,
            investigate_threshold=cfg.investigate_threshold,
        )
        return {
            "resumed": 0,
            "digest": prior_digest,
            "regression": None,
            "recommendation": rec,
            "artifacts": {},
            "written": {},
        }

    sub = cases_from_log(prior, incomplete)
    new_log = run_eval(sub, cfg, callable_fn=callable_fn, display=display)
    rerun_digest = digest(new_log)
    merged = merge_digests(prior_digest, rerun_digest)

    regression = compare_digests(merged, prior_digest)
    recommendation = recommend(
        merged,
        regression,
        pass_threshold=cfg.pass_threshold,
        investigate_threshold=cfg.investigate_threshold,
    )
    artifacts = {
        "report.md": render_markdown(merged, regression, recommendation),
        "report.json": render_json(merged, regression, recommendation),
        "report.junit.xml": render_junit_xml(merged),
    }
    written: dict[str, str] = {}
    if cfg.report_dir:
        out = Path(cfg.report_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            path = out / f"{merged.run_id}.{name}"
            path.write_text(content, encoding="utf-8")
            written[name] = str(path)
    return {
        "resumed": len(incomplete),
        "digest": merged,
        "regression": regression,
        "recommendation": recommendation,
        "artifacts": artifacts,
        "written": written,
    }
```

- [ ] **Step 4: Run the orchestrator test**

Run: `uv run pytest tests/test_resume.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing CLI test**

Create `tests/test_cli_resume.py`:

```python
"""Phase 3 M8 - `agon resume` CLI wiring (offline)."""

from typer.testing import CliRunner

from agon.cli.app import app

runner = CliRunner()


def test_cli_resume_nothing_to_resume(tmp_path):
    log_dir = str(tmp_path / "logs")
    report_dir = str(tmp_path / "reports")
    # A clean mockllm run: cases pass/fail by score but none error -> nothing to resume.
    runner.invoke(
        app,
        ["run", "examples/datasets/rag_smoke.yaml", "--log-dir", log_dir,
         "--report-dir", report_dir, "--display", "none"],
    )
    result = runner.invoke(
        app,
        ["resume", "--latest", "--log-dir", log_dir, "--report-dir", report_dir, "--display", "none"],
    )
    assert result.exit_code == 0
    assert "nothing to resume" in result.output


def test_cli_resume_unknown_run_id_aborts(tmp_path):
    result = runner.invoke(
        app, ["resume", "nope", "--log-dir", str(tmp_path), "--display", "none"]
    )
    assert result.exit_code == 2
    assert "[abort]" in result.output
```

- [ ] **Step 6: Run CLI test to verify it fails**

Run: `uv run pytest tests/test_cli_resume.py -q`
Expected: FAIL — no `resume` command on the Typer app.

- [ ] **Step 7: Add the CLI command**

In `agon/cli/app.py`, update the module docstring command list (line 3) to include `resume`:

```python
Commands: ``run``, ``resume``, ``compare``, ``report``, ``review``, ``calibrate``.
```

Add this command after the `run` command (after its closing, ~line 197), before `compare`:

```python
@app.command()
def resume(
    run_id: str = typer.Argument(None, help="Run id to resume (default: latest in --log-dir)"),
    config: str = typer.Option(None, "--config", "-c", help="Run config (.toml/.yaml/.json)"),
    log_dir: str = typer.Option(None, "--log-dir"),
    report_dir: str = typer.Option(None, "--report-dir"),
    display: str = typer.Option("plain", "--display", help="Inspect display: plain|rich|none"),
    latest: bool = typer.Option(False, "--latest", help="Resume the most recent run"),
    max_retries: int = typer.Option(None, "--max-retries", help="Per-request retry count"),
    request_timeout: int = typer.Option(None, "--request-timeout", help="Whole-request timeout (s)"),
    attempt_timeout: int = typer.Option(None, "--attempt-timeout", help="Per-attempt timeout (s)"),
    retry_on_error: int = typer.Option(None, "--retry-on-error", help="Per-sample retry count"),
    sample_time_limit: int = typer.Option(None, "--sample-time-limit", help="Per-sample time limit (s)"),
    fail_on_error: str = typer.Option(None, "--fail-on-error", help="true|false or error-rate 0..1"),
) -> None:
    """Re-run the failed/incomplete cases of a prior run and emit a merged report."""
    from agon.task.resume import resume_run

    cfg = load_run_config(config) if config else RunConfig()
    if log_dir:
        cfg.log_dir = log_dir
    if report_dir:
        cfg.report_dir = report_dir

    try:
        _apply_resilience_flags(
            cfg,
            max_retries=max_retries,
            request_timeout=request_timeout,
            attempt_timeout=attempt_timeout,
            retry_on_error=retry_on_error,
            sample_time_limit=sample_time_limit,
            fail_on_error=fail_on_error,
        )
    except (ValueError, ValidationError) as exc:
        typer.echo(f"[abort] invalid resilience flag: {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    target = None if latest else run_id
    try:
        result = resume_run(cfg, target, display=display)
    except FileNotFoundError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    if result["resumed"] == 0:
        typer.echo("nothing to resume: all cases completed in the prior run")
        raise typer.Exit(PASS_GATE)

    d = result["digest"]
    rec: Recommendation = result["recommendation"]
    typer.echo(
        f"\nresumed {result['resumed']} case(s): pass {d.overall_pass_rate * 100:.1f}% "
        f"({sum(r.passed for r in d.records)}/{len(d.records)})  -> {rec.value}"
    )
    for path in result["written"].values():
        typer.echo(f"  wrote {path}")

    regression = result["regression"]
    regressed = regression is not None and regression.regression_detected
    if rec is Recommendation.PASS and not regressed:
        raise typer.Exit(PASS_GATE)
    raise typer.Exit(FAIL_GATE)
```

- [ ] **Step 8: Run CLI test + full suite**

Run: `uv run pytest tests/test_cli_resume.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check agon/task/resume.py agon/cli/app.py tests/test_resume.py tests/test_cli_resume.py
git add agon/task/resume.py agon/cli/app.py tests/test_resume.py tests/test_cli_resume.py
git commit -m "$(printf 'feat(resume): agon resume command + orchestrator with merged report\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: ADR, docs, and final verification

**Files:**
- Create: `docs/decisions/ADR-0009-run-recovery-error-taxonomy.md`
- Modify: `README.md` (commands + capability mention)
- Modify: `CLAUDE.md` (commands block)

- [ ] **Step 1: Write the ADR**

Create `docs/decisions/ADR-0009-run-recovery-error-taxonomy.md`:

```markdown
# ADR-0009: Run Recovery & Error Taxonomy

**Status:** Accepted - 2026-06-06 (Phase 3 M8)

## Context

A partially-failed run had no recovery path (only a full re-run) and every failure looked the
same in reports (one boolean, one count). Solver/model/timeout errors were in fact invisible:
a sample that errors before scoring produces no scorer score and so was dropped from the digest
entirely (`error_count` read 0).

## Decision

**1. Resume is harness-native, not Inspect `eval_retry`.** `eval_retry` reconstructs a task by
registry name; our `agon_task` is an anonymous in-process `Task` (no `task_registry_name`/
`task_file`), so `eval_retry` raises `Task '<name>' not found` (verified). Registering a
serializable `@task` would break the `callable_fn` programmatic path (in-process callables do
not serialize). Instead `agon resume` reads the prior log, selects incomplete samples,
reconstructs their `AgonCase`s from `metadata[METADATA_CASE_KEY]`, re-runs only those, and
merges the new records with the prior run's passing records into one `RunDigest` rendered
through the existing renderers. A case that legitimately scored `fail` is a result, not an
incomplete sample, and is not re-run. Merged-report cost reflects the re-run only.

**2. Five error categories, classified best-effort.** `timeout`/`resource` come from the
structured `sample.limit.type`; `scorer` from caught judge errors in scorer metadata;
`network`/`sample` from pattern-matching `sample.error` text. Inspect persists only the error
*string* (not the exception class), so network-vs-sample is best-effort; unmatched -> `sample`.
Pre-scoring errors are promoted to visible records (fixing the invisibility bug above).

**3. Per-case timeout is enforced in the SUT solver.** `AgonCase.sample_time_limit` overrides
the run-level default; both are applied per sample via `inspect_ai.util.time_limit`, not via
`eval()`'s global `time_limit` (so a case may request more time than the default). A breach
surfaces as `sample.limit(type="time")` and is classified `timeout`.

## Consequences

- Errors are now first-class in every report (`error_count_by_category`).
- `resume` works fully offline (mockllm / callable adapter), preserving the reproducibility bar.
- Per-case timeouts do not apply to the native ReAct agent path (`agent_task`), which builds its
  own solver; that is acceptable and noted for a future milestone if needed.
```

- [ ] **Step 2: Update README and CLAUDE command lists**

In `CLAUDE.md`, add to the commands block (after the `agon run ... --fail-on-error` line):

```bash
uv run agon resume <run_id> --display none   # re-run only a prior run's failed/incomplete cases; merged report
```

In `README.md`, find the existing CLI/commands listing and add an analogous `agon resume` line plus a one-sentence mention that reports now break errors down by category (`timeout/resource/network/scorer/sample`) and cases may set a per-case `sample_time_limit`. (Match the surrounding format; keep it brief.)

- [ ] **Step 3: Full verification (offline)**

Run each and confirm:

```bash
uv run ruff check agon tests
uv run pytest -q
uv run agon run examples/datasets/rag_smoke.yaml --display none
uv run agon resume --latest --display none
```

Expected:
- ruff: clean.
- pytest: all pass (M8 added ~5 new test files), no new skips beyond the pre-existing 1.
- `agon run`: writes reports; report shows the pass-rate CI + cost `$0.0000`.
- `agon resume --latest`: prints `nothing to resume: all cases completed in the prior run` (rag_smoke has no errored samples) and exits 0.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/ADR-0009-run-recovery-error-taxonomy.md README.md CLAUDE.md
git commit -m "$(printf 'docs(adr): ADR-0009 run recovery and error taxonomy + README/CLAUDE wiring\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-review notes (for the implementer)

- **Latent-bug fix:** Task 2 changes digest output for runs that have pre-scoring errors (they now appear as records). No existing test exercises such a run through the digest, so the suite stays green; if you find one that breaks, the new behavior is correct — update the expectation.
- **Type consistency:** `build_digest` keyword args are identical in `digest()` (Task 2) and `merge_digests` (Task 5). `select_incomplete`/`cases_from_log`/`merge_digests`/`resume_run` signatures match their call sites in Task 6.
- **Windows/ASCII:** every `typer.echo` added uses `-> ` and plain ASCII. The jinja/markdown/ADR may stay UTF-8.
- **Per-case timeout latency:** the timeout tests sleep 3s against a 1s limit, so each costs ~1s. Acceptable.
- **Epochs > 1:** error promotion reads `log.samples` keyed by id and dedupes; cross-epoch error attribution is best-effort. All M8 tests run at the default `epochs=1`.
```
