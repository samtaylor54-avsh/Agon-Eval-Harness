# Statistical Rigor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add uncertainty-aware statistics — Wilson confidence intervals on pass rates, a two-proportion significance test + small-sample awareness in regression detection, and a confidence interval on the judge's Cohen's kappa — all closed-form in a pure-Python `agon/stats` package (no new dependency), fully offline.

**Architecture:** A new stdlib-only `agon/stats/` package computes the statistics; the result data types (`Interval`, `ProportionTest`) live in `agon/schemas` so `agon/stats` imports schemas (never the reverse — no cycles). The digest, regression, and calibration layers consume them; reports render them. The regression *gate* is unchanged — significance is added as information, never to suppress a real regression.

**Tech Stack:** Python 3.12, stdlib `math` (incl. `math.erf` for the normal CDF), Pydantic v2, pytest (`asyncio_mode=auto`), uv, ruff. No scipy/numpy.

**Spec:** `docs/superpowers/specs/2026-06-05-statistical-rigor-design.md`

**Branch:** `phase-3-m6-statistical-rigor` (already created; the design spec is committed there).

---

## Background the engineer needs (read before starting)

- **No new dependency.** Every statistic is closed-form. The normal CDF is `0.5 * (1 + math.erf(z / sqrt(2)))`. Two-sided z critical values are hard-coded constants. Do NOT add scipy/numpy/statsmodels.
- **Verified textbook values** (used in the tests below; computed against the exact formulas):
  - Wilson interval 8/10 @95% = point 0.8, low ≈ 0.4902, high ≈ 0.9433. `n=0` → total uncertainty `[0.0, 1.0]`.
  - `normal_cdf(0)=0.5`, `normal_cdf(1.96)≈0.97500`, `normal_cdf(-1.96)≈0.02500`.
  - Two-proportion test 90/100 vs 80/100: diff 0.1, z ≈ 1.980, p ≈ 0.0477 → significant @95%. 45/50 vs 40/50: diff 0.1, z ≈ 1.400, p ≈ 0.1614 → not significant.
  - kappa CI for `po=0.85, pe=0.5, n=25`: kappa 0.70, CI ≈ [0.4201, 0.9799].
- **Schema-first boundary:** `agon/schemas` holds types that cross modules; `agon/stats` imports from `agon.schemas`. `agon/schemas` imports nothing from `agon`. Keep it that way.
- **Pydantic models** use `model_config = ConfigDict(extra="forbid")` and `Field(default_factory=...)`. New `RunDigest` / `RegressionReport` / `CalibrationReport` fields get sensible defaults so existing construction sites (test helpers) keep working without passing them.
- **ASCII console rule (cp1252):** all `print`/`typer.echo`/CLI output ASCII. Render intervals as `[0.49, 0.94]`, deltas as `+8.0pp` / `p=0.048`. No `±`, no `→`. Docstrings / markdown / jinja may be UTF-8.
- **Name the imported `small_sample` function `is_small_sample`** in `logs.py` / `regression.py` to avoid shadowing the model field also named `small_sample`.
- **Commit hygiene:** banner-PNG deletions and `docs/*.docx` are intentionally unstaged. Every task uses a targeted `git add` of only its own files — never `git add .` / `git add -A`.

---

## File structure

- **Create** `agon/stats/__init__.py`, `agon/stats/normal.py`, `agon/stats/proportion.py`, `agon/stats/kappa.py`.
- **Modify** `agon/schemas/models.py` — add `Interval`, `ProportionTest`; extend `RegressionReport`.
- **Modify** `agon/schemas/__init__.py` — export `Interval`, `ProportionTest`.
- **Modify** `agon/analysis/logs.py` — `RunDigest` CI fields + `digest()` population.
- **Modify** `agon/analysis/regression.py` — compute the pass-rate test.
- **Modify** `agon/calibrate/runner.py` — `CalibrationReport` kappa CI; expose `po`/`pe`.
- **Modify** `agon/reporting/generator.py` + `agon/reporting/templates/report.md.jinja2` — render CIs.
- **Modify** `agon/cli/app.py` — `compare` + `calibrate` output shows CIs / significance.
- **Create** `tests/test_stats.py`; extend digest/regression/calibration tests.
- **Create** `docs/decisions/ADR-0007-statistical-rigor.md`; **modify** `README.md`, `CLAUDE.md`.

---

## Task 1: Schema result types + `agon/stats` normal core

