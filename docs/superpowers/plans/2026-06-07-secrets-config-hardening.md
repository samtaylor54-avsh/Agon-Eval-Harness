# Secrets & Config Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agon safe to run against real providers and safe to share its artifacts — a real key never lands in any artifact agon writes, a missing key fails fast, and config/secret state is introspectable without leaking.

**Architecture:** A new pure-function module `agon/secrets.py` (masking, hybrid redaction, provider→env preflight) plus `agon/config.load_env()`. The CLI loads `.env` at entry, validates provider keys before real runs, and gains an `agon doctor` command. Redaction is applied at the artifact emission boundaries: report serialization (`agon/reporting/generator.py`) and OTel span free-text values (`agon/observability/exporter.py`).

**Tech Stack:** Python 3.12, Typer, Pydantic, python-dotenv (promoted to a direct dep; already installed transitively at 1.2.2), Inspect AI, pytest, ruff (line-length 100).

**Conventions (from CLAUDE.md / HANDOFF):**
- **ASCII-only** in any string printed by the CLI (`typer.echo`) — mask separator is `...`, abort arrows are `-> `; no `…`/`→`/`—`/`±`. Docstrings/markdown/jinja may be UTF-8.
- **Targeted `git add` ONLY** — stage each task's own files. NEVER `git add .`/`-A` (the tree carries pre-existing `*.png` deletions and untracked `docs/*.docx`, `reports2/`, `HANDOFF.md`).
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- TDD: failing test first, then minimal code. Run `uv run ruff check agon tests` before each commit.

---

## File Structure

- **Create** `agon/secrets.py` — masking, redaction, provider-key preflight (pure; reads `os.environ` only).
- **Create** `agon/config/env.py` — `load_env()` (.env loader); re-exported from `agon/config/__init__.py`.
- **Modify** `agon/cli/app.py` — `@app.callback()` loads `.env`; `_preflight()` helper; wire preflight into `run`/`resume`/`calibrate`; new `doctor` command.
- **Modify** `agon/reporting/generator.py` — redact artifact strings before write.
- **Modify** `agon/observability/exporter.py` — redact span free-text values (score value, tool error).
- **Modify** `pyproject.toml` — add `python-dotenv` to `dependencies`.
- **Create** `docs/decisions/ADR-0010-secrets-config-hardening.md`.
- **Modify** `docs/running-real-evals.md` — `.env` usage + `agon doctor`.
- **Create tests:** `tests/test_secrets.py`, `tests/test_env_loading.py`, `tests/test_doctor.py`, `tests/test_preflight_cli.py`, `tests/test_redaction_artifacts.py`. **Extend:** `tests/test_observability.py`.

---

## Task 1: `agon/secrets.py` — constants, `mask()`, `secret_values()`

**Files:**
- Create: `agon/secrets.py`
- Test: `tests/test_secrets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_secrets.py
"""Phase 3 M9 — secret masking, redaction, and provider-key preflight."""

from agon import secrets


def test_mask_known_prefix_keeps_prefix_and_last4():
    assert secrets.mask("sk-ant-ABCDEFGHIJKLMNOP1234") == "sk-ant-...1234"


def test_mask_generic_long_value_uses_first3_and_last4():
    assert secrets.mask("ABCDEFGHIJKLMNOP") == "ABC...MNOP"


def test_mask_empty_or_none_is_not_set():
    assert secrets.mask("") == "(not set)"
    assert secrets.mask(None) == "(not set)"


def test_mask_short_value_is_fully_hidden():
    assert secrets.mask("short") == "***"


def test_secret_values_collects_set_env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-LIVEKEY0000000000")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")  # whitespace-only -> ignored
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    vals = secrets.secret_values()
    assert "sk-ant-LIVEKEY0000000000" in vals
    assert "   " not in vals
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agon.secrets'`.

- [ ] **Step 3: Write minimal implementation**

