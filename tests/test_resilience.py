"""Phase 3 M5 — resilience config surface + offline fault-injection behavior."""

import pytest
from pydantic import ValidationError

from agon.schemas import ResilienceConfig, RunConfig
from agon.task.builder import resilience_eval_kwargs


def test_resilience_defaults():
    r = ResilienceConfig()
    assert r.max_retries == 5
    assert r.retry_on_error == 0
    assert r.fail_on_error is False
    assert r.request_timeout is None
    assert r.attempt_timeout is None
    assert r.sample_time_limit is None


def test_resilience_rejects_out_of_range_fail_on_error():
    with pytest.raises(ValidationError):
        ResilienceConfig(fail_on_error=1.5)
    with pytest.raises(ValidationError):
        ResilienceConfig(fail_on_error=-0.1)
    # bools and in-range floats are fine:
    assert ResilienceConfig(fail_on_error=True).fail_on_error is True
    assert ResilienceConfig(fail_on_error=0.25).fail_on_error == 0.25


def test_runconfig_has_resilience_and_no_fail_fast():
    cfg = RunConfig()
    assert isinstance(cfg.resilience, ResilienceConfig)
    assert not hasattr(cfg, "fail_fast")


def test_eval_kwargs_minimal_defaults():
    kwargs = resilience_eval_kwargs(RunConfig())
    assert kwargs["max_connections"] == 8
    assert kwargs["max_retries"] == 5
    assert kwargs["retry_on_error"] == 0
    assert kwargs["fail_on_error"] is False
    # Optional knobs are omitted (None) so Inspect uses its own defaults.
    assert "timeout" not in kwargs
    assert "attempt_timeout" not in kwargs
    assert "time_limit" not in kwargs


def test_eval_kwargs_full():
    cfg = RunConfig(
        resilience=ResilienceConfig(
            max_retries=2,
            request_timeout=120,
            attempt_timeout=60,
            retry_on_error=1,
            sample_time_limit=30,
            fail_on_error=0.25,
        )
    )
    kwargs = resilience_eval_kwargs(cfg)
    assert kwargs["max_retries"] == 2
    assert kwargs["timeout"] == 120
    assert kwargs["attempt_timeout"] == 60
    assert kwargs["retry_on_error"] == 1
    assert kwargs["time_limit"] == 30
    assert kwargs["fail_on_error"] == 0.25
