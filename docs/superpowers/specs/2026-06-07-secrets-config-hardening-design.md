# Secrets & Config Hardening — Design Spec (Phase 3 M9)

**Status:** Approved (design) · **Date:** 2026-06-07 · **Milestone:** Phase 3 M9
**Branch:** `phase-3-m9-secrets-config-hardening` (to be created)

## Goal

Make agon **safe to run against real providers and safe to share its artifacts**. Today a real eval
needs a provider key in the environment, but the harness does nothing to (a) prevent that key from
leaking into anything it writes, (b) fail fast when the key is absent, or (c) let you see what
secret/config state it resolved. This milestone closes those three gaps while keeping the existing
promise — **"agon does not store secrets."** It is **offline-first and fully offline-testable**;
secret *storage* (vaults, encryption at rest, rotation) is explicitly out of scope.

Four interlocking pieces:

1. **Secret redaction** — a real key never appears in any artifact agon writes (md/json/junit
   reports, OpenTelemetry span attributes, console/error output).
2. **Preflight key validation** — before a real-provider run, confirm the expected env var(s) are
   present; fail fast with a clean ASCII message instead of a deep provider stack trace.
3. **`agon doctor` command** — introspect resolved config + which provider keys are *set* (masked,
   never the raw value) + the offline-vs-real path, leaking nothing.
4. **`.env` enabler + precedence** — load `.env` at CLI entry so preflight/doctor see those keys, and
   document + test config/secret precedence.

## Background / current state (verified against the code)

- **Provider keys come from the provider's own env vars.** `docs/running-real-evals.md` states keys
  come from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, and that *"agon does not store secrets."* The only
  in-package `os.environ` reads are in `agon/observability/otel.py` (`LANGSMITH_API_KEY`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `LANGSMITH_PROJECT`).
- **Provider is derived from the model string.** In `agon/cli/app.py::run`, `--model` sets
  `cfg.sut.model` (e.g. `anthropic/claude-sonnet-4-5`) and flips `cfg.sut.adapter` from `mockllm` to
  `litellm`. The provider is the first `/`-segment of the model string. The offline default
  (`mockllm`) needs no key.
- **`run` already has a fail-fast seam.** `run` validates resilience flags, loads plugins, loads the
  dataset, validates scorer types, then calls `anyio.run(health_check, cfg.sut)` **before**
  `run_eval`. Preflight slots in alongside/just before `health_check`. Exit codes are already defined:
  `0` pass, `1` fail-gate, `2` abort (config/dataset/health error).
- **Inspect loads `.env` — but only at `eval()` time.** `inspect_ai._eval/context.py` and
  `inspect_ai/_cli/main.py` call `init_dotenv()` (via `python-dotenv`'s `find_dotenv(usecwd=True)`,
  walking up the directory tree). That fires when our `eval()` runs — **too late** for preflight or
  `doctor`, which run first. So we must load `.env` ourselves at CLI entry. `python-dotenv` is already
  a transitive dependency (Inspect uses it), so promoting it to a direct dep adds no download.
- **No redaction, no preflight, no introspection command exist today.** Reports
  (`agon/reporting/generator.py` → `render_markdown/json/junit`) and OTel spans
  (`agon/observability/`) serialize whatever they are given with no secret filter. The CLI prints
  config-derived text via `typer.echo` with no filter.

## Decisions locked

1. **Redaction is hybrid: env values (precise) + known prefixes (backstop).** Redact the exact current
   values of `KNOWN_SECRET_ENV_VARS` (zero false positives) AND any substring matching a known key
   prefix followed by a high-entropy run (catches a key that arrived by a path other than those env
   vars). Pattern-only was rejected (false positives on innocent tokens); env-only was rejected (misses
   a key embedded in, e.g., a dataset case input).
2. **Mask format is `<prefix>...<last4>`, identical for `doctor` and artifact-redaction.** E.g.
   `sk-ant-...a3f9`. The separator is ASCII `...` (cp1252 console constraint — never `…`). The key is
   unreconstructable from prefix + 4 chars. A stricter full-`***REDACTED***` mode for *persisted*
   artifacts (while `doctor` keeps prefix+last4) is recorded in the ADR as a trivial future toggle but
   is **not** built now.
3. **Preflight is a hard abort (exit 2), skipped on the offline path.** Offline adapters
   (`mockllm`, `http`) need no key → preflight returns no missing keys. For `litellm`, an unmapped
   provider is **not** blocked (we only assert keys for providers we know how to map). No
   `--skip-preflight` flag — the fix is to set the key.