```python
# agon/secrets.py
"""Secret masking, redaction, and provider-key preflight (Phase 3 M9).

agon stores no secrets. These are read-only transforms over ``os.environ`` and arbitrary text so a
real key never lands in an artifact and a missing provider key fails fast with a clear message.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

# Env vars whose VALUES are secrets — redacted precisely wherever they appear.
KNOWN_SECRET_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "TOGETHER_API_KEY",
    "HF_TOKEN",
)

# Recognizable key prefixes — the pattern backstop for a key that arrives by another path.
# Order matters: longer/more-specific prefixes first (mask() and the regex try them in order).
KNOWN_KEY_PREFIXES: tuple[str, ...] = ("sk-ant-", "sk-", "lsv2_", "ls__", "hf_", "gsk_")

# provider (first segment of a model string) -> env var(s) that must be present for a real run.
PROVIDER_ENV: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "google": ("GOOGLE_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "together": ("TOGETHER_API_KEY",),
}

_MIN_MASK_LEN = 8
# prefix followed by >=16 chars of key body (base64/hex/url-safe).
_PREFIX_TOKEN_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in KNOWN_KEY_PREFIXES) + r")[A-Za-z0-9_\-]{16,}"
)


def mask(value: str | None) -> str:
    """Return a non-reconstructable label for a secret. ASCII only (cp1252 console).

    empty/None -> ``(not set)``; <8 chars -> ``***``; known prefix -> ``<prefix>...<last4>``;
    otherwise ``<first3>...<last4>``.
    """
    if not value:
        return "(not set)"
    if len(value) < _MIN_MASK_LEN:
        return "***"
    for prefix in KNOWN_KEY_PREFIXES:
        if value.startswith(prefix):
            return f"{prefix}...{value[-4:]}"
    return f"{value[:3]}...{value[-4:]}"


def secret_values() -> set[str]:
    """Current non-empty values of the known secret env vars (the precise redaction set)."""
    out: set[str] = set()
    for var in KNOWN_SECRET_ENV_VARS:
        value = os.environ.get(var)
        if value and value.strip():
            out.add(value)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: 5 passed.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/secrets.py tests/test_secrets.py
git commit -m "feat(secrets): mask() + secret_values() with known key constants

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `agon/secrets.py` — `redact()`

**Files:**
- Modify: `agon/secrets.py`
- Test: `tests/test_secrets.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_secrets.py`)**

```python
def test_redact_replaces_env_set_secret_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-PROJ1234567890abcdef")
    text = "calling provider with key sk-PROJ1234567890abcdef now"
    out = secrets.redact(text)
    assert "sk-PROJ1234567890abcdef" not in out
    assert "sk-...cdef" in out


def test_redact_prefix_backstop_without_env(monkeypatch):
    for var in secrets.KNOWN_SECRET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    text = "leaked sk-ant-ABCDEFGHIJKLMNOP1234 in a trace"
    out = secrets.redact(text)
    assert "sk-ant-ABCDEFGHIJKLMNOP1234" not in out
    assert "sk-ant-...1234" in out


def test_redact_leaves_innocent_text_untouched(monkeypatch):
    for var in secrets.KNOWN_SECRET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    text = "the sky is blue and 2 + 2 = 4"
    assert secrets.redact(text) == text


def test_redact_is_idempotent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ZZZZZZZZZZZZZZZZ9999")
    once = secrets.redact("key=sk-ant-ZZZZZZZZZZZZZZZZ9999")
    assert secrets.redact(once) == once


