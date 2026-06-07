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