4. **`.env` is loaded at CLI entry with `override=False`.** Process env wins over `.env` (matches
   `python-dotenv` default). `python-dotenv` becomes a direct dependency.
5. **`agon` stores no secrets.** No vault, no encryption at rest, no rotation, no writing keys
   anywhere. Redaction and masking are read-only transforms.

## Architecture

### Component 1 — `agon/secrets.py` (new module)

Pure, dependency-light functions plus extensible constants. No I/O except reading `os.environ`.

```python
KNOWN_SECRET_ENV_VARS: tuple[str, ...]   # ANTHROPIC_API_KEY, OPENAI_API_KEY, LANGSMITH_API_KEY, ...
KNOWN_KEY_PREFIXES: tuple[str, ...]      # "sk-ant-", "sk-", "ls__", ...
PROVIDER_ENV: dict[str, tuple[str, ...]] # "anthropic": ("ANTHROPIC_API_KEY",), "openai": (...), ...

def mask(value: str) -> str: ...
    # empty/None -> "(not set)"; value too short to mask safely (< 8 chars) -> "***" (no chars
    # leaked); else "<prefix>...<last4>" where <prefix> is the matched known key prefix if any,
    # else the first 3 chars. ASCII only.

def secret_values() -> set[str]: ...
    # current non-empty values of KNOWN_SECRET_ENV_VARS (the precise redaction set)

def redact(text: str, *, extra: Iterable[str] = ()) -> str: ...
    # replace every occurrence of each secret value (secret_values() | extra) with mask(value);
    # then replace prefix+high-entropy substrings (KNOWN_KEY_PREFIXES) with their mask. Idempotent.

def missing_provider_keys(model: str | None, adapter: str) -> list[str]: ...
    # offline adapter (not "litellm") -> []; else provider = model.split("/")[0];
    # return the PROVIDER_ENV[provider] vars that are unset/empty; unknown provider -> [].

def secret_status() -> list[tuple[str, str]]: ...
    # [(var, mask(value)) or (var, "(not set)")] over KNOWN_SECRET_ENV_VARS, for doctor.
```

Edge cases: `mask` on `None`/short value returns `(empty)`; `redact` is a no-op when no secrets are
set and no prefix matches; `redact` must produce valid-JSON-string content (masked form has no quotes
or control chars). `missing_provider_keys` treats whitespace-only env values as unset.

### Component 2 — Preflight (consumed by the CLI)

In `agon/cli/app.py`, a helper `_preflight(cfg)` calls `missing_provider_keys(cfg.sut.model,
cfg.sut.adapter)`; if non-empty:

```
[abort] missing API key for provider 'anthropic': ANTHROPIC_API_KEY (set it in your shell or a .env file)
```

(ASCII; lists all missing vars), then `raise typer.Exit(ABORT)`. Wired into `run` and `resume`
**after** `.env` load and **before** `health_check`. `calibrate` gets the same guard only where it
resolves a provider model for its judge (if it does not resolve one at that point, it is left
unchanged and this is noted in the plan).

### Component 3 — `agon doctor`

New `@app.command()`:

```
agon doctor [--model <provider/model>] [--config <file>]
```

Prints (all through `redact()`, statuses via `mask()`):
- agon version + Inspect version; the default path (offline `mockllm`, no key required).
- `secret_status()`: one line per known var — `ANTHROPIC_API_KEY: sk-ant-...a3f9` or
  `ANTHROPIC_API_KEY: (not set)`.
- If `--model`: the provider it maps to and whether its required keys are present (reuses
  `missing_provider_keys`).
- If `--config`: the resolved `RunConfig` summary, redacted.

Informational → always **exit 0**. Never prints a raw secret.

### Component 4 — `.env` enabler + precedence

- `agon/config/__init__.py` (or a small `agon/config/env.py`) gains `load_env() -> str | None`:
  `find_dotenv(usecwd=True)` then `load_dotenv(path, override=False)`; returns the path it loaded or
  `None`. Idempotent.
- A typer `@app.callback()` in `agon/cli/app.py` calls `load_env()` once before any command body, so
  preflight and `doctor` see `.env` keys.
- **Precedence**, documented in `docs/running-real-evals.md` and asserted by tests:
  - Config values: **CLI flags > config file > `RunConfig` defaults** (already true; add a test).
  - Secrets: **process env > `.env`** (`override=False`); `.env` never overrides an already-set var.

### Where redaction is applied (emission boundaries)

- **Reports** — `agon/reporting/generator.py`: apply `redact()` to the serialized text of each format
  immediately before it is written (md, json, junit). Defense-in-depth: even a secret that reached a
  field is masked on write. JSON stays valid (masked form is plain string content).