def test_redact_empty_string_is_safe():
    assert secrets.redact("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_secrets.py -k redact -v`
Expected: FAIL with `AttributeError: module 'agon.secrets' has no attribute 'redact'`.

- [ ] **Step 3: Write minimal implementation (append to `agon/secrets.py`)**

```python
def redact(text: str, *, extra: Iterable[str] = ()) -> str:
    """Mask every known secret occurring in ``text``. Hybrid: exact env values + prefix backstop.

    Idempotent: a masked value (``sk-ant-...1234``) contains ``.`` so the prefix regex won't re-match
    it, and the original value is already gone after the exact-replace pass.
    """
    if not text:
        return text
    # Exact env-set values first, longest-first so a short value can't pre-empt a longer one.
    candidates = secret_values() | {e for e in extra if e}
    for secret in sorted(candidates, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, mask(secret))
    # Backstop: mask prefix+entropy tokens that arrived by another path.
    return _PREFIX_TOKEN_RE.sub(lambda m: mask(m.group(0)), text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: all passed (Task 1 + Task 2 tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/secrets.py tests/test_secrets.py
git commit -m "feat(secrets): hybrid redact() (env values + prefix backstop)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `agon/secrets.py` — `missing_provider_keys()` + `secret_status()`

**Files:**
- Modify: `agon/secrets.py`
- Test: `tests/test_secrets.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_secrets.py`)**

```python
def test_missing_provider_keys_offline_adapter_is_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert secrets.missing_provider_keys("mockllm/model", "mockllm") == []
    assert secrets.missing_provider_keys(None, "http") == []


def test_missing_provider_keys_real_provider_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert secrets.missing_provider_keys("anthropic/claude-x", "litellm") == ["ANTHROPIC_API_KEY"]


def test_missing_provider_keys_real_provider_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PRESENT0000000000")
    assert secrets.missing_provider_keys("anthropic/claude-x", "litellm") == []


def test_missing_provider_keys_whitespace_value_treated_as_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    assert secrets.missing_provider_keys("openai/gpt-4o", "litellm") == ["OPENAI_API_KEY"]


def test_missing_provider_keys_unknown_provider_not_blocked(monkeypatch):
    assert secrets.missing_provider_keys("acme/model", "litellm") == []


def test_secret_status_masks_set_and_marks_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-STATUS00000000000")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = dict(secrets.secret_status())
    assert status["ANTHROPIC_API_KEY"] == "sk-ant-...0000"
    assert status["OPENAI_API_KEY"] == "(not set)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_secrets.py -k "provider or status" -v`
Expected: FAIL with `AttributeError` on `missing_provider_keys`.

- [ ] **Step 3: Write minimal implementation (append to `agon/secrets.py`)**

```python
def missing_provider_keys(model: str | None, adapter: str) -> list[str]:
    """Env vars required by ``model``'s provider that are unset/empty. Empty list = OK.

    Offline adapters (anything other than ``litellm``) need no key. An unmapped provider is not
    blocked — we only assert keys for providers we know how to map.
    """
    if adapter != "litellm" or not model:
        return []
    provider = model.split("/")[0].lower()
    required = PROVIDER_ENV.get(provider)
    if not required:
        return []
    return [var for var in required if not (os.environ.get(var) or "").strip()]


def secret_status() -> list[tuple[str, str]]:
    """``(env_var, masked_value_or_'(not set)')`` over the known secret vars — for ``agon doctor``."""
    return [(var, mask(os.environ.get(var))) for var in KNOWN_SECRET_ENV_VARS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: all passed.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/secrets.py tests/test_secrets.py
git commit -m "feat(secrets): missing_provider_keys() + secret_status() for preflight/doctor

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `agon/config.load_env()` + precedence

**Files:**
- Create: `agon/config/env.py`
- Modify: `agon/config/__init__.py`
- Modify: `pyproject.toml` (add `python-dotenv` to `dependencies`)
- Test: `tests/test_env_loading.py`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add to the `dependencies` list (after `"rouge-score>=0.1.2",`):

```toml
    "python-dotenv>=1.0",
```

Then run `uv sync` (no new download — 1.2.2 is already installed transitively).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_env_loading.py
"""Phase 3 M9 — .env loading at CLI entry; process env wins over .env."""

import os

from agon.config import load_env


def test_load_env_reads_dotenv_from_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("AGON_M9_PROBE", raising=False)
    (tmp_path / ".env").write_text("AGON_M9_PROBE=from_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    loaded = load_env()
    assert loaded is not None
    assert os.environ["AGON_M9_PROBE"] == "from_dotenv"


def test_load_env_does_not_override_process_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGON_M9_PROBE", "from_process")
    (tmp_path / ".env").write_text("AGON_M9_PROBE=from_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    load_env()
    assert os.environ["AGON_M9_PROBE"] == "from_process"


def test_load_env_no_dotenv_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # tmp_path has no .env and (being a temp dir) no ancestor .env.
    assert load_env() is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_env_loading.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_env' from 'agon.config'`.

- [ ] **Step 4: Write minimal implementation**

```python
# agon/config/env.py
"""Load a .env at CLI entry so preflight/doctor see those keys (Inspect only loads it at eval time).

Process env always wins (``override=False``); a real shell-exported key is never clobbered by a
stale .env.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv


def load_env() -> str | None:
    """Load a .env from the cwd, walking up the tree. Return its path, or None if none found."""
    path = find_dotenv(usecwd=True)
    if not path:
        return None
    load_dotenv(path, override=False)
    return path
```

```python
# agon/config/__init__.py  (replace the file)
"""Run configuration loading (TOML / YAML / JSON) and .env loading."""

from agon.config.env import load_env
from agon.config.loader import load_run_config

__all__ = ["load_env", "load_run_config"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_env_loading.py -v`
Expected: 3 passed.

> Note: `find_dotenv(usecwd=True)` walks up the directory tree. The `returns_none` test relies on `tmp_path` having no ancestor `.env`; pytest's tmp dirs live outside the repo, so this holds.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/config/env.py agon/config/__init__.py pyproject.toml tests/test_env_loading.py
git commit -m "feat(config): load_env() (.env at CLI entry, process env wins); python-dotenv dep

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CLI — `.env` callback + `_preflight()` wired into run/resume/calibrate

**Files:**
- Modify: `agon/cli/app.py`
- Test: `tests/test_preflight_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preflight_cli.py
"""Phase 3 M9 — preflight aborts a real-provider run with a missing key; offline path unaffected."""

from pathlib import Path

from typer.testing import CliRunner

from agon.cli import app
from agon.cli.app import _preflight

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_preflight_helper_aborts_on_missing_key(monkeypatch):
    import typer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    raised = False
    try:
        _preflight("anthropic/claude-x", "litellm")
    except typer.Exit as exc:
        raised = True
        assert exc.exit_code == 2
    assert raised


def test_preflight_helper_passes_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _preflight("mockllm/model", "mockllm")  # no raise


def test_run_aborts_when_real_provider_key_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "run", str(FIXTURES / "mini.yaml"),
            "--model", "anthropic/claude-sonnet-4-5",
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(tmp_path / "reports"),
            "--display", "none",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "ANTHROPIC_API_KEY" in result.output
    assert "anthropic" in result.output
    # aborted before any network/log was written
    assert not (tmp_path / "logs").exists() or not list((tmp_path / "logs").glob("*.eval"))
```

> `_preflight` raises `typer.Exit`; `CliRunner` turns the exit into `result.exit_code`. The abort message goes to stderr, which `CliRunner` (default `mix_stderr=True`) folds into `result.output`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preflight_cli.py -v`
Expected: FAIL with `ImportError: cannot import name '_preflight'`.

- [ ] **Step 3: Write minimal implementation**

In `agon/cli/app.py`, add the `.env` callback (place directly after the `app = typer.Typer(...)` line and the exit-code constants, before `_parse_fail_on_error`):

```python
@app.callback()
def _load_env_callback() -> None:
    """Load a .env at CLI entry so preflight/doctor see those keys."""
    from agon.config import load_env

    load_env()


def _preflight(model: str | None, adapter: str) -> None:
    """Abort (exit 2) if a real-provider run is missing its required API key(s)."""
    from agon.secrets import missing_provider_keys

    missing = missing_provider_keys(model, adapter)
    if missing:
        provider = (model or "").split("/")[0]
        typer.echo(
            f"[abort] missing API key for provider '{provider}': {', '.join(missing)} "
            f"(set it in your shell or a .env file)",
            err=True,
        )
        raise typer.Exit(ABORT)
```

In `run`, add the preflight call immediately **before** the `health_check` block (after the `_validate_scorers` block, before `if not anyio.run(health_check, cfg.sut):`):

```python
    _preflight(cfg.sut.model, cfg.sut.adapter)

```

In `resume`, add it immediately **before** the `try: result = resume_run(...)` block (after the `target = None if latest else run_id` line):

```python
    _preflight(cfg.sut.model, cfg.sut.adapter)

```

In `calibrate`, add it as the **first** statement of the function body (the function signature ends at `min_kappa: ...`; insert before the existing body):

```python
    _preflight(judge_model, "mockllm" if judge_model.startswith("mockllm") else "litellm")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_preflight_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Regression — offline run still works**

Run: `uv run pytest tests/test_cli.py tests/test_cli_resume.py tests/test_calibrate.py -q`
Expected: all passed (the offline mockllm path is unaffected — preflight returns `[]`).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/cli/app.py tests/test_preflight_cli.py
git commit -m "feat(cli): load .env at entry; preflight provider keys in run/resume/calibrate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: CLI — `agon doctor` command

**Files:**
- Modify: `agon/cli/app.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_doctor.py
"""Phase 3 M9 — `agon doctor` masks secrets and never prints a raw key."""

from typer.testing import CliRunner

from agon.cli import app

runner = CliRunner()


def test_doctor_masks_set_key_and_marks_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-DOCTORKEY00000000")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "sk-ant-DOCTORKEY00000000" not in result.output  # raw key never printed
    assert "sk-ant-...0000" in result.output
    assert "OPENAI_API_KEY: (not set)" in result.output


def test_doctor_model_flag_reports_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor", "--model", "anthropic/claude-x"])
    assert result.exit_code == 0, result.output
    assert "MISSING" in result.output
    assert "ANTHROPIC_API_KEY" in result.output


def test_doctor_model_flag_reports_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PRESENTKEY0000000")
    result = runner.invoke(app, ["doctor", "--model", "anthropic/claude-x"])
    assert result.exit_code == 0, result.output
    assert "keys present" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_doctor.py -v`
Expected: FAIL — `doctor` is not a command (exit code 2 / "No such command").

- [ ] **Step 3: Write minimal implementation**

In `agon/cli/app.py`, add a new command (place after the `report` command, before `trace`):

```python
@app.command()
def doctor(
    model: str = typer.Option(None, "--model", help="Check keys for this provider/model"),
    config: str = typer.Option(None, "--config", "-c", help="Show resolved config (redacted)"),
) -> None:
    """Report agon/Inspect versions, masked secret status, and provider-key readiness."""
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    from agon.secrets import missing_provider_keys, redact, secret_status

    def _ver(name: str) -> str:
        try:
            return _pkg_version(name)
        except PackageNotFoundError:
            return "(unknown)"

    typer.echo("agon doctor")
    typer.echo(f"  agon:    {_ver('agon-eval-harness')}")
    typer.echo(f"  inspect: {_ver('inspect-ai')}")
    typer.echo("  default path: offline (mockllm; no API key required)")

    typer.echo("\nsecret env vars:")
    for var, shown in secret_status():
        typer.echo(f"  {var}: {shown}")

    if model:
        adapter = "mockllm" if model.startswith("mockllm") else "litellm"
        provider = model.split("/")[0]
        missing = missing_provider_keys(model, adapter)
        if missing:
            typer.echo(f"\nmodel {model}: provider '{provider}' MISSING {', '.join(missing)}")
        else:
            typer.echo(f"\nmodel {model}: provider '{provider}' keys present")

    if config:
        cfg = load_run_config(config)
        typer.echo("\nresolved config:")
        typer.echo(redact(cfg.model_dump_json(indent=2)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_doctor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/cli/app.py tests/test_doctor.py
git commit -m "feat(cli): agon doctor — masked secret/config introspection (exit 0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Redaction at the report emission boundary

**Files:**
- Modify: `agon/reporting/generator.py`
- Test: `tests/test_redaction_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_redaction_artifacts.py
"""Phase 3 M9 — headline guard: a secret never lands in a written report artifact."""

from pathlib import Path

from typer.testing import CliRunner

from agon.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"

# An sk-ant- prefixed token with a >=16-char body so the prefix backstop catches it.
PLANTED = "sk-ant-ABCDEFGHIJKLMNOP1234"


def _run(tmp_path):
    reports = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "run", str(FIXTURES / "mini.yaml"),
            "--system-version", f"build-{PLANTED}",
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(reports),
            "--display", "none",
        ],
    )
    return reports, result