**Files:**
- Modify: `agon/schemas/models.py`, `agon/schemas/__init__.py`
- Create: `agon/stats/__init__.py`, `agon/stats/normal.py`
- Test: `tests/test_stats.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stats.py`:

```python
"""Phase 3 M6 — closed-form statistics (stats core, textbook values)."""

import pytest

from agon.schemas import Interval, ProportionTest
from agon.stats import normal_cdf, z_critical


def test_interval_and_proportiontest_construct():
    iv = Interval(point=0.8, low=0.49, high=0.94)
    assert iv.confidence == 0.95
    pt = ProportionTest(diff=0.1, z=1.98, p_value=0.048, significant=True)
    assert pt.significant is True and pt.confidence == 0.95


def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_z_critical():
    assert z_critical(0.95) == pytest.approx(1.95996, abs=1e-4)
    assert z_critical(0.90) == pytest.approx(1.64485, abs=1e-4)
    with pytest.raises(ValueError):
        z_critical(0.5)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'Interval'` (and `agon.stats` does not exist).

- [ ] **Step 3: Add the schema result types**

In `agon/schemas/models.py`, add these two classes (near the other small result models, e.g. just before `class RegressionReport`):

```python
class Interval(BaseModel):
    """A point estimate with a confidence interval (e.g. a Wilson pass-rate interval)."""

    model_config = ConfigDict(extra="forbid")

    point: float
    low: float
    high: float
    confidence: float = 0.95


class ProportionTest(BaseModel):
    """Result of a two-proportion z-test (e.g. current vs. baseline pass rate)."""

    model_config = ConfigDict(extra="forbid")

    diff: float  # p1 - p2 (e.g. current - baseline)
    z: float
    p_value: float
    significant: bool
    confidence: float = 0.95
```

- [ ] **Step 4: Export the types**

In `agon/schemas/__init__.py`, add `Interval` and `ProportionTest` to the import from `.models` and to `__all__` (keep alphabetical). READ the file first to match its structure.

- [ ] **Step 5: Create the stats normal module**

Create `agon/stats/normal.py`:

```python
"""Normal-distribution helpers (stdlib only) for agon's closed-form statistics."""

from __future__ import annotations

import math

# Two-sided z critical values for common confidence levels.
_Z_CRITICAL = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def normal_cdf(z: float) -> float:
    """Standard-normal CDF via the error function (no scipy)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def z_critical(confidence: float = 0.95) -> float:
    """Two-sided z critical value for a confidence level (0.90 / 0.95 / 0.99 supported)."""
    try:
        return _Z_CRITICAL[confidence]
    except KeyError as exc:
        raise ValueError(
            f"unsupported confidence {confidence}; use one of {sorted(_Z_CRITICAL)}"
        ) from exc
```

Create `agon/stats/__init__.py`:

```python
"""Closed-form statistics for agon (Phase 3 M6) — pure Python, no scipy."""

from agon.stats.normal import normal_cdf, z_critical

__all__ = ["normal_cdf", "z_critical"]
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_stats.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check agon tests` (expect All checks passed!)

```bash
git add agon/schemas/models.py agon/schemas/__init__.py agon/stats/__init__.py agon/stats/normal.py tests/test_stats.py
git commit -m "$(printf 'feat(stats): Interval/ProportionTest schema types + normal CDF core\n\nClosed-form normal CDF via math.erf and hard-coded z criticals; no scipy.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Wilson interval + two-proportion test

**Files:**
- Create: `agon/stats/proportion.py`
- Modify: `agon/stats/__init__.py`
- Test: `tests/test_stats.py` (append)

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_stats.py`:

```python
from agon.stats import small_sample, two_proportion_test, wilson_interval  # noqa: E402


def test_wilson_interval_textbook():
    iv = wilson_interval(8, 10)
    assert iv.point == pytest.approx(0.8)
    assert iv.low == pytest.approx(0.4902, abs=1e-3)
    assert iv.high == pytest.approx(0.9433, abs=1e-3)


def test_wilson_interval_boundaries():
    empty = wilson_interval(0, 0)
    assert empty.low == 0.0 and empty.high == 1.0 and empty.point == 0.0
    full = wilson_interval(10, 10)
    assert full.point == 1.0 and full.high == pytest.approx(1.0, abs=1e-9)
    zero = wilson_interval(0, 10)
    assert zero.point == 0.0 and zero.low == 0.0


def test_two_proportion_test_significant():
    pt = two_proportion_test(90, 100, 80, 100)
    assert pt.diff == pytest.approx(0.1)
    assert pt.z == pytest.approx(1.980, abs=1e-2)
    assert pt.p_value == pytest.approx(0.0477, abs=1e-3)
    assert pt.significant is True


def test_two_proportion_test_not_significant():
    pt = two_proportion_test(45, 50, 40, 50)
    assert pt.p_value == pytest.approx(0.1614, abs=1e-3)
    assert pt.significant is False


def test_two_proportion_test_degenerate():
    pt = two_proportion_test(0, 0, 5, 10)
    assert pt.p_value == 1.0 and pt.significant is False


def test_small_sample():
    assert small_sample(10) is True
    assert small_sample(30) is False
    assert small_sample(100) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'wilson_interval'`.

