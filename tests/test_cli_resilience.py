"""Phase 3 M5 -- `agon run` exposes resilience flags onto RunConfig.resilience."""

import pytest
from pydantic import ValidationError

from agon.cli.app import _apply_resilience_flags
from agon.schemas import RunConfig


def test_apply_resilience_flags_sets_fields():
    cfg = RunConfig()
    _apply_resilience_flags(
        cfg,
        max_retries=2,
        request_timeout=120,
        attempt_timeout=60,
        retry_on_error=1,
        sample_time_limit=30,
        fail_on_error="0.25",
    )
    r = cfg.resilience
    assert r.max_retries == 2
    assert r.request_timeout == 120
    assert r.attempt_timeout == 60
    assert r.retry_on_error == 1
    assert r.sample_time_limit == 30
    assert r.fail_on_error == 0.25


def test_apply_resilience_flags_parses_bool_fail_on_error():
    cfg = RunConfig()
    _apply_resilience_flags(cfg, fail_on_error="true")
    assert cfg.resilience.fail_on_error is True
    _apply_resilience_flags(cfg, fail_on_error="false")
    assert cfg.resilience.fail_on_error is False


def test_apply_resilience_flags_rejects_out_of_range_fail_on_error():
    # The CLI assigns the field directly; validate_assignment makes the 0..1 validator fire.
    cfg = RunConfig()
    with pytest.raises(ValidationError):
        _apply_resilience_flags(cfg, fail_on_error="1.5")


def test_apply_resilience_flags_rejects_non_numeric_fail_on_error():
    cfg = RunConfig()
    with pytest.raises(ValueError):
        _apply_resilience_flags(cfg, fail_on_error="notanumber")


def test_apply_resilience_flags_ignores_unset():
    cfg = RunConfig()
    _apply_resilience_flags(cfg)  # all None -> no change
    assert cfg.resilience == RunConfig().resilience
