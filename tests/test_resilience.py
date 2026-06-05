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


# ---------------------------- offline fault-injection behavior ---------------------------- #
#
# Verified Inspect runtime behavior (exploration runs, 2026-06-05):
#
# 1. A raising mockllm custom_outputs policy surfaces as a *sample* error: the sample's
#    ``error`` field is populated and ``log.results`` is set to ``None``.
#
# 2. ``log.status`` uses the literals ``"success"`` | ``"error"`` | ``"cancelled"`` | ``"started"``.
#
# 3. When all samples fail AND there is no ``fail_on_error`` threshold, ``log.status == "error"``
#    and ``log.results is None``.
#
# 4. When ``fail_on_error`` is exceeded (error-rate > threshold), same: ``log.status == "error"``
#    and ``log.results is None``.
#
# 5. When ``fail_on_error`` is NOT exceeded (error-rate <= threshold), ``log.status == "success"``
#    and ``log.results`` is populated; ``completed_samples`` counts only the samples that
#    finished without error (i.e. errored samples are excluded from ``completed_samples``).
#
# 6. ``retry_on_error=N`` re-runs an errored sample up to N times. After a successful retry
#    the sample counts as completed; ``log.status == "success"``.
#
# Assertions are adjusted from the original spec to guard against ``log.results is None``
# (accessing attributes on None would raise AttributeError, not fail gracefully).

from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.model import get_model  # noqa: E402

from agon.schemas import AgonCase, AgonDataset, ScoringSpec  # noqa: E402
from agon.task import agon_task  # noqa: E402
from tests.support.fault_injection import FlakyPolicy  # noqa: E402


def _dataset(messages_by_id: dict[str, str]) -> AgonDataset:
    """Build a minimal AgonDataset from a {test_id: user_message} mapping."""
    cases = [
        AgonCase(
            test_id=tid,
            name=tid,
            category="resilience",
            input={"user_message": msg},
            scoring=[ScoringSpec(type="exact_match")],
        )
        for tid, msg in messages_by_id.items()
    ]
    return AgonDataset(name="resilience_suite", dataset_version="v0", test_cases=cases)


def _run(dataset: AgonDataset, policy, tmp_path, **eval_kwargs):
    cfg = RunConfig(log_dir=str(tmp_path))
    task = agon_task(dataset, cfg)
    model = get_model("mockllm/model", custom_outputs=policy)
    return inspect_eval(task, model=model, log_dir=str(tmp_path), display="none", **eval_kwargs)[0]


def test_retry_on_error_recovers_a_transient_failure(tmp_path):
    """With retry_on_error=1 a single transient fault is retried and the sample completes."""
    dataset = _dataset({"flaky": "hello"})
    log = _run(dataset, FlakyPolicy(transient_failures=1), tmp_path, retry_on_error=1)
    assert log.status == "success"
    assert log.results is not None
    assert log.results.completed_samples == 1


def test_no_retry_lets_a_transient_failure_surface(tmp_path):
    """With retry_on_error=0 a transient fault is NOT retried; the run ends in error."""
    dataset = _dataset({"flaky": "hello"})
    log = _run(dataset, FlakyPolicy(transient_failures=1), tmp_path, retry_on_error=0)
    # Inspect sets log.status == "error" and log.results == None when the only sample errors.
    assert log.status == "error"
    assert log.results is None


def test_fail_on_error_threshold_trips_above_rate(tmp_path):
    """Error rate 0.5 (2 of 4 samples fail) exceeds threshold 0.4 → run status is error."""
    dataset = _dataset(
        {"ok1": "fine one", "ok2": "fine two", "bad1": "boom one [boom]", "bad2": "boom two [boom]"}
    )
    log = _run(dataset, FlakyPolicy(), tmp_path, fail_on_error=0.4)
    assert log.status == "error"
    assert log.results is None


def test_fail_on_error_threshold_tolerates_below_rate(tmp_path):
    """Error rate 0.5 (2 of 4 samples fail) is within threshold 0.6 → run status is success."""
    dataset = _dataset(
        {"ok1": "fine one", "ok2": "fine two", "bad1": "boom one [boom]", "bad2": "boom two [boom]"}
    )
    log = _run(dataset, FlakyPolicy(), tmp_path, fail_on_error=0.6)
    assert log.status == "success"
    assert log.results is not None
    # Only the 2 non-erroring samples are counted as completed.
    assert log.results.completed_samples == 2