- [ ] **Step 3: Implement the proportion module**

Create `agon/stats/proportion.py`:

```python
"""Closed-form proportion statistics: Wilson score interval + two-proportion z-test."""

from __future__ import annotations

import math

from agon.schemas import Interval, ProportionTest
from agon.stats.normal import normal_cdf, z_critical

SMALL_SAMPLE_N = 30


def small_sample(n: int, min_n: int = SMALL_SAMPLE_N) -> bool:
    """True when n is below the rule-of-thumb threshold for the normal approximation."""
    return n < min_n


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion (stable at small n and at 0%/100%)."""
    if n <= 0:
        return Interval(point=0.0, low=0.0, high=1.0, confidence=confidence)
    z = z_critical(confidence)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Interval(
        point=p,
        low=max(0.0, center - margin),
        high=min(1.0, center + margin),
        confidence=confidence,
    )


def two_proportion_test(
    s1: int, n1: int, s2: int, n2: int, confidence: float = 0.95
) -> ProportionTest:
    """Pooled two-proportion z-test. ``diff = p1 - p2`` (e.g. current - baseline)."""
    if n1 <= 0 or n2 <= 0:
        return ProportionTest(
            diff=0.0, z=0.0, p_value=1.0, significant=False, confidence=confidence
        )
    p1, p2 = s1 / n1, s2 / n2
    pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0.0:
        return ProportionTest(
            diff=p1 - p2, z=0.0, p_value=1.0, significant=False, confidence=confidence
        )
    z = (p1 - p2) / se
    p_value = 2.0 * (1.0 - normal_cdf(abs(z)))
    return ProportionTest(
        diff=p1 - p2,
        z=z,
        p_value=p_value,
        significant=p_value < (1.0 - confidence),
        confidence=confidence,
    )
```

- [ ] **Step 4: Re-export from the package**

Update `agon/stats/__init__.py` to:

```python
"""Closed-form statistics for agon (Phase 3 M6) — pure Python, no scipy."""

from agon.stats.normal import normal_cdf, z_critical
from agon.stats.proportion import (
    SMALL_SAMPLE_N,
    small_sample,
    two_proportion_test,
    wilson_interval,
)

__all__ = [
    "SMALL_SAMPLE_N",
    "normal_cdf",
    "small_sample",
    "two_proportion_test",
    "wilson_interval",
    "z_critical",
]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_stats.py -q`
Expected: PASS (9 passed).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check agon tests`

```bash
git add agon/stats/proportion.py agon/stats/__init__.py tests/test_stats.py
git commit -m "$(printf 'feat(stats): Wilson interval + two-proportion z-test + small-sample helper\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Cohen's kappa confidence interval

**Files:**
- Create: `agon/stats/kappa.py`
- Modify: `agon/stats/__init__.py`
- Test: `tests/test_stats.py` (append)

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_stats.py`:

```python
from agon.stats import kappa_interval  # noqa: E402


def test_kappa_interval_textbook():
    iv = kappa_interval(0.85, 0.5, 25)
    assert iv.point == pytest.approx(0.70, abs=1e-9)
    assert iv.low == pytest.approx(0.4201, abs=1e-3)
    assert iv.high == pytest.approx(0.9799, abs=1e-3)


def test_kappa_interval_degenerate():
    perfect = kappa_interval(1.0, 1.0, 10)  # pe >= 1 -> degenerate perfect agreement
    assert perfect.point == 1.0 and perfect.low == 1.0 and perfect.high == 1.0
    empty = kappa_interval(0.5, 0.5, 0)  # n = 0
    assert empty.low == empty.high == empty.point