- **OpenTelemetry spans** — `agon/observability/`: redact string span-attribute values before they are
  set (the place attributes are assigned from record/config data). The LangSmith API key travels in an
  HTTP header (transport), not a span attribute, so it is already out of the artifact surface; this
  covers attribute *data*.
- **Console** — `doctor` is safe by construction; add defensive `redact()` only on CLI paths that echo
  config-derived text.

## Data flow

```
CLI entry (@app.callback) -> load_env()  [process env > .env]
  -> run/resume: build cfg (CLI > file > defaults)
       -> _preflight(cfg)  [missing key on real provider -> abort 2]
       -> health_check -> run_eval -> generate_reports
            -> render_*  -> redact(text) -> write artifact
       -> (OTel) set span attr -> redact(value)
  -> doctor: secret_status()/missing_provider_keys() -> redact() -> stdout (exit 0)
```

## Error handling

- Missing provider key (real path) → ASCII abort, exit 2, before any network call.
- Offline path → preflight no-op; `doctor` works with no keys set.
- `redact` never raises on odd input (None-safe at call sites; operates on `str`).
- Adding `python-dotenv` as a direct dep must not change the offline reproducibility budget (already
  installed transitively).

## Testing strategy (TDD, offline)

Unit (`tests/test_secrets.py`):
- `mask`: known-prefix value → `sk-ant-...a3f9`; empty → `(not set)`; short (<8 chars) → `***`;
  generic long value → first-3 + `...` + last-4.
- `redact`: replaces an env-set secret value wherever it appears; replaces a prefix+entropy token not
  in any env var; leaves innocent text (`"the sky is blue"`, short tokens) untouched; idempotent;
  output remains valid JSON when fed a JSON string.
- `missing_provider_keys`: offline adapter → `[]`; `litellm` + key set → `[]`; `litellm` + key unset →
  `["ANTHROPIC_API_KEY"]`; unknown provider → `[]`; whitespace-only env value treated as unset.

Integration / CLI (`tests/test_doctor.py`, extend `tests/test_cli*.py`):
- `doctor` with a key set → prints masked form, never the raw value; unset → `(not set)`; `--model`
  reports presence; exit 0.
- `run --model anthropic/x` with `ANTHROPIC_API_KEY` unset → exit 2 + ASCII abort message in output;
  no network attempted.
- Precedence: a CLI flag overrides a config-file value (existing behavior, asserted).

`.env` (`tests/test_env_loading.py`):
- temp `.env` in cwd → `load_env()` makes a fake key visible to `doctor`; returns the loaded path.
- an already-set process env var is **not** overridden by `.env`.

Redaction-in-artifacts regression (the headline test, `tests/test_redaction_regression.py`):
- Plant `ANTHROPIC_API_KEY=sk-ant-FAKE...` in env **and** embed the raw key in a dataset case input;
  run an offline eval through to reports; assert the raw key string appears in **none** of the
  written md/json/junit files and in **no** exported span attribute; assert the masked form may
  appear. This is the permanent guard for the milestone's headline property.

## Out of scope (YAGNI)

Secret storage / vaults (AWS Secrets Manager), encryption at rest, key rotation, a `--skip-preflight`
flag, full-`***REDACTED***` artifact mode (noted as a future toggle), and **LangSmith dashboards**
(deferred to M10).

## Deliverables

- `agon/secrets.py` (redaction, masking, preflight mapping).
- `agon/config` `load_env()` + a `@app.callback()` wiring it in.
- `agon doctor` command.
- Redaction wired into `agon/reporting/generator.py` and `agon/observability/`.
- Preflight in `run`/`resume` (and `calibrate` if it resolves a provider model).
- `python-dotenv` promoted to a direct dependency in `pyproject.toml`.
- `docs/decisions/ADR-0010-secrets-config-hardening.md`.
- `docs/running-real-evals.md` update (`.env` usage + `agon doctor`).
- The full test suite above; `ruff` clean; offline reproducibility budget unchanged.

## Known constraints / gotchas

1. **ASCII console output** — mask separator is `...`, abort messages use `-> `/plain ASCII (no
   `…`/`→`/`—`); docstrings/markdown/jinja may be UTF-8.
2. **Targeted `git add` only** — stage only this milestone's files; the working tree carries
   pre-existing `*.png` deletions and untracked `docs/*.docx`, `reports2/`, `HANDOFF.md`.
3. **Preflight must run after `load_env()`** so `.env`-sourced keys count as present.
4. **`override=False`** so a real shell-exported key is never clobbered by a stale `.env`.
5. **Don't break JSON reports** — redaction substitutes plain masked strings, preserving validity.
