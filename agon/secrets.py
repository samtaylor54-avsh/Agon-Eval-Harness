"""Secret masking, redaction, and provider-key preflight (Phase 3 M9).

agon stores no secrets. These are read-only transforms over ``os.environ`` and arbitrary text so a
real key never lands in an artifact and a missing provider key fails fast with a clear message.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

# Env vars whose VALUES are secrets -- redacted precisely wherever they appear.
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

# Recognizable key prefixes -- the pattern backstop for a key that arrives by another path.
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
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(p) for p in KNOWN_KEY_PREFIXES)
    + r")[A-Za-z0-9_\-]{16,}"
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
    # last4 may overlap prefix chars for a very short secret, but no real key is this short.
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


def redact(text: str, *, extra: Iterable[str] = ()) -> str:
    """Mask every known secret occurring in ``text``. Hybrid: exact env values + prefix backstop.

    Idempotent: a masked value (``sk-ant-...1234``) contains ``.`` so the prefix regex won't
    re-match it, and the original value is already gone after the exact-replace pass.
    """
    if not text:
        return text
    # Exact env-set values first, longest-first so a short value can't pre-empt a longer one.
    candidates = secret_values() | {e for e in extra if e and e.strip()}
    for secret in sorted(candidates, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, mask(secret))
    # Backstop: mask prefix+entropy tokens that arrived by another path.
    return _PREFIX_TOKEN_RE.sub(lambda m: mask(m.group(0)), text)


def missing_provider_keys(model: str | None, adapter: str) -> list[str]:
    """Env vars required by ``model``'s provider that are unset/empty. Empty list = OK.

    Offline adapters (anything other than ``litellm``) need no key. An unmapped provider is not
    blocked -- we only assert keys for providers we know how to map.
    """
    if adapter != "litellm" or not model:
        return []
    provider = model.split("/")[0].lower()
    required = PROVIDER_ENV.get(provider)
    if not required:
        return []
    return [var for var in required if not (os.environ.get(var) or "").strip()]


def secret_status() -> list[tuple[str, str]]:
    """``(env_var, masked_value_or_'(not set)')`` over the known secret vars -- for ``agon doctor``.
    """
    return [(var, mask(os.environ.get(var))) for var in KNOWN_SECRET_ENV_VARS]