def test_kappa_interval_clamps():
    # Wide SE on a high kappa must clamp the upper bound at 1.0.
    iv = kappa_interval(0.95, 0.5, 5)
    assert iv.high <= 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'kappa_interval'`.

- [ ] **Step 3: Implement the kappa module**

Create `agon/stats/kappa.py`:

```python
"""Closed-form confidence interval for Cohen's kappa (normal approximation)."""

from __future__ import annotations

import math

from agon.schemas import Interval
from agon.stats.normal import z_critical


def kappa_interval(po: float, pe: float, n: int, confidence: float = 0.95) -> Interval:
    """Normal-approximation CI for Cohen's kappa.

    ``po`` = observed agreement, ``pe`` = chance agreement, ``n`` = number of items.
    ``kappa = (po - pe) / (1 - pe)``; ``SE = sqrt(po(1-po)) / ((1-pe) sqrt(n))``. The interval
    is clamped to ``[-1, 1]``. Degenerate inputs (``n <= 0`` or ``pe >= 1``) return a
    zero-width interval at the degenerate kappa.
    """
    if n <= 0 or pe >= 1.0:
        k = 1.0 if pe >= 1.0 else 0.0
        return Interval(point=k, low=k, high=k, confidence=confidence)
    kappa = (po - pe) / (1.0 - pe)
    z = z_critical(confidence)
    se = math.sqrt(po * (1.0 - po)) / ((1.0 - pe) * math.sqrt(n))
    return Interval(
        point=kappa,
        low=max(-1.0, kappa - z * se),
        high=min(1.0, kappa + z * se),
        confidence=confidence,
    )
```

- [ ] **Step 4: Re-export**

In `agon/stats/__init__.py`, add `from agon.stats.kappa import kappa_interval` and insert `"kappa_interval"` into `__all__` (alphabetical).

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_stats.py -q`
Expected: PASS (12 passed).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check agon tests`

```bash
git add agon/stats/kappa.py agon/stats/__init__.py tests/test_stats.py
git commit -m "$(printf 'feat(stats): normal-approximation confidence interval for Cohen kappa\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: Pass-rate confidence intervals in the digest + reports

**Files:**
- Modify: `agon/analysis/logs.py`
- Modify: `agon/reporting/generator.py`, `agon/reporting/templates/report.md.jinja2`
- Test: `tests/test_stats_reporting.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stats_reporting.py`:

```python
"""Phase 3 M6 — pass-rate confidence intervals flow into the digest and reports."""

import json

from inspect_ai import eval
from inspect_ai.model import get_model

from agon.analysis.logs import digest
from agon.schemas import AgonCase, AgonDataset, Interval, Recommendation, RunConfig, ScoringSpec
from agon.reporting.generator import render_json, render_markdown
from agon.task import agon_task


def _offline_log(tmp_path, n=3):
    cases = [
        AgonCase(
            test_id=f"c{i}",
            name=f"c{i}",
            category="c",
            input={"user_message": "hi"},
            scoring=[ScoringSpec(type="exact_match")],
        )
        for i in range(n)
    ]
    dataset = AgonDataset(name="ci_suite", dataset_version="v0", test_cases=cases)
    task = agon_task(dataset, RunConfig(log_dir=str(tmp_path)))
    return eval(task, model=get_model("mockllm/model"), log_dir=str(tmp_path), display="none")[0]


def test_digest_has_pass_rate_ci(tmp_path):
    d = digest(_offline_log(tmp_path))
    assert isinstance(d.overall_pass_ci, Interval)
    assert d.n_cases == 3
    assert d.small_sample is True  # n=3 < 30
    assert 0.0 <= d.overall_pass_ci.low <= d.overall_pass_ci.high <= 1.0


def test_markdown_shows_ci_and_small_sample(tmp_path):
    d = digest(_offline_log(tmp_path))
    md = render_markdown(d, None, Recommendation.PASS)
    assert "[" in md and "]" in md  # an interval is rendered on the pass-rate row
    assert "Small sample" in md


def test_json_has_ci_block(tmp_path):
    d = digest(_offline_log(tmp_path))
    payload = json.loads(render_json(d, None, Recommendation.PASS))
    assert "overall_pass_ci" in payload
    assert payload["n_cases"] == 3
    assert payload["small_sample"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stats_reporting.py -q`
Expected: FAIL — `RunDigest` has no `overall_pass_ci` attribute.

- [ ] **Step 3: Add CI fields to `RunDigest` and populate them**

In `agon/analysis/logs.py`:

1. Add imports near the existing top imports:

```python
from agon.schemas import Interval
from agon.stats import small_sample as is_small_sample, wilson_interval
```

