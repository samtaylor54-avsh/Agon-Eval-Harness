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
