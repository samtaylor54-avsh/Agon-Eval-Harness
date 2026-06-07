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