2. Add fields to `class RunDigest` (after `error_count`):

```python
    n_cases: int = 0
    overall_pass_ci: Interval = Field(
        default_factory=lambda: Interval(point=0.0, low=0.0, high=1.0)
    )
    pass_ci_by_category: dict[str, Interval] = Field(default_factory=dict)
    small_sample: bool = False
```

3. In `digest()`, after the per-category loop builds `cat_pass` and before the `return RunDigest(`, add:

```python
    overall_pass_ci = wilson_interval(passed, total)
    pass_ci_by_category = {k: wilson_interval(v[0], v[1]) for k, v in sorted(cat_pass.items())}
```

and add these to the `RunDigest(...)` constructor:

```python
        n_cases=total,
        overall_pass_ci=overall_pass_ci,
        pass_ci_by_category=pass_ci_by_category,
        small_sample=is_small_sample(total),
```

- [ ] **Step 4: Render the CI in JSON**

In `agon/reporting/generator.py::render_json`, add to the `payload` dict (after `"overall_pass_rate"`):

```python
        "n_cases": d.n_cases,
        "overall_pass_ci": d.overall_pass_ci.model_dump(),
        "pass_ci_by_category": {k: v.model_dump() for k, v in d.pass_ci_by_category.items()},
        "small_sample": d.small_sample,
```

- [ ] **Step 5: Render the CI in the md template**

In `agon/reporting/templates/report.md.jinja2`, replace the overall-pass-rate table row:

```jinja
| **Overall pass rate** | **{{ "%.1f"|format(d.overall_pass_rate * 100) }}%** ({{ passed }}/{{ total }}) |
```

with:

```jinja
| **Overall pass rate** | **{{ "%.1f"|format(d.overall_pass_rate * 100) }}%** [{{ "%.1f"|format(d.overall_pass_ci.low * 100) }}%, {{ "%.1f"|format(d.overall_pass_ci.high * 100) }}%] ({{ passed }}/{{ total }}) |
```

Then, immediately AFTER the closing `|` of the metadata table (before the `## Pass rate by category` heading), add:

```jinja
{% if d.small_sample %}
> Small sample (n={{ d.n_cases }} < 30): treat pass rates and intervals with caution.
{% endif %}
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_stats_reporting.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Full suite + lint**

Run: `uv run pytest -q` (expect all pass + 1 skipped — confirms existing reporting/digest tests still pass; if one asserts an exact JSON key set or md snapshot, update it to include the new CI fields — the new data is expected output, not a regression).
Run: `uv run ruff check agon tests`

- [ ] **Step 8: Commit**

```bash
git add agon/analysis/logs.py agon/reporting/generator.py agon/reporting/templates/report.md.jinja2 tests/test_stats_reporting.py
git commit -m "$(printf 'feat(stats): Wilson pass-rate CIs + small-sample note in digest and reports\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Regression significance + small-sample awareness

**Files:**
- Modify: `agon/schemas/models.py` (extend `RegressionReport`)
- Modify: `agon/analysis/regression.py`
- Modify: `agon/cli/app.py` (`compare` output) + `agon/reporting/templates/report.md.jinja2` (regression section)
- Test: `tests/test_regression_significance.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_regression_significance.py`:

```python
"""Phase 3 M6 — regression detection gains a two-proportion test + small-sample flag."""

from agon.analysis.logs import RunDigest, SampleRecord
from agon.analysis.regression import compare_digests
from agon.schemas import ProportionTest


def _digest(run_id, passed_flags):
    records = [
        SampleRecord(
            test_id=f"t{i}",
            passed=p,
            composite_score=1.0 if p else 0.0,
            category="c",
            risk_level="medium",
        )
        for i, p in enumerate(passed_flags)
    ]
    passed = sum(passed_flags)
    total = len(passed_flags)
    return RunDigest(
        run_id=run_id,
        task="t",
        records=records,
        overall_pass_rate=passed / total,
        pass_rate_by_category={"c": passed / total},
        pass_rate_by_risk={"medium": passed / total},
        top_failure_labels=[],
        error_count=0,
    )


def test_regression_report_has_pass_rate_test():
    # 9/10 baseline vs 8/10 current — a small, non-significant drop.
    base = _digest("base", [True] * 9 + [False])
    cur = _digest("cur", [True] * 8 + [False] * 2)
    report = compare_digests(cur, base)
    assert isinstance(report.pass_rate_test, ProportionTest)
    assert report.pass_rate_test.diff < 0  # current is lower
    assert report.small_sample is True  # n=10 < 30
    # The existing gate is unchanged: a new failure still trips it.
    assert report.regression_detected is True
    assert "t9" not in report.new_failures  # t9 failed in both -> unchanged, not new


def test_regression_significant_drop_flagged_in_test_only():
    # Large suites, a clearly significant drop, but the gate logic is the new-failure rule.
    base = _digest("base", [True] * 95 + [False] * 5)
    cur = _digest("cur", [True] * 80 + [False] * 20)
    report = compare_digests(cur, base)
    assert report.pass_rate_test.significant is True
    assert report.small_sample is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_regression_significance.py -q`
