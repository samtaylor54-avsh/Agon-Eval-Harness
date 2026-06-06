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
    # Assigned only via sample.limit (wall-clock); transport timeouts in error text -> NETWORK.
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
    r"(\bconnection\b|\bconnect\b|timeout|timed out|rate.?limit|\b429\b|\b50\d\b|"
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
        return classify_limit_type(getattr(limit, "type", "") or "")
    error = getattr(sample, "error", None)
    if error is not None:
        text = f"{getattr(error, 'message', '')} {getattr(error, 'traceback', '')}"
        return classify_error_text(text)
    return None
