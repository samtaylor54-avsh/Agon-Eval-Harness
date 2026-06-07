"""Phase 3 M10 - eval-outcome enrichment of OTel spans."""

from types import SimpleNamespace as NS

import pytest

pytest.importorskip("opentelemetry.sdk")

from agon.analysis.logs import digest  # noqa: E402
from agon.observability import export_eval_log, in_memory_tracer  # noqa: E402
from agon.observability.semconv import (  # noqa: E402
    AGON_CATEGORY,
    AGON_COMPOSITE_SCORE,
    AGON_COST_TOTAL_TOKENS,
    AGON_COST_USD,
    AGON_ERROR_CATEGORY,
    AGON_ERROR_COUNT,
    AGON_N_CASES,
    AGON_OVERALL_PASS_RATE,
    AGON_PASSED,
    AGON_RECOMMENDATION,
    AGON_RISK_LEVEL,
    AGON_SYSTEM_VERSION,
)
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig  # noqa: E402
from agon.sut.contract import SUTResponse  # noqa: E402
from agon.task.builder import run_eval  # noqa: E402


async def _fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _ds(messages):
    cases = [
        AgonCase(
            test_id=tid, name=tid, category="c", input={"user_message": msg},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        )
        for tid, msg in messages.items()
    ]
    return AgonDataset(name="m10", dataset_version="v0", test_cases=cases)


def _run(tmp_path, messages, **cfg_kwargs):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"), **cfg_kwargs)
    log = run_eval(_ds(messages), cfg, callable_fn=_fn, display="none")
    return log, digest(log)


def test_run_span_carries_outcome_scalars(tmp_path):
    log, d = _run(tmp_path, {"a": "hi", "b": "hello"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert run.attributes[AGON_OVERALL_PASS_RATE] == d.overall_pass_rate
    assert run.attributes[AGON_N_CASES] == 2
    assert run.attributes[AGON_ERROR_COUNT] == 0
    assert run.attributes[AGON_RECOMMENDATION] in ("PASS", "INVESTIGATE", "FAIL")
    assert AGON_COST_USD in run.attributes
    assert AGON_COST_TOTAL_TOKENS in run.attributes


def test_sample_spans_carry_per_case_outcomes(tmp_path):
    log, d = _run(tmp_path, {"a": "hi"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    sample = next(s for s in exporter.get_finished_spans() if s.name.startswith("invoke_agent "))
    assert sample.attributes[AGON_PASSED] is True
    assert sample.attributes[AGON_COMPOSITE_SCORE] == 1.0
    assert sample.attributes[AGON_CATEGORY] == "c"
    assert sample.attributes[AGON_RISK_LEVEL] == "medium"


def test_no_digest_means_no_enrichment_backward_compat():
    ev = NS(
        event="score", timestamp="2026-01-01T00:00:00", scorer="agon_scorer", score=NS(value=1.0)
    )
    sample = NS(id="s1", events=[ev])
    log = NS(
        eval=NS(run_id="r1", task="demo", model=None, created="2026-01-01T00:00:00"),
        samples=[sample],
    )
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)  # no digest -> no outcome attrs
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert AGON_OVERALL_PASS_RATE not in run.attributes
    sample_span = next(
        s for s in exporter.get_finished_spans() if s.name.startswith("invoke_agent ")
    )
    assert AGON_PASSED not in sample_span.attributes


def test_system_version_is_redacted_on_run_span(tmp_path):
    log, d = _run(tmp_path, {"a": "hi"}, system_version="build-sk-ant-ABCDEFGHIJKLMNOP1234")
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    run = next(s for s in exporter.get_finished_spans() if s.name.startswith("eval "))
    assert "sk-ant-ABCDEFGHIJKLMNOP1234" not in run.attributes[AGON_SYSTEM_VERSION]
    assert "sk-ant-...1234" in run.attributes[AGON_SYSTEM_VERSION]


def test_error_taxonomy_on_run_and_sample_spans(tmp_path):
    log, d = _run(tmp_path, {"good": "hi", "bad": "boom"})
    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer, digest=d)
    spans = exporter.get_finished_spans()
    run = next(s for s in spans if s.name.startswith("eval "))
    assert run.attributes[AGON_ERROR_COUNT] >= 1
    cat_attrs = {k: v for k, v in run.attributes.items() if k.startswith("agon.error_count.")}
    assert cat_attrs  # e.g. agon.error_count.network == 1
    bad = next(s for s in spans if s.name == "invoke_agent bad")
    assert AGON_ERROR_CATEGORY in bad.attributes