Expected: FAIL — `RegressionReport` has no `pass_rate_test` field (validation error / AttributeError).

- [ ] **Step 3: Extend `RegressionReport`**

In `agon/schemas/models.py`, add to `class RegressionReport` (after `regression_detected`):

```python
    pass_rate_test: ProportionTest | None = None
    small_sample: bool = False
```

- [ ] **Step 4: Compute the test in `compare_digests`**

In `agon/analysis/regression.py`:

1. Add the import:

```python
from agon.stats import small_sample as is_small_sample, two_proportion_test
```

2. Inside `compare_digests`, after `common = ...` (or anywhere before the `return`), compute:

```python
    cur_pass = sum(1 for r in current.records if r.passed)
    cur_n = len(current.records)
    base_pass = sum(1 for r in baseline.records if r.passed)
    base_n = len(baseline.records)
    pass_rate_test = two_proportion_test(cur_pass, cur_n, base_pass, base_n)
    small = is_small_sample(cur_n) or is_small_sample(base_n)
```

3. Add `pass_rate_test=pass_rate_test,` and `small_sample=small,` to the `RegressionReport(...)` constructor. **Do not change `regression_detected`.**

- [ ] **Step 5: Show it in the CLI `compare` output**

In `agon/cli/app.py`, in the `compare` command, after the `fixed failures` echo line and before the `for tid, old, new in reg.score_drops:` loop, add:

```python
    t = reg.pass_rate_test
    if t is not None:
        note = "significant" if t.significant else "not significant"
        small = "; small sample" if reg.small_sample else ""
        typer.echo(
            f"  overall pass-rate diff: {t.diff * 100:+.1f}pp "
            f"(p={t.p_value:.3f}, {note}{small})"
        )
```

- [ ] **Step 6: Show it in the md regression section**

In `agon/reporting/templates/report.md.jinja2`, inside the `{% if regression %}` block (after the `- Fixed failures:` line), add:

```jinja
{% if regression.pass_rate_test %}- Overall pass-rate diff: {{ "%+.1f"|format(regression.pass_rate_test.diff * 100) }}pp (p={{ "%.3f"|format(regression.pass_rate_test.p_value) }}, {{ "significant" if regression.pass_rate_test.significant else "not significant" }}{{ "; small sample" if regression.small_sample else "" }})
{% endif %}
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_regression_significance.py -q`
Expected: PASS (2 passed).

- [ ] **Step 8: Full suite + lint**

Run: `uv run pytest -q` (expect all pass + 1 skipped — confirm existing regression/CLI tests still pass).
Run: `uv run ruff check agon tests`

- [ ] **Step 9: Commit**

```bash
git add agon/schemas/models.py agon/analysis/regression.py agon/cli/app.py agon/reporting/templates/report.md.jinja2 tests/test_regression_significance.py
git commit -m "$(printf 'feat(stats): two-proportion significance + small-sample in regression report\n\nThe regression gate is unchanged (new-failure/severe-drop tripwires); the test\nand small-sample flag are added as information in the report and compare CLI.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: Kappa CI in calibration + CLI + ADR + docs + final verification

**Files:**
- Modify: `agon/calibrate/runner.py`
- Modify: `agon/cli/app.py` (`calibrate` output)
- Create: `docs/decisions/ADR-0007-statistical-rigor.md`
- Modify: `README.md`, `CLAUDE.md`
- Test: `tests/test_calibration_ci.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calibration_ci.py`:

```python
"""Phase 3 M6 — calibration reports a confidence interval on Cohen's kappa."""

from agon.calibrate.runner import kappa_components
from agon.schemas import Interval
from agon.stats import kappa_interval