def test_planted_key_is_redacted_from_all_report_formats(tmp_path):
    reports, result = _run(tmp_path)
    assert result.exit_code in (0, 1), result.output  # gate code, not an abort
    written = list(reports.glob("*.report.md")) + \
        list(reports.glob("*.report.json")) + \
        list(reports.glob("*.report.junit.xml"))
    assert len(written) == 3
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert PLANTED not in text, f"raw key leaked into {path.name}"
    # prove the value actually reached the artifacts (md/json carry system_version) and was masked
    masked_seen = any("sk-ant-...1234" in p.read_text(encoding="utf-8") for p in written)
    assert masked_seen, "masked form not found — redaction path not exercised"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_redaction_artifacts.py -v`
Expected: FAIL — `PLANTED` string is present in md/json (no redaction yet).

- [ ] **Step 3: Write minimal implementation**

In `agon/reporting/generator.py`, add the import near the top (after `from agon.schemas import ...`):

```python
from agon.secrets import redact
```

In `generate_reports`, redact the artifacts immediately after the dict is built and before writing. Replace:

```python
    artifacts = {
        "report.md": render_markdown(d, regression, recommendation),
        "report.json": render_json(d, regression, recommendation),
        "report.junit.xml": render_junit_xml(d),
    }
```

with:

```python
    artifacts = {
        "report.md": render_markdown(d, regression, recommendation),
        "report.json": render_json(d, regression, recommendation),
        "report.junit.xml": render_junit_xml(d),
    }
    # Defense-in-depth: no secret value reaches a written/returned artifact.
    artifacts = {name: redact(content) for name, content in artifacts.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_redaction_artifacts.py -v`
Expected: 1 passed.

- [ ] **Step 5: Regression — reporting tests still pass**

Run: `uv run pytest tests/test_reporting.py tests/test_taxonomy_reporting.py tests/test_stats_reporting.py -q`
Expected: all passed (redact is a no-op on secret-free report text).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/reporting/generator.py tests/test_redaction_artifacts.py
git commit -m "feat(reporting): redact secrets from md/json/junit artifacts before write

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Redaction of OTel span free-text values

**Files:**
- Modify: `agon/observability/exporter.py`
- Test: `tests/test_observability.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_observability.py`)**

```python
def test_score_value_and_tool_error_are_redacted_in_spans(monkeypatch):
    from agon.observability.semconv import AGON_SCORE_VALUE

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SPANLEAK0000000000")
    leak = "model said sk-ant-SPANLEAK0000000000"
    model_event = NS(
        event="model", timestamp=T0, completed=T1, model="openai/gpt-4o",
        output=NS(usage=NS(input_tokens=1, output_tokens=1)),
    )
    tool_event = NS(
        event="tool", timestamp=T0, completed=T1, id="c1", function="search",
        error="boom sk-ant-SPANLEAK0000000000",
    )
    score_event = NS(event="score", timestamp=T0, scorer="agon_scorer", score=NS(value=leak))
    sample = NS(id="s1", events=[model_event, tool_event, score_event])
    log = NS(
        eval=NS(run_id="r1", task="demo", model="openai/gpt-4o", created="2026-01-01T00:00:00"),
        samples=[sample],
    )

    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)
    spans = exporter.get_finished_spans()

    score = next(s for s in spans if s.name.startswith("agon.score"))
    assert "sk-ant-SPANLEAK0000000000" not in score.attributes[AGON_SCORE_VALUE]
    assert "sk-ant-...0000" in score.attributes[AGON_SCORE_VALUE]

    tool = next(s for s in spans if s.name.startswith("execute_tool "))
    assert "sk-ant-SPANLEAK0000000000" not in (tool.status.description or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability.py -k redacted -v`
Expected: FAIL — the raw key is present in the score-value attribute.

- [ ] **Step 3: Write minimal implementation**

In `agon/observability/exporter.py`, add the import (after `from agon.observability.semconv import (...)` block):

```python
from agon.secrets import redact
```

Update `_strval` to redact its output:

```python
def _strval(value: Any) -> str:
    s = json.dumps(value, default=str) if isinstance(value, dict | list) else str(value)
    return redact(s)
```

In `_emit_tool`, redact the error status string. Replace:

```python
    if getattr(e, "error", None):
        span.set_status(Status(StatusCode.ERROR, str(e.error)))
```

with:

```python
    if getattr(e, "error", None):
        span.set_status(Status(StatusCode.ERROR, redact(str(e.error))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_observability.py -v`
Expected: all passed (existing span tests + the new redaction test).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check agon tests
git add agon/observability/exporter.py tests/test_observability.py
git commit -m "feat(observability): redact secrets from span score values + tool errors

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Docs — running-real-evals + ADR-0010

**Files:**
- Modify: `docs/running-real-evals.md`
- Create: `docs/decisions/ADR-0010-secrets-config-hardening.md`

- [ ] **Step 1: Update `docs/running-real-evals.md`**

After the "## 1. Pick a provider + set its key" section (after the `export ANTHROPIC_API_KEY=...` example block), insert:

````markdown
### Use a `.env` instead of exporting (optional)

agon loads a `.env` from the working directory (walking up the tree) at startup. Keep keys out of
your shell history:

```bash
# .env  (gitignored — never commit this)
ANTHROPIC_API_KEY=sk-ant-...
```

Process-environment variables always win over `.env` (a real exported key is never overridden by a
stale file).

### Check readiness before you run

```bash
uv run agon doctor                              # masked status of every known key
uv run agon doctor --model anthropic/claude-sonnet-4-5   # is THIS provider's key present?
```

`doctor` masks every value (`sk-ant-...a3f9`) and never prints a raw key. If a real-provider `run`
is missing its key, agon aborts immediately (exit 2) with the exact env var to set — no provider
stack trace.

> **Secrets are never stored or written.** agon redacts known keys (exact env values plus
> recognizable key prefixes) from every report (md/json/junit) and OpenTelemetry span before it is
> written, so an artifact is safe to share.
````

- [ ] **Step 2: Create the ADR**

```markdown
# ADR-0010: Secrets & Config Hardening

**Status:** Accepted · **Date:** 2026-06-07 · **Milestone:** Phase 3 M9

## Context

agon runs offline by default (`mockllm`, no key). A real-provider run needs a key in the environment,
but the harness did nothing to keep that key out of the artifacts it writes (reports, OTel spans),
nothing to fail fast when the key is absent, and offered no way to see what secret/config state it
resolved. For a harness whose artifacts are meant to be shared as evidence, a leaked key in a
committed report is a real failure mode.

## Decision

Add four offline-first capabilities; store no secrets.

1. **Hybrid redaction** (`agon/secrets.py::redact`) — replace the exact values of known secret env
   vars (precise, zero false positives) plus a backstop pattern of recognizable key prefixes
   (`sk-ant-`, `sk-`, `ls__`, ...) followed by a high-entropy body. Applied at the emission
   boundaries we own: report serialization and OTel span free-text values (score values, tool
   errors).
2. **Preflight validation** (`missing_provider_keys`) — before a real (`litellm`) run, map the
   model's provider to its required env var(s) and abort (exit 2) with a clean ASCII message if
   missing. Offline adapters and unmapped providers are not blocked.
3. **`agon doctor`** — print agon/Inspect versions, masked per-key status, and provider readiness;
   exit 0; never prints a raw key.
4. **`.env` at CLI entry** (`agon.config.load_env`) — Inspect only loads `.env` at `eval()` time,
   too late for preflight/doctor, so we load it ourselves with `override=False` (process env wins).
   `python-dotenv` is promoted to a direct dependency (already installed transitively).

**Mask format:** `<prefix>...<last4>` (e.g. `sk-ant-...a3f9`), identical for `doctor` and
artifact-redaction. The key is unreconstructable from a prefix plus four characters.

## Consequences

- A committed report or exported trace is safe to share — no known key survives.
- A missing key fails in under a second with the exact fix, not a deep provider error.
- Redaction is defense-in-depth: today no report field carries free text (the input is not echoed
  and `SampleRecord` has no error-message field), and the realistic span vector is the score value
  (model output) and tool-error strings — all now covered.

## Known limitations / future toggles

- **Persisted-artifact masking still ships ~12 identifiable characters** (prefix + last 4). A
  stricter full-`***REDACTED***` mode for written artifacts (while `doctor` keeps prefix+last4) is a
  trivial future toggle; not built now.
- **Unmapped providers are not preflighted** — only providers in `PROVIDER_ENV` are checked. Adding a
  provider is a one-line dict entry.
- **No secret storage** — vaults, encryption at rest, and rotation remain out of scope.
- **LangSmith dashboards** were deferred to M10 during M9 brainstorming.
```

- [ ] **Step 3: Commit**

```bash
git add docs/running-real-evals.md docs/decisions/ADR-0010-secrets-config-hardening.md
git commit -m "docs(adr): ADR-0010 secrets & config hardening; .env + doctor in running-real-evals

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Lint the whole package**

Run: `uv run ruff check agon tests`
Expected: `All checks passed!`

- [ ] **Step 2: Full offline test suite**

Run: `uv run pytest -q`
Expected: all passed (prior 225 + ~24 new M9 tests), 1 skipped. No failures.

- [ ] **Step 3: Offline smoke + doctor sanity**

```bash
uv run agon run examples/datasets/rag_smoke.yaml --display none   # report still $0.0000, gate as before
uv run agon doctor                                                # masked statuses, exit 0
uv run agon doctor --model anthropic/claude-sonnet-4-5            # MISSING or present, exit 0
```
Expected: `run` behaves exactly as before (no secrets in the offline env → redaction is a no-op);
`doctor` prints masked statuses and exits 0.

- [ ] **Step 4: Confirm no unintended files staged**

Run: `git status --short`
Expected: only M9 files committed across Tasks 1-9; the pre-existing `*.png` deletions and untracked
`docs/*.docx`, `reports2/`, `HANDOFF.md` remain untouched and unstaged.

---

## Self-Review Notes (completed by plan author)

- **Spec coverage:** redaction (T2, T7, T8), preflight (T3, T5), doctor (T6), `.env`+precedence (T4),
  emission boundaries reports+spans+console (T7, T8, T6), headline regression test (T7 + T8),
  python-dotenv dep (T4), ADR + docs (T9). All spec deliverables mapped.
- **De-risked against live code:** case input does NOT reach reports and `SampleRecord` has no
  free-text field, so the headline report test uses `--system-version` (verified to reach md+json)
  carrying an `sk-ant-` token the prefix backstop masks; the span test targets the score value
  (model output) and tool error — the real free-text vectors.
- **Type consistency:** `mask(str|None)->str`, `redact(text,*,extra)->str`,
  `missing_provider_keys(model,adapter)->list[str]`, `secret_status()->list[tuple[str,str]]`,
  `secret_values()->set[str]`, `load_env()->str|None`, `_preflight(model,adapter)->None` — names and
  signatures match across all tasks.
- **ASCII:** all `typer.echo` strings and the `...` mask separator are ASCII.
- **No placeholders:** every code/test step shows complete content.
