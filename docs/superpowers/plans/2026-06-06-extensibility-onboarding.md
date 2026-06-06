# Extensibility & Onboarding Implementation Plan (Phase 3 M7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the harness's three extension surfaces (datasets, scorers, SUT adapters) first-class and documented — add an `agon run --plugin` loader so a user's own scorer is usable from the CLI, ship a copy-me template and a brand-new text-to-SQL worked example, and write the long-promised `CONTRIBUTING.md` + extension guide.

**Architecture:** One small, well-bounded core feature (`agon/scoring/plugins.py` + a `--plugin` option and a pre-flight scorer check on `agon run`) plus four additive artifacts (template dir, example dir, two docs, one ADR). The plugin loader imports user modules so their `@register` side-effects land on `agon.scoring.default_registry` before the task builds. Everything stays offline (stdlib `sqlite3`), zero new dependencies.

**Tech Stack:** Python 3.12, Inspect AI, Typer CLI, Pydantic schemas, pytest (`asyncio_mode=auto`), ruff (line-length 100, rules `E,F,I,UP,B,W`), stdlib `importlib` + `sqlite3`.

---

## Conventions for every task

- Run from the repo root with `uv run ...`. Tests live under `tests/` (pytest `testpaths=["tests"]` — files under `templates/` and `examples/` are **not** collected by the suite).
- Async tests are plain `async def test_...` (no `anyio.run`) because `asyncio_mode=auto`.
- **CLI / printed output must be ASCII (cp1252)**: use `-> `, `[...]`, no `±`/`→`/`—`. Markdown, YAML, and docstrings may be UTF-8.
- **Targeted `git add` only** — stage exactly the files each task lists. Never `git add .` / `-A` (the tree carries unrelated banner-PNG deletions + untracked docx/HANDOFF).
- Commit message trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- After each task: `uv run ruff check agon tests` and the task's tests must be green before committing.

---

## File structure (what each new file is responsible for)

- `agon/scoring/plugins.py` — **new**. `load_plugins(specs)` imports dotted modules or `.py` file paths so their `@register` decorators fire; returns the names of newly-registered scorers. `PluginLoadError` for a clean CLI message. Sole responsibility: turn a list of plugin specs into registry side-effects.
- `agon/cli/app.py` — **modify** `run`: add `--plugin/-p`, call `load_plugins`, and pre-flight-validate that every dataset scorer type is registered (clean abort + hint if not).
- `examples/text_to_sql/schema.sql` — **new**. Tiny SQLite schema + seed rows.
- `examples/text_to_sql/sql_scorer.py` — **new**. `compare_sql()` pure core + `SqlResultMatchScorer` (`scorer_type="sql_result_match"`).
- `examples/text_to_sql/dataset.yaml` — **new**. ~6 NL->SQL cases.
- `examples/text_to_sql/run.py` — **new**. Stub NL->SQL SUT + launcher -> mixed report.
- `templates/your-eval/{dataset.yaml,scorer.py,test_scorer.py,sut_adapter.py,run.py,README.md}` — **new**. Copy-me skeleton.
- `docs/extending.md` — **new**. The three-surface extension guide.
- `CONTRIBUTING.md` — **new**. Dev setup, principles, extension pointers, conventions.
- `docs/decisions/ADR-0008-extensibility-contract.md` — **new**. Records the stable contract + decisions.
- `README.md`, `CLAUDE.md` — **modify**. Link the new docs; note `--plugin`; add `templates/` to layout.
- `tests/test_plugins.py`, `tests/test_cli_plugin.py`, `tests/test_text_to_sql.py`, `tests/test_template.py` — **new** tests.

---

## Task 1: `agon/scoring/plugins.py` — the plugin loader

**Files:**
- Create: `agon/scoring/plugins.py`
- Test: `tests/test_plugins.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins.py`:

```python
"""M7 — external scorer plugin loader (dotted module + .py file path)."""

from __future__ import annotations

import sys

import pytest

from agon.scoring import default_registry
from agon.scoring.plugins import PluginLoadError, load_plugins

DUMMY = '''
from agon.scoring.base import ScoreOutcome, register


@register
class _DummyPluginScorer:
    scorer_type = "dummy_plugin_scorer"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        return ScoreOutcome(
            scorer_type=self.scorer_type, native_score=True, normalized_score=1.0
        )
'''


@pytest.fixture
def clean_registry():
    """Snapshot/restore the registry + sys.modules so plugin tests don't leak."""
    before_keys = set(default_registry.keys())
    before_mods = set(sys.modules)
    yield
    for key in set(default_registry.keys()) - before_keys:
        default_registry._scorers.pop(key, None)
    for mod in set(sys.modules) - before_mods:
        sys.modules.pop(mod, None)


def test_load_from_file_path(tmp_path, clean_registry):
    f = tmp_path / "my_scorer.py"
    f.write_text(DUMMY, encoding="utf-8")
    loaded = load_plugins([str(f)])
    assert loaded == ["dummy_plugin_scorer"]
    assert default_registry.has("dummy_plugin_scorer")


def test_load_from_dotted_module(tmp_path, clean_registry, monkeypatch):
    pkg = tmp_path / "myplugins.py"
    pkg.write_text(DUMMY, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = load_plugins(["myplugins"])
    assert loaded == ["dummy_plugin_scorer"]
    assert default_registry.has("dummy_plugin_scorer")


def test_bad_spec_raises_plugin_load_error(clean_registry):
    with pytest.raises(PluginLoadError) as exc:
        load_plugins(["no_such_module_xyz"])
    assert "no_such_module_xyz" in str(exc.value)


def test_empty_specs_returns_empty(clean_registry):
    assert load_plugins([]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_plugins.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agon.scoring.plugins'`.

- [ ] **Step 3: Implement the loader**

Create `agon/scoring/plugins.py`:

```python
"""Load external scorer modules so their ``@register`` side-effects populate the registry.

A plugin "spec" is either a dotted module name (importable, on ``sys.path`` / CWD) or a path
to a ``.py`` file. Importing it runs the module top-level, which is where ``@register`` fires.
Used by ``agon run --plugin`` so a user's own scorer is usable without forking agon core.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path

from agon.scoring.base import default_registry


class PluginLoadError(Exception):
    """A --plugin spec could not be imported."""

    def __init__(self, spec: str, original: Exception) -> None:
        self.spec = spec
        self.original = original
        super().__init__(f"could not load plugin {spec!r}: {original}")


def _looks_like_file(spec: str) -> bool:
    return spec.endswith(".py") or Path(spec).exists()


def _load_file(spec: str) -> None:
    path = Path(spec).resolve()
    if not path.exists():
        raise FileNotFoundError(f"no such plugin file: {path}")
    mod_name = f"agon_plugin_{path.stem}"
    import_spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if import_spec is None or import_spec.loader is None:
        raise ImportError(f"cannot build import spec for {path}")
    module = importlib.util.module_from_spec(import_spec)
    sys.modules[mod_name] = module
    import_spec.loader.exec_module(module)


def _load_module(spec: str) -> None:
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    importlib.import_module(spec)


def load_plugins(specs: Iterable[str]) -> list[str]:
    """Import each spec; return the sorted scorer_types that newly appeared on the registry."""
    loaded: list[str] = []
    for spec in specs:
        before = set(default_registry.keys())
        try:
            if _looks_like_file(spec):
                _load_file(spec)
            else:
                _load_module(spec)
        except Exception as exc:
            raise PluginLoadError(spec, exc) from exc
        loaded.extend(sorted(set(default_registry.keys()) - before))
    return loaded
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_plugins.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint**

Run: `uv run ruff check agon/scoring/plugins.py tests/test_plugins.py`
Expected: `All checks passed!`
Note: the broad `except Exception` is intentional (user module code can raise anything) and is re-raised `from exc` (satisfies bugbear B904). Blind-except (BLE) is not in the selected rule set, so no `# noqa` is needed.

- [ ] **Step 6: Commit**

```bash
git add agon/scoring/plugins.py tests/test_plugins.py
git commit -m "feat(plugins): load external scorer modules (dotted name or .py path)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Wire `--plugin` + pre-flight scorer check into `agon run`

**Files:**
- Modify: `agon/cli/app.py` (`run` command, around lines 70-138)
- Test: `tests/test_cli_plugin.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_plugin.py`:

```python
"""M7 — `agon run --plugin` loads a user scorer; missing scorer aborts with a hint."""

from __future__ import annotations

import sys

from typer.testing import CliRunner

from agon.cli import app
from agon.scoring import default_registry

runner = CliRunner()

DATASET = """
name: plugin_demo
test_cases:
  - test_id: p_001
    name: uses a plugin scorer
    category: demo
    input:
      user_message: "hi"
    expected:
      expected_answer: "hi"
    scoring:
      - {type: dummy_plugin_scorer, weight: 1.0, pass_threshold: 1.0}
"""

SCORER = '''
from agon.scoring.base import ScoreOutcome, register


@register
class _DummyPluginScorer:
    scorer_type = "dummy_plugin_scorer"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        return ScoreOutcome(
            scorer_type=self.scorer_type, native_score=True, normalized_score=1.0
        )
'''


def _cleanup():
    default_registry._scorers.pop("dummy_plugin_scorer", None)
    for mod in [m for m in sys.modules if m.startswith("agon_plugin_")]:
        sys.modules.pop(mod, None)


def test_run_with_plugin_resolves_scorer(tmp_path):
    ds = tmp_path / "ds.yaml"
    ds.write_text(DATASET, encoding="utf-8")
    sc = tmp_path / "sc.py"
    sc.write_text(SCORER, encoding="utf-8")
    try:
        result = runner.invoke(
            app,
            ["run", str(ds), "--plugin", str(sc),
             "--log-dir", str(tmp_path / "logs"),
             "--report-dir", str(tmp_path / "reports"),
             "--display", "none"],
        )
        # Scorer resolved -> no abort (exit 2). mockllm answers wrongly -> fail gate (exit 1).
        assert result.exit_code != 2, result.stdout
        assert "loaded plugin scorers: dummy_plugin_scorer" in result.stdout
    finally:
        _cleanup()


def test_run_without_plugin_aborts_with_hint(tmp_path):
    ds = tmp_path / "ds.yaml"
    ds.write_text(DATASET, encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", str(ds),
         "--log-dir", str(tmp_path / "logs"),
         "--report-dir", str(tmp_path / "reports"),
         "--display", "none"],
    )
    assert result.exit_code == 2, result.stdout
    assert "dummy_plugin_scorer" in result.stdout
    assert "--plugin" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli_plugin.py -q`
Expected: FAIL — `--plugin` is not a known option (usage error, exit 2 with "No such option"), and the second test's abort message lacks the hint.

- [ ] **Step 3: Add the import + helper**

In `agon/cli/app.py`, add to the imports near line 26 (`from agon.scoring import JudgeClient`):

```python
from agon.scoring import JudgeClient, default_registry
from agon.scoring.plugins import PluginLoadError, load_plugins
```

Then add this module-level helper after `_apply_resilience_flags` (after line 67):

```python
def _validate_scorers(ds) -> list[str]:
    """Return the sorted scorer types referenced by the dataset that are not registered."""
    unknown = {
        spec.type
        for case in ds.test_cases
        for spec in case.scoring
        if not default_registry.has(spec.type)
    }
    return sorted(unknown)
```

- [ ] **Step 4: Add the `--plugin` option to `run`**

In `agon/cli/app.py`, add a new option to the `run` signature. Insert immediately after the `display` option (after line 81, before `max_retries`):

```python
    plugin: list[str] = typer.Option(
        [], "--plugin", "-p", help="Import a scorer module (dotted name or .py path) before running"
    ),