def test_kappa_components_basic():
    human = [True, True, True, False, False]
    judge = [True, True, False, False, False]
    po, pe = kappa_components(human, judge)
    assert po == 0.8  # 4 of 5 agree
    # p_h = 3/5, p_j = 2/5 -> pe = 0.6*0.4 + 0.4*0.6 = 0.48
    assert abs(pe - 0.48) < 1e-9


def test_kappa_interval_from_components():
    human = [True, True, True, False, False]
    judge = [True, True, False, False, False]
    po, pe = kappa_components(human, judge)
    iv = kappa_interval(po, pe, len(human))
    assert isinstance(iv, Interval)
    assert -1.0 <= iv.low <= iv.point <= iv.high <= 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_calibration_ci.py -q`
Expected: FAIL — `ImportError: cannot import name 'kappa_components'`.

- [ ] **Step 3: Add `kappa_components` and the CI to the report**

In `agon/calibrate/runner.py`:

1. Add the import:

```python
from agon.schemas import Interval
from agon.stats import kappa_interval
from agon.stats import small_sample as is_small_sample
```

2. Add the `kappa_components` helper (above `cohen_kappa`) and refactor `cohen_kappa` to use it:

```python
def kappa_components(human: list[bool], judge: list[bool]) -> tuple[float, float]:
    """Return (po, pe): observed and chance agreement for two binary raters."""
    n = len(human)
    if n == 0:
        return 0.0, 0.0
    po = sum(h == j for h, j in zip(human, judge, strict=True)) / n
    p_h = sum(human) / n
    p_j = sum(judge) / n
    pe = p_h * p_j + (1 - p_h) * (1 - p_j)
    return po, pe


def cohen_kappa(human: list[bool], judge: list[bool]) -> float:
    """Cohen's kappa for two binary raters."""
    po, pe = kappa_components(human, judge)
    if pe >= 1.0:
        return 1.0  # perfect, degenerate agreement
    if len(human) == 0:
        return 0.0
    return (po - pe) / (1 - pe)
```

3. Add fields to `class CalibrationReport` (after `cohen_kappa`):

```python
    kappa_ci: Interval = Field(default_factory=lambda: Interval(point=0.0, low=0.0, high=0.0))
    small_sample: bool = False
```

4. In `run_calibration`, replace the `kappa = cohen_kappa(...)` line and the `return CalibrationReport(...)` so they compute and pass the CI:

```python
    po, pe = kappa_components(human_labels, judge_labels)
    kappa = cohen_kappa(human_labels, judge_labels)
    kappa_ci = kappa_interval(po, pe, n)
    return CalibrationReport(
        scorer_type=cset.scorer_type,
        n=n,
        accuracy=accuracy,
        cohen_kappa=kappa,
        kappa_ci=kappa_ci,
        small_sample=is_small_sample(n),
        min_kappa=min_kappa,
        passed=kappa >= min_kappa,
        disagreements=disagreements,
    )
```

- [ ] **Step 4: Show the CI in the CLI `calibrate` output**

In `agon/cli/app.py`, in the `calibrate` command, change the summary `typer.echo(...)` that prints
`kappa={report.cohen_kappa:.2f}` to include the interval and small-sample note. Replace that echo with:

```python
    small = " (small sample)" if report.small_sample else ""
    typer.echo(
        f"calibration [{report.scorer_type}] n={report.n} "
        f"accuracy={report.accuracy:.2f} "
        f"kappa={report.cohen_kappa:.2f} [{report.kappa_ci.low:.2f}, {report.kappa_ci.high:.2f}] "
        f"(min {report.min_kappa}){small} -> {'PASS' if report.passed else 'FAIL'}"
    )
```

READ the current `calibrate` command first to match the exact echo it replaces (keep the
disagreement loop and exit code after it unchanged).

- [ ] **Step 5: Write ADR-0007**

Create `docs/decisions/ADR-0007-statistical-rigor.md`:

```markdown
# ADR-0007: Statistical rigor via closed-form, dependency-free statistics

**Status:** Accepted · **Date:** 2026-06-05 · **Milestone:** Phase 3 M6

## Context

The harness reported point estimates only: bare pass rates, a fixed-epsilon regression rule, and a
Cohen's kappa with no interval. A 90% -> 88% move on 50 samples looked identical to the same move on
500; a borderline judge kappa looked as trustworthy as a confident one. The project is offline-first
with a minimal dependency set.

## Decision

Add uncertainty-aware statistics computed **closed-form in pure Python** (a new `agon/stats`
package), with the result types (`Interval`, `ProportionTest`) living in `agon/schemas`:

