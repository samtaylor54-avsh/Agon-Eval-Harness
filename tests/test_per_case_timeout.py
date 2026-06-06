"""Phase 3 M8 - per-case timeout overrides, enforced in the SUT solver."""

import asyncio

from agon.analysis.logs import digest
from agon.schemas import (
    AgonCase,
    AgonDataset,
    ResilienceConfig,
    RunConfig,
    ScoringSpec,
    SUTConfig,
)
from agon.sut.contract import SUTResponse
from agon.task.builder import resilience_eval_kwargs, run_eval


async def _slow_fn(req):
    await asyncio.sleep(3)
    return SUTResponse(final_answer="the answer")


def _case(tid, msg, time_limit=None):
    return AgonCase(
        test_id=tid, name=tid, category="c", input={"user_message": msg},
        expected={"expected_answer": "the answer"},
        scoring=[ScoringSpec(type="exact_match")], sample_time_limit=time_limit,
    )


def test_schema_accepts_per_case_time_limit():
    assert _case("x", "hi", time_limit=5).sample_time_limit == 5


def test_eval_kwargs_no_longer_sets_global_time_limit():
    cfg = RunConfig(resilience=ResilienceConfig(sample_time_limit=30))
    assert "time_limit" not in resilience_eval_kwargs(cfg)


def test_per_case_timeout_trips_and_is_categorized(tmp_path):
    ds = AgonDataset(name="t", dataset_version="v0", test_cases=[_case("slow", "hi", time_limit=1)])
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(ds, cfg, callable_fn=_slow_fn, display="none")
    d = digest(log)
    rec = d.record_map()["slow"]
    assert rec.errored is True
    assert rec.error_category == "timeout"
    assert d.error_count_by_category == {"timeout": 1}


def test_global_default_applies_without_per_case_override(tmp_path):
    ds = AgonDataset(name="t", dataset_version="v0", test_cases=[_case("slow", "hi")])
    cfg = RunConfig(
        log_dir=str(tmp_path),
        sut=SUTConfig(adapter="callable"),
        resilience=ResilienceConfig(sample_time_limit=1),
    )
    log = run_eval(ds, cfg, callable_fn=_slow_fn, display="none")
    assert digest(log).record_map()["slow"].error_category == "timeout"