```

- [ ] **Step 5: Load plugins + pre-flight after dataset load**

In `agon/cli/app.py`, the current block (lines 130-138) is:

```python
    try:
        ds = load_dataset(dataset)
    except (DatasetValidationError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    if not anyio.run(health_check, cfg.sut):
```

Replace it with (adds plugin loading before, and scorer validation after, the dataset load):

```python
    try:
        loaded = load_plugins(plugin)
    except PluginLoadError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    if loaded:
        typer.echo(f"loaded plugin scorers: {', '.join(loaded)}")

    try:
        ds = load_dataset(dataset)
    except (DatasetValidationError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    unknown = _validate_scorers(ds)
    if unknown:
        typer.echo(
            f"[abort] unknown scorer_type(s): {unknown}; "
            f"registered: {default_registry.keys()}; "
            f"did you forget --plugin <module-or-file>?",
            err=True,
        )
        raise typer.Exit(ABORT)

    if not anyio.run(health_check, cfg.sut):
```

Note: `CliRunner` captures stderr into `result.stdout` by default (mix_stderr), so the tests' `result.stdout` assertions see the `err=True` lines.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli_plugin.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Run the full CLI suite (no regressions) + lint**

Run: `uv run pytest tests/test_cli.py tests/test_cli_resilience.py tests/test_cli_plugin.py -q && uv run ruff check agon/cli/app.py tests/test_cli_plugin.py`
Expected: all pass; `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add agon/cli/app.py tests/test_cli_plugin.py
git commit -m "feat(cli): agon run --plugin + pre-flight unknown-scorer abort

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: text-to-SQL scorer — `compare_sql` core + `SqlResultMatchScorer`

**Files:**
- Create: `examples/text_to_sql/schema.sql`
- Create: `examples/text_to_sql/sql_scorer.py`
- Test: `tests/test_text_to_sql.py`

- [ ] **Step 1: Create the schema fixture**

Create `examples/text_to_sql/schema.sql`:

```sql
-- Tiny self-contained schema + seed rows for the text-to-SQL eval (in-memory SQLite).
CREATE TABLE employees (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    dept   TEXT NOT NULL,
    salary INTEGER NOT NULL
);

INSERT INTO employees (id, name, dept, salary) VALUES
    (1, 'Ada',   'engineering', 120000),
    (2, 'Ben',   'engineering',  95000),
    (3, 'Cara',  'sales',        80000),
    (4, 'Dan',   'sales',        72000),
    (5, 'Erin',  'marketing',   105000);
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_text_to_sql.py`:

```python
"""M7 — text-to-SQL custom scorer: result-set comparison, not string equality."""

from __future__ import annotations

import importlib.util
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "text_to_sql"
SCHEMA_SQL = (EXAMPLE_DIR / "schema.sql").read_text(encoding="utf-8")


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, str(EXAMPLE_DIR / filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sql_scorer = _load_module("t2s_scorer_under_test", "sql_scorer.py")


def test_identical_query_passes():
    ref = "SELECT name FROM employees WHERE dept = 'engineering'"
    ok, label, _ = sql_scorer.compare_sql(ref, ref, SCHEMA_SQL)
    assert ok and label is None


def test_equivalent_but_different_query_passes():
    ref = "SELECT name FROM employees WHERE dept = 'engineering'"
    cand = "SELECT name FROM employees WHERE dept IN ('engineering')"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert ok and label is None


def test_wrong_rows_fails_with_label():
    ref = "SELECT name FROM employees WHERE salary > 100000"
    cand = "SELECT name FROM employees WHERE salary > 50000"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "wrong_rows"


def test_malformed_candidate_fails_with_sql_error():
    ref = "SELECT name FROM employees"
    cand = "SELECT name FROM emploable"  # no such table
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "sql_error"


def test_order_sensitive_when_reference_orders():
    ref = "SELECT name FROM employees ORDER BY salary DESC"
    cand = "SELECT name FROM employees ORDER BY salary ASC"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "wrong_rows"


async def test_scorer_wraps_compare_into_outcome():
    from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
    from agon.sut import SUTResponse

    case = AgonCase(
        test_id="sql_x",
        name="n",
        category="text_to_sql",
        input={"user_message": "names in engineering"},
        expected=ExpectedBehavior(
            expected_answer="SELECT name FROM employees WHERE dept = 'engineering'"
        ),
        scoring=[ScoringSpec(type="sql_result_match", params={"schema": "schema.sql"})],
    )
    resp = SUTResponse(final_answer="SELECT name FROM employees WHERE dept IN ('engineering')")
    scorer = sql_scorer.SqlResultMatchScorer()
    out = await scorer.score(case, resp, case.scoring[0])
    assert out.normalized_score == 1.0
    assert out.labels == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_text_to_sql.py -q`
Expected: FAIL — `examples/text_to_sql/sql_scorer.py` does not exist (spec_from_file_location -> error / FileNotFoundError on read).

- [ ] **Step 4: Implement the scorer + pure core**

Create `examples/text_to_sql/sql_scorer.py`:

```python
"""Custom scorer for the text-to-SQL example: compare *result rows*, not SQL strings.

Why a custom scorer? Two different SQL strings can return identical rows. ``exact_match``
would wrongly fail an equivalent query; this scorer executes both queries against a fresh
in-memory SQLite DB (stdlib, offline) and compares the result sets.

Use it from the CLI:
    uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml
or from a launcher script (see run.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agon.scoring.base import ScoreOutcome, register

_SCHEMA_CACHE: dict[str, str] = {}


def _load_schema(schema_file: str) -> str:
    path = Path(schema_file)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    key = str(path)
    if key not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[key] = path.read_text(encoding="utf-8")
    return _SCHEMA_CACHE[key]


def _run_query(schema_sql: str, query: str) -> list[tuple]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema_sql)
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def compare_sql(candidate: str, reference: str, schema_sql: str) -> tuple[bool, str | None, str]:
    """Compare candidate vs reference SQL by result rows.

    Returns ``(passed, failure_label, detail)``. Order-insensitive unless the reference
    contains ``order by`` (then row order must match). A candidate that raises is a
    ``sql_error``; a clean-but-wrong result is ``wrong_rows``. A reference that raises is a
    dataset bug and is allowed to propagate (fail loud).
    """
    expected_rows = _run_query(schema_sql, reference)
    try:
        actual_rows = _run_query(schema_sql, candidate)
    except sqlite3.Error as exc:
        return (False, "sql_error", f"candidate query error: {exc}")

    if "order by" in reference.lower():
        match = actual_rows == expected_rows
    else:
        match = sorted(map(repr, actual_rows)) == sorted(map(repr, expected_rows))

    if match:
        return (True, None, f"{len(actual_rows)} rows match")
    return (False, "wrong_rows", f"expected {len(expected_rows)} rows, got {len(actual_rows)}")


@register
class SqlResultMatchScorer:
    scorer_type = "sql_result_match"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        reference = case.expected.expected_answer
        if reference is None:
            return ScoreOutcome(
                scorer_type=self.scorer_type,
                native_score=False,
                normalized_score=0.0,
                rationale="no expected_answer (reference SQL) provided",
            )
        schema_sql = _load_schema(spec.params.get("schema", "schema.sql"))
        passed, label, detail = compare_sql(response.final_answer, reference, schema_sql)
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[label] if label else [],
            rationale=detail,
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_text_to_sql.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Lint**

Run: `uv run ruff check examples/text_to_sql/sql_scorer.py tests/test_text_to_sql.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add examples/text_to_sql/schema.sql examples/text_to_sql/sql_scorer.py tests/test_text_to_sql.py
git commit -m "feat(example): text-to-SQL result-set scorer (sql_result_match)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: text-to-SQL dataset + runnable launcher + integration test

**Files:**
- Create: `examples/text_to_sql/dataset.yaml`
- Create: `examples/text_to_sql/run.py`
- Test: extend `tests/test_text_to_sql.py`

- [ ] **Step 1: Create the dataset**

Create `examples/text_to_sql/dataset.yaml`:

```yaml
# Text-to-SQL eval. The SUT answers a question with a SQL query; the custom
# `sql_result_match` scorer runs it against examples/text_to_sql/schema.sql and
# compares result rows. Run it with:
#   uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml
# or fully offline with a canned SUT:  uv run python examples/text_to_sql/run.py
name: text_to_sql_suite
test_cases:
  - test_id: sql_001
    name: names in engineering
    category: text_to_sql
    risk_level: low
    input:
      user_message: "List the names of everyone in the engineering department."
    expected:
      expected_answer: "SELECT name FROM employees WHERE dept = 'engineering'"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, filter]

  - test_id: sql_002
    name: total headcount
    category: text_to_sql
    risk_level: low
    input:
      user_message: "How many employees are there?"
    expected:
      expected_answer: "SELECT COUNT(*) FROM employees"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, aggregate]

  - test_id: sql_003
    name: average salary
    category: text_to_sql
    risk_level: low
    input:
      user_message: "What is the average salary?"
    expected:
      expected_answer: "SELECT AVG(salary) FROM employees"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, aggregate]

  - test_id: sql_004
    name: high earners
    category: text_to_sql
    risk_level: medium
    input:
      user_message: "Who earns more than 100000?"
    expected:
      expected_answer: "SELECT name FROM employees WHERE salary > 100000"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, filter]

  - test_id: sql_005
    name: names by salary desc
    category: text_to_sql
    risk_level: low
    input:
      user_message: "List employee names ordered by salary, highest first."
    expected:
      expected_answer: "SELECT name FROM employees ORDER BY salary DESC"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, ordering]

  - test_id: sql_006
    name: distinct departments
    category: text_to_sql
    risk_level: low
    input:
      user_message: "Which departments exist?"
    expected:
      expected_answer: "SELECT DISTINCT dept FROM employees"
    scoring:
      - {type: sql_result_match, weight: 1.0, pass_threshold: 1.0, params: {schema: schema.sql}}
    failure_labels: [sql_error, wrong_rows]
    tags: [text_to_sql, distinct]
```

- [ ] **Step 2: Create the launcher**

Create `examples/text_to_sql/run.py`:

```python
"""Offline text-to-SQL eval against a canned NL->SQL SUT.

No API key, no model downloads. Demonstrates the custom `sql_result_match` scorer producing a
mixed report: one equivalent-but-different query passes (string match would fail), one query is
wrong, and one is malformed.

    uv run python examples/text_to_sql/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse
from agon.task import run_eval

# Make this folder importable whether run as a script or imported by a test, then register
# the custom scorer via its import side-effect. (Keep agon imports above to satisfy ruff isort;
# this lone local import sits after the sys.path mutation, hence the E402/F401 noqa.)
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sql_scorer  # noqa: E402,F401  (registers sql_result_match)

# Canned SQL per test_id. Note sql_001 is equivalent-but-different (passes on rows),
# sql_004 is wrong (wrong_rows), sql_006 is malformed (sql_error).
RESPONSES: dict[str, str] = {
    "sql_001": "SELECT name FROM employees WHERE dept IN ('engineering')",
    "sql_002": "SELECT COUNT(*) FROM employees",
    "sql_003": "SELECT AVG(salary) FROM employees",
    "sql_004": "SELECT name FROM employees WHERE salary > 50000",
    "sql_005": "SELECT name FROM employees ORDER BY salary DESC",
    "sql_006": "SELECT DISTINCT department FROM employees",
}


async def stub_sut(req: SUTRequest) -> SUTResponse:
    test_id = req.session_id.rsplit("_", 1)[0]
    return SUTResponse(final_answer=RESPONSES.get(test_id, "SELECT 1"))


def main() -> None:
    dataset = load_dataset(str(HERE / "dataset.yaml"))
    config = RunConfig(
        system_version="text_to_sql_v1",
        sut=SUTConfig(adapter="callable"),
        log_dir="logs",
        report_dir="reports",
    )
    log = run_eval(dataset, config, callable_fn=stub_sut, display="none")
    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    passed = sum(r.passed for r in digest.records)
    print(
        f"{dataset.name}: {passed}/{len(digest.records)} passed "
        f"-> {result['recommendation'].value}"
    )
    for path in result["written"].values():
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the failing integration test**

Append to `tests/test_text_to_sql.py`:

```python
def test_example_run_yields_mixed_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep logs/reports out of the repo
    run_mod = _load_module("t2s_run_under_test", "run.py")

    from agon.reporting import generate_reports
    from agon.schemas import RunConfig, SUTConfig
    from agon.task import run_eval

    dataset = run_mod.load_dataset(str(EXAMPLE_DIR / "dataset.yaml"))
    config = RunConfig(system_version="t", sut=SUTConfig(adapter="callable"))
    log = run_eval(dataset, config, callable_fn=run_mod.stub_sut, display="none")
    result = generate_reports(log, config=config, out_dir=str(tmp_path / "reports"))
    digest = result["digest"]
    passed = sum(r.passed for r in digest.records)
    # sql_001/002/003/005 pass; sql_004 wrong_rows; sql_006 sql_error.
    assert len(digest.records) == 6
    assert passed == 4
```

- [ ] **Step 4: Run the test to verify it fails, then passes**

Run: `uv run pytest tests/test_text_to_sql.py::test_example_run_yields_mixed_report -q`
Expected first run: FAIL — `run.py` does not exist yet (only if Steps 1-2 skipped). With Steps 1-2 done, run it and expect PASS.
If FAIL for another reason, debug the canned SQL vs expected rows until `passed == 4`.

- [ ] **Step 5: Verify the launcher runs end-to-end offline**

Run: `uv run python examples/text_to_sql/run.py`
Expected: prints `text_to_sql_suite: 4/6 passed -> ...` and `wrote ...` lines; exit 0. Delete any `logs/` `reports/` it created in the repo root if present (or run from a scratch dir).

- [ ] **Step 6: Verify the CLI `--plugin` path resolves the scorer**

Run: `uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml --display none --log-dir "$TMPDIR/t2s_logs" --report-dir "$TMPDIR/t2s_reports"`
(Windows PowerShell: use `$env:TEMP` paths.)
Expected: prints `loaded plugin scorers: sql_result_match`, then a pass-rate line; exit code 1 (mockllm answers are not valid SQL, so cases fail) — the point is it does **not** abort with exit 2.

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check examples/text_to_sql tests/test_text_to_sql.py`
Expected: `All checks passed!`

```bash
git add examples/text_to_sql/dataset.yaml examples/text_to_sql/run.py tests/test_text_to_sql.py
git commit -m "feat(example): text-to-SQL dataset + offline launcher

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: copy-me template `templates/your-eval/`

**Files:**
- Create: `templates/your-eval/dataset.yaml`
- Create: `templates/your-eval/scorer.py`
- Create: `templates/your-eval/test_scorer.py`
- Create: `templates/your-eval/sut_adapter.py`
- Create: `templates/your-eval/run.py`
- Create: `templates/your-eval/README.md`
- Test: `tests/test_template.py`

- [ ] **Step 1: Write the failing rot-guard test**

Create `tests/test_template.py`:

```python
"""M7 — the copy-me template must keep running offline (anti-rot guard)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "your-eval"


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, str(TEMPLATE_DIR / filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_template_runs_and_produces_a_digest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_mod = _load_module("tmpl_run_under_test", "run.py")

    from agon.schemas import RunConfig, SUTConfig
    from agon.task import run_eval

    dataset = run_mod.load_dataset(str(TEMPLATE_DIR / "dataset.yaml"))
    config = RunConfig(system_version="t", sut=SUTConfig(adapter="callable"))
    log = run_eval(dataset, config, callable_fn=run_mod.my_sut, display="none")
    assert log.status == "success"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_template.py -q`
Expected: FAIL — `templates/your-eval/run.py` does not exist.

- [ ] **Step 3: Create the template dataset**

Create `templates/your-eval/dataset.yaml`:

```yaml
# Copy this folder, then edit this file. Each test_case is one challenge for your system.
# Run it (built-in scorer, no code):   uv run agon run templates/your-eval/dataset.yaml --display none
# Run it with YOUR scorer:             uv run agon run --plugin templates/your-eval/scorer.py templates/your-eval/dataset.yaml --display none
name: your_eval_suite
test_cases:
  - test_id: example_001
    name: mentions the capital
    category: your_category          # group cases however you like
    risk_level: low                  # low | medium | high
    input:
      user_message: "What is the capital of France?"
    expected:
      answer_contains: ["Paris"]     # keyword_containment checks these appear
    scoring:
      - {type: keyword_containment, weight: 1.0, pass_threshold: 1.0}
      # To use YOUR scorer (scorer.py) instead, register it there and swap in:
      # - {type: my_scorer, weight: 1.0, pass_threshold: 1.0}
    failure_labels: [missing_keyword]
    tags: [example]

  - test_id: example_002
    name: refuses an unanswerable question
    category: your_category
    risk_level: low
    input:
      user_message: "What is the capital of the Moon?"
    expected:
      answer_contains: ["no", "not"]
    scoring:
      - {type: keyword_containment, weight: 1.0, pass_threshold: 0.5}
    failure_labels: [missing_keyword]
    tags: [example, robustness]
```

- [ ] **Step 4: Create the scorer stub**

Create `templates/your-eval/scorer.py`:

```python
"""Your custom scorer. Register it here, then use it via:
    uv run agon run --plugin templates/your-eval/scorer.py templates/your-eval/dataset.yaml

A scorer maps (AgonCase, SUTResponse, ScoringSpec) -> ScoreOutcome with a normalized_score in
[0.0, 1.0]. Keep the comparison logic pure and unit-test it (see test_scorer.py).
"""

from __future__ import annotations

from agon.scoring.base import ScoreOutcome, register


@register
class MyScorer:
    scorer_type = "my_scorer"      # TODO: rename; must match `type:` in dataset.yaml
    requires_judge = False         # set True only if you need an LLM judge (real provider)

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        # TODO: replace this stub. Compare response.final_answer against
        # case.expected.* and/or spec.params.*, then normalize to [0.0, 1.0].
        expected = (case.expected.expected_answer or "").strip().lower()
        actual = response.final_answer.strip().lower()
        passed = bool(expected) and expected in actual
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[] if passed else ["my_failure_label"],  # TODO: your failure labels
        )
```

- [ ] **Step 5: Create the scorer boundary test (teaching artifact)**

Create `templates/your-eval/test_scorer.py`:

```python
"""Boundary test for your scorer. Run from this folder:  uv run pytest test_scorer.py
(Not collected by the agon suite — testpaths=["tests"] — it ships as an example to copy.)
"""

from __future__ import annotations

from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
from agon.sut import SUTResponse

from scorer import MyScorer


def _case(expected: str) -> AgonCase:
    return AgonCase(
        test_id="t1",
        name="t",
        category="c",
        input={"user_message": "q"},
        expected=ExpectedBehavior(expected_answer=expected),
        scoring=[ScoringSpec(type="my_scorer")],
    )


async def test_pass():
    out = await MyScorer().score(
        _case("paris"), SUTResponse(final_answer="The capital is Paris."), ScoringSpec(type="my_scorer")
    )
    assert out.normalized_score == 1.0


async def test_fail():
    out = await MyScorer().score(
        _case("paris"), SUTResponse(final_answer="I don't know."), ScoringSpec(type="my_scorer")
    )
    assert out.normalized_score == 0.0
    assert out.labels == ["my_failure_label"]
```

- [ ] **Step 6: Create the SUT adapter stub**

Create `templates/your-eval/sut_adapter.py`:

```python
"""Your System-Under-Test adapter: an async function mapping a request to a response.

The harness calls this once per test case. Put your real system behind it (HTTP call,
in-process model, agent, ...). The CLI cannot wire a Python callable, so use run.py to drive it.
"""

from __future__ import annotations

from agon.sut import SUTRequest, SUTResponse


async def my_sut(req: SUTRequest) -> SUTResponse:
    # req.user_message is the case input; req.documents / req.session_id are also available.
    # TODO: call your system here and return its answer.
    answer = f"echo: {req.user_message}"
    return SUTResponse(final_answer=answer)
```

- [ ] **Step 7: Create the launcher**

Create `templates/your-eval/run.py`:

```python
"""Run your eval offline against your SUT adapter + your scorer.

    uv run python templates/your-eval/run.py

Uses the `callable` adapter (your my_sut). Swap in your real scorer by editing scorer.py;
this launcher imports it so its @register fires.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.task import run_eval

# Make this folder importable, then pull in your scorer (side-effect: registers my_scorer) and
# your SUT adapter. agon imports stay above to satisfy ruff isort; these locals sit after the
# sys.path mutation, hence the E402 noqa.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import scorer  # noqa: E402,F401  (registers my_scorer)
from sut_adapter import my_sut  # noqa: E402


def main() -> None:
    dataset = load_dataset(str(HERE / "dataset.yaml"))
    config = RunConfig(
        system_version="your_eval_v1",
        sut=SUTConfig(adapter="callable"),
        log_dir="logs",
        report_dir="reports",
    )
    log = run_eval(dataset, config, callable_fn=my_sut, display="none")
    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    passed = sum(r.passed for r in digest.records)
    print(f"{dataset.name}: {passed}/{len(digest.records)} passed -> {result['recommendation'].value}")
    for path in result["written"].values():
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Create the template README**

Create `templates/your-eval/README.md`:

```markdown
# Your Eval (copy-me template)

Copy this folder somewhere and edit it to build your own Agon eval. Do it in this order:

1. **`dataset.yaml`** — write your test cases (the only required step). Each case has an
   `input.user_message`, an `expected` block, and one or more `scoring` specs. Start with the
   built-in `keyword_containment` scorer so it runs with no code:

   ```bash
   uv run agon run dataset.yaml --display none
   ```

2. **`scorer.py`** *(optional)* — if no built-in scorer fits, write your own. Edit the `# TODO`s,
   rename `my_scorer`, and reference it in `dataset.yaml` (`type: my_scorer`). Run it via the
   plugin loader (no need to fork agon):

   ```bash
   uv run agon run --plugin scorer.py dataset.yaml --display none
   ```

3. **`test_scorer.py`** — every scorer earns a boundary test (a pass case and a fail case).
   Run it from this folder: `uv run pytest test_scorer.py`.

4. **`sut_adapter.py` + `run.py`** *(optional)* — to evaluate **your** system instead of the mock,
   put it behind `my_sut` and drive the whole eval from Python (the CLI can't wire a callable):

   ```bash
   uv run python run.py
   ```

See `docs/extending.md` for the full contract of each extension point, and
`examples/text_to_sql/` for a complete worked example with a real custom scorer.
```

- [ ] **Step 9: Run the rot-guard test + verify the launcher**

Run: `uv run pytest tests/test_template.py -q`
Expected: PASS.
Run: `uv run python templates/your-eval/run.py`
Expected: prints a `your_eval_suite: N/2 passed -> ...` line; exit 0.

- [ ] **Step 10: Lint + commit**

Run: `uv run ruff check templates/your-eval tests/test_template.py`
Expected: `All checks passed!`
(If ruff flags the template's `import scorer` / `from sut_adapter import my_sut` as unsorted/first-party, the `# noqa: E402` on the deferred imports already covers ordering after `sys.path` mutation; keep them.)

```bash
git add templates/your-eval tests/test_template.py
git commit -m "feat(template): copy-me your-eval skeleton (dataset/scorer/adapter/run)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: extension guide `docs/extending.md`

**Files:**
- Create: `docs/extending.md`

- [ ] **Step 1: Write the guide**

Create `docs/extending.md` with the following content (three surfaces; each: contract -> minimal example -> how to run -> the test you owe):

```markdown
# Extending Agon

Agon has three extension surfaces. Pick the smallest one that does the job:

| You want to...                                  | Surface        | Code? |
|-------------------------------------------------|----------------|-------|
| Add new test cases                              | a **dataset**  | No (YAML) |
| Score answers in a way the built-ins can't      | a **scorer**   | Yes (~30 lines) |
| Evaluate **your own** system, not the mock      | a **SUT adapter** | Yes (one function) |

A copy-me skeleton for all three lives in `templates/your-eval/`. A complete worked example
(with a real custom scorer) lives in `examples/text_to_sql/`.

## 1. Add a dataset (no code)

A dataset is a YAML file: a `name` plus a list of `test_cases`. Each case:

- `test_id` (unique, `[a-z0-9_-]`), `name`, `category`, optional `risk_level` (low|medium|high)
- `input.user_message` — the challenge given to the system
- `expected` — references the scorer checks (`expected_answer`, `answer_contains`,
  `allowed_sources`, `citation_required`, `json_schema`, ...)
- `scoring` — one or more `{type, weight, pass_threshold, params}` specs; `type` must name a
  registered scorer (`uv run agon run --help` lists the built-ins, or see `agon/scoring/`)
- `failure_labels` — the labels a failing case may surface (intersected with what scorers emit)

Run and validate it:

    uv run agon run path/to/your_dataset.yaml --display none

Built-in scorers include `exact_match`, `keyword_containment`, `citation_check`, `json_schema`,
and judge-backed ones (`rubric_judge`, `safety_judge`, ...) that need a real provider. See
`examples/datasets/rag_smoke.yaml` for a 20-case reference.

**The test you owe:** none for data alone — but if a case encodes a real failure you found, that
*is* the regression test (failure is data).

## 2. Add a scorer (Python)

A scorer is a class with `scorer_type`, `requires_judge`, and an async `score(...)` that returns a
normalized `ScoreOutcome`. Register it with `@register`:

```python
from agon.scoring.base import ScoreOutcome, register


@register
class MyScorer:
    scorer_type = "my_scorer"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        passed = ...  # compare response.final_answer to case.expected / spec.params
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[] if passed else ["my_failure_label"],
        )
```

`ScoreOutcome` fields: `scorer_type`, `native_score` (raw value), `normalized_score` (0..1, the
number that gates the case), `labels` (failure labels), `rationale`, `details`.

**Use it from the CLI** without touching agon's source — point `--plugin` at your module (a dotted
name on `sys.path`) or your `.py` file:

    uv run agon run --plugin my_scorers.py path/to/dataset.yaml --display none

(`--plugin` is repeatable. If a dataset names a scorer that isn't registered, `agon run` aborts
with a list of registered types and a reminder to pass `--plugin`.)

**Worked example:** `examples/text_to_sql/sql_scorer.py` implements `sql_result_match`, which runs
both the candidate and reference SQL against an in-memory SQLite DB and compares result rows — so
two different-but-equivalent queries both pass, where `exact_match` would wrongly fail one.

**The test you owe:** a boundary test asserting the normalized score at a pass case and a fail case
(and any special path, e.g. malformed input). Keep the comparison logic a pure function so it's
testable without the harness — see `compare_sql` in the text-to-SQL example and its tests in
`tests/test_text_to_sql.py`.

## 3. Add a SUT adapter (evaluate your own system)

The System Under Test is reached through a normalized contract: an async function
`(SUTRequest) -> SUTResponse`.

```python
from agon.sut import SUTRequest, SUTResponse


async def my_sut(req: SUTRequest) -> SUTResponse:
    answer = call_my_system(req.user_message, req.documents)
    return SUTResponse(final_answer=answer, citations=[...])
```

`SUTRequest`: `user_message`, `documents`, `session_id`, `config_overrides`.
`SUTResponse`: `final_answer`, `citations`, `tool_calls`, `retrieved_documents`, `token_usage`, ...

The CLI cannot wire a Python callable, so drive the eval from a short launcher script (the
`callable` adapter):

```python
from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.task import run_eval

dataset = load_dataset("your_dataset.yaml")
config = RunConfig(sut=SUTConfig(adapter="callable"))
log = run_eval(dataset, config, callable_fn=my_sut, display="none")
generate_reports(log, config=config, out_dir="reports")
```

For an HTTP system you don't need a callable at all — set `adapter="http"`, `endpoint_url`, and a
`field_map` on `SUTConfig` and run from the CLI. See `examples/quickstart.py` (callable) and
`docs/running-real-evals.md` (providers/HTTP).

**The test you owe:** if your adapter does non-trivial mapping (HTTP JSON -> `SUTResponse`), test
that mapping on a representative payload.
```

- [ ] **Step 2: Sanity-check the doc commands**

Run: `uv run agon run templates/your-eval/dataset.yaml --display none --log-dir "$TMPDIR/l" --report-dir "$TMPDIR/r"` (PowerShell: `$env:TEMP`).
Expected: runs (exit 0 or 1 depending on mockllm answers) — confirms the documented "no code" command is valid.

- [ ] **Step 3: Commit**

```bash
git add docs/extending.md
git commit -m "docs(extending): three-surface extension guide

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `CONTRIBUTING.md` + README/CLAUDE wiring

**Files:**
- Create: `CONTRIBUTING.md`
- Modify: `README.md` (Contributing section ~line 297-299; roadmap; command list under Quickstart)
- Modify: `CLAUDE.md` (layout note; a `--plugin` line)

- [ ] **Step 1: Create CONTRIBUTING.md**

Create `CONTRIBUTING.md`:

```markdown
# Contributing to Agon

Thanks for extending the harness. A documented failure mode or a new eval is as valuable here as a
feature — **failure is data**: when you find a way a system breaks, add the case that catches it.

## Dev setup

```bash
uv sync                                   # Python pinned to 3.12 via .python-version
uv run pytest                             # full suite, fully offline (mockllm)
uv run ruff check agon tests              # lint (line-length 100)
```

Everything must run **offline** by default — no API key, no model downloads — via Inspect's
`mockllm/model` provider. Real-provider and semantic-scorer paths are opt-in extras. A reviewer
should be able to clone and run the harness in under 20 minutes; keep examples within that budget.

## Principles (these shape every change)

- **Failure is data, not noise.** Fix a failure mode *and* add the regression case to a dataset.
- **Evidence over claims.** Back results with metrics, traces, reproducible runs — never assertions.
- **Retrieval is isolated from generation.** recall@k / MRR are measured by `agon retrieve`,
  independently of answer quality. Don't conflate them in one score.
- **No single-number obsession.** The evaluation categories are tracked distinctly.

## Adding things

See **`docs/extending.md`** for the three extension surfaces (dataset, scorer, SUT adapter) and
**`templates/your-eval/`** for a copy-me skeleton. In short:

- New **scorer**: a class with `@register` (see `agon/scoring/`); usable from the CLI via
  `agon run --plugin <module-or-file> <dataset.yaml>`. Every scorer earns a **boundary test**
  asserting its normalized score at pass/fail; keep the core comparison a pure function.
- New **dataset**: a YAML file of `test_cases` (validated by `agon run`).
- New **SUT adapter**: an async `(SUTRequest) -> SUTResponse`, driven from a launcher script.

## Decisions & ADRs

Architectural decisions are recorded under `docs/decisions/ADR-NNNN-*.md`. If your change makes a
non-obvious trade-off (a new dependency, a contract, a default), add an ADR.

## Commits & PRs

- Stage only the files your change touches (`git add <paths>`), not `git add .` — the tree carries
  unrelated untracked artifacts.
- Create new commits rather than amending; don't skip hooks.
- Don't push or open a PR unless asked; the maintainer merges.

## Definition of done

`uv run pytest` green, `uv run ruff check agon tests` clean, a boundary test for any new scorer,
and — if you fixed a failure — the case that reproduces it added to a dataset.
```

- [ ] **Step 2: Update README Contributing section**

In `README.md`, replace the Contributing paragraph (the sentence "A `CONTRIBUTING.md` will accompany the Phase 1 release."):

Find:
```markdown
Contributions, adversarial test cases, and documented failure modes are all welcome — a good failure report is as valuable here as a working feature. A `CONTRIBUTING.md` will accompany the Phase 1 release.
```
Replace with:
```markdown
Contributions, adversarial test cases, and documented failure modes are all welcome — a good failure report is as valuable here as a working feature. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for dev setup and conventions, and **[docs/extending.md](docs/extending.md)** for how to add your own dataset, scorer, or SUT adapter. Start from the copy-me skeleton in [`templates/your-eval/`](templates/your-eval/).
```

- [ ] **Step 3: Add a `--plugin` line to the README command list**

In `README.md`, in the Quickstart command block (after the offline OWASP line at ~line 268), add:

```bash
# 10. Run a brand-new-domain eval (text-to-SQL) with a custom scorer loaded via --plugin.
uv run python examples/text_to_sql/run.py        # offline: 4/6 pass (equivalent SQL passes, wrong/malformed fail)
uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml --display none
#    -> custom `sql_result_match` scorer compares result rows, not SQL strings
```

- [ ] **Step 4: Update CLAUDE.md**

In `CLAUDE.md`, update the "Key layout" line to mention `templates/` and add a one-line note about `--plugin`. Find the layout sentence (ends `...config,cli,cost,observability,stats}`) and after it (in the same paragraph that mentions registering a scorer) append:

```markdown
Custom scorers can be loaded without editing the package via `agon run --plugin <module-or-.py>`
(see `docs/extending.md`); a copy-me skeleton lives in `templates/your-eval/`.
```

- [ ] **Step 5: Verify links resolve + commit**

Run: `uv run python -c "import pathlib; [print(p, pathlib.Path(p).exists()) for p in ['CONTRIBUTING.md','docs/extending.md','templates/your-eval/README.md','examples/text_to_sql/run.py']]"`
Expected: each prints `True`.

```bash
git add CONTRIBUTING.md README.md CLAUDE.md
git commit -m "docs(contributing): CONTRIBUTING.md + README/CLAUDE extension wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: ADR-0008 — extensibility contract

**Files:**
- Create: `docs/decisions/ADR-0008-extensibility-contract.md`

- [ ] **Step 1: Write the ADR**

Create `docs/decisions/ADR-0008-extensibility-contract.md`:

```markdown
# ADR-0008: Extensibility contract and the `--plugin` loader

**Status:** Accepted · **Date:** 2026-06-06 · **Milestone:** Phase 3 M7

## Context

The harness had three extension points in code but no documented contract and one real gap: a
user's own scorer was invisible to `agon run` (the CLI resolves scorers through the global
`default_registry`, populated only by side-effect imports in `agon/scoring/__init__.py`). The only
way to use a custom scorer was to fork that file or write a launcher script.

## Decision

1. **The three extension surfaces are the stable public contract:**
   - **Dataset** — the YAML `test_cases` schema (`AgonCase` / `ScoringSpec` / `ExpectedBehavior`).
   - **Scorer** — the `AgonScorer` protocol + the `@register` / `default_registry` mechanism,
     returning a normalized `ScoreOutcome`.
   - **SUT adapter** — the `callable` solver, i.e. an async `(SUTRequest) -> SUTResponse`.
2. **`agon run --plugin <spec>` (repeatable)** imports external scorer modules before the task
   builds, so their `@register` side-effects land on `default_registry`. A spec is a dotted module
   name **or** a path to a `.py` file. A pre-flight check aborts (exit 2) with a helpful message if a
   dataset references an unregistered scorer.
3. **Onboarding is docs + a static template + one worked example**, not a generator: a copy-me
   `templates/your-eval/`, a `docs/extending.md` guide, a `CONTRIBUTING.md`, and a brand-new-domain
   example (`examples/text_to_sql/`) whose custom `sql_result_match` scorer compares result rows.

## Alternatives considered

- **`agon new` scaffolding command** — rejected (YAGNI; a static folder needs no code/tests and can't
  drift from the runtime).
- **setuptools entry-point plugin discovery** — deferred. `--plugin` covers the need explicitly;
  entry-point auto-discovery of installed `agon.scorers` packages can be added later without breaking
  the flag.
- **Shipping `sql_result_match` as a built-in** — rejected. It is domain-specific and lives in the
  example, loaded via `--plugin`, precisely to demonstrate extending from your own code.

## Consequences

- A newcomer can stand up a new eval — dataset, scorer, and their own system — from a copy-me folder
  and one guide, and run it from the CLI. The three surfaces are documented and stable, so future
  milestones extend rather than re-invent.
- `--plugin` is a small, well-bounded surface; the example proves the project's thesis in miniature
  (a naive scorer is wrong here; the right custom scorer is a few dozen lines). Still zero new
  dependencies, still fully offline.
```

- [ ] **Step 2: Commit**

```bash
git add docs/decisions/ADR-0008-extensibility-contract.md
git commit -m "docs(adr): ADR-0008 extensibility contract + --plugin loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Final verification (whole milestone)

**Files:** none (verification only)

- [ ] **Step 1: Full suite + lint**

Run: `uv run ruff check agon tests && uv run pytest -q`
Expected: `All checks passed!` and all tests pass (prior baseline 168 passed, 1 skipped; this milestone adds ~16 tests across `test_plugins.py`, `test_cli_plugin.py`, `test_text_to_sql.py`, `test_template.py` — expect ~184 passed, 1 skipped). No failures.

- [ ] **Step 2: Offline integration commands (the onboarding paths a reviewer will try)**

Run each; all must succeed offline:

```bash
uv run python examples/text_to_sql/run.py                 # -> text_to_sql_suite: 4/6 passed
uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml --display none --log-dir logs --report-dir reports   # prints "loaded plugin scorers: sql_result_match"
uv run python templates/your-eval/run.py                  # -> your_eval_suite: N/2 passed
uv run agon run templates/your-eval/dataset.yaml --display none --log-dir logs --report-dir reports   # built-in scorer path
```

Expected: the first prints `4/6 passed`; the second prints the `loaded plugin scorers:` line and does **not** abort (exit 2); the launchers print a pass line and exit 0.
Clean up any `logs/` `reports/` created in the repo root afterward (do not commit them).

- [ ] **Step 3: Confirm no stray files staged**

Run: `git status --short`
Expected: only intended new files are tracked; the pre-existing banner-PNG deletions and untracked `docs/*.docx` / `HANDOFF.md` remain **unstaged** (never add them).

- [ ] **Step 4: Branch is ready for review**

This is the end of the build. Hand off to the holistic reviewer (per the working rhythm) before pushing / opening the PR. Do not push or open the PR unless the maintainer asks.

---

## Self-review notes (plan vs spec)

- **Spec Unit A (`--plugin` loader)** -> Tasks 1-2. The spec's "sharpen the `ScorerRegistry.get`
  message" is realized instead as a **CLI pre-flight check** (Task 2): cleaner layering (the
  `--plugin` hint is a CLI concern, not a core-registry concern) and it makes the hint land
  deterministically on `agon run` rather than buried in a per-sample error. Behavior for valid
  datasets is unchanged.
- **Spec Unit B (template)** -> Task 5. **Unit C (text-to-SQL)** -> Tasks 3-4. **Unit D
  (extending.md)** -> Task 6. **Unit E (CONTRIBUTING + README/CLAUDE)** -> Task 7. **ADR-0008** ->
  Task 8.
- **Decision 3a** (scorer ships only in the example, not the built-in registry) is honored: it is
  registered via the example module / `--plugin`, never added to `agon/scoring/__init__.py`.
- **Offline / ASCII / no-new-deps** honored throughout (stdlib `sqlite3`, `importlib`; ASCII CLI
  strings; no extras).
- **Types are consistent across tasks:** `load_plugins`/`PluginLoadError` (Task 1) are imported in
  Task 2; `compare_sql`/`SqlResultMatchScorer` (Task 3) are exercised in Task 4; `my_sut`/`MyScorer`
  (Task 5) match the template test and launcher.
```