- **Pass rates** carry a **Wilson score interval** (stable at small n and at 0%/100%), surfaced in
  the digest and md/json reports, with a small-sample note when n < 30.
- **Regression** gains a **two-proportion z-test** on the overall pass-rate delta plus a
  small-sample flag — as *information*. The existing gate (new failures / high-risk score drops) is
  unchanged: a real regression is never silenced by "not statistically significant."
- **Calibration** gains a **normal-approximation confidence interval on Cohen's kappa**, so a
  borderline judge validation is visibly uncertain. `passed` still keys on the point estimate.

No scipy/numpy: the normal CDF is `math.erf`; z criticals are constants; all formulas are
textbook-tested.

## Consequences

- Results are honest about uncertainty without adding a dependency or breaking the offline path.
- Reviewers get a signal/noise read; the regression gate keeps its exact sensitivity.

## Deferred

- Bayesian / credible intervals, sequential testing, power analysis; multiple-comparison correction
  across per-category tests; per-case (continuous score) significance.
```

- [ ] **Step 6: Update README + CLAUDE**

In `README.md`, under **Phase 3**, add a checked line after the real-provider-hardening line:

```markdown
- [x] **Statistical rigor** — Wilson confidence intervals on pass rates, a two-proportion significance test + small-sample awareness in regression, and a Cohen's kappa CI in judge calibration; closed-form, no new dependency (M6, ADR-0007)
```

In `CLAUDE.md`, in the Key-layout sentence that lists `agon/{...}` packages, add `stats` to the list
(e.g. `...,scoring,analysis,reporting,calibrate,review,retrieval,task,config,cli,cost,stats}`). READ
the file first to match the exact current list (it may already include `cost`).

- [ ] **Step 7: Final verification (offline)**

Run each and confirm:

```bash
uv run ruff check agon tests          # All checks passed!
uv run pytest -q                      # all pass (+ new M6 tests), 1 skipped
uv run agon run examples/datasets/rag_smoke.yaml --display none --report-dir reports_verify   # report shows a pass-rate CI + small-sample note
```

Open the latest `reports_verify/*.report.md` and confirm the overall pass-rate row shows a
`[low%, high%]` interval and (for the 20-case suite) a `Small sample` note; confirm ASCII. Then
`rm -rf reports_verify` (do NOT stage it).

- [ ] **Step 8: Commit**

```bash
git add agon/calibrate/runner.py agon/cli/app.py docs/decisions/ADR-0007-statistical-rigor.md README.md CLAUDE.md tests/test_calibration_ci.py
git commit -m "$(printf 'feat(stats): kappa CI in calibration + ADR-0007 + README/CLAUDE\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-review notes (plan vs. spec)

- **Spec coverage:** `agon/stats` core with no scipy (Tasks 1-3); Wilson pass-rate CIs in digest+reports (Task 4); two-proportion significance + small-sample in regression, gate unchanged (Task 5); kappa CI in calibration (Task 6); `Interval`/`ProportionTest` in schemas with `agon/stats` importing schemas (Task 1); ADR + README/CLAUDE (Task 6). Small-sample n<30 threshold (Task 2 `SMALL_SAMPLE_N`).
- **Augment-not-gate honored:** Task 5 explicitly does not change `regression_detected`; the test asserts the new-failure tripwire still fires (`regression_detected is True`) while the significance test is informational.
- **Verified numerics:** Wilson 8/10 -> [0.4902, 0.9433]; normal_cdf(1.96) -> 0.975; two-proportion 90/100 vs 80/100 -> p 0.0477 significant, 45/50 vs 40/50 -> p 0.1614 not; kappa(0.85,0.5,25) -> 0.70 [0.4201, 0.9799]. All asserted with `pytest.approx` tolerances.
- **Type consistency:** `Interval{point,low,high,confidence}` and `ProportionTest{diff,z,p_value,significant,confidence}` are used identically across stats, digest, regression, calibration. `wilson_interval`/`two_proportion_test`/`kappa_interval`/`small_sample`/`normal_cdf`/`z_critical` signatures match between definition (Tasks 1-3) and call sites (Tasks 4-6). `small_sample` imported as `is_small_sample` at call sites to avoid the field-name clash.
- **No placeholders:** every step has concrete code/commands.
- **Integration risk flagged:** Task 4 Step 7 notes that an existing report/digest test asserting an exact JSON key set or md snapshot must be updated to include the new CI fields (expected output, not a regression).
