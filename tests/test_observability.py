"""M3 — OpenTelemetry export of eval logs (in-memory exporter)."""

from datetime import datetime
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("opentelemetry.sdk")

from agon.observability import export_eval_log, in_memory_tracer  # noqa: E402
from agon.observability.semconv import (  # noqa: E402
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_TOOL_NAME,
    GEN_AI_USAGE_INPUT_TOKENS,
)

T0 = datetime(2026, 1, 1, 0, 0, 0)
T1 = datetime(2026, 1, 1, 0, 0, 1)


def _fake_log() -> NS:
    model_event = NS(
        event="model", timestamp=T0, completed=T1, model="openai/gpt-4o",
        output=NS(usage=NS(input_tokens=10, output_tokens=5)),
    )
    tool_event = NS(
        event="tool", timestamp=T0, completed=T1, id="c1", function="search", error="boom",
    )
    score_event = NS(event="score", timestamp=T0, scorer="agon_scorer", score=NS(value=1.0))
    sample = NS(id="s1", events=[model_event, tool_event, score_event])
    return NS(
        eval=NS(run_id="r1", task="demo", model="openai/gpt-4o", created="2026-01-01T00:00:00"),
        samples=[sample],
    )


def test_export_builds_gen_ai_span_tree():
    tracer, exporter = in_memory_tracer()
    n = export_eval_log(_fake_log(), tracer)
    spans = exporter.get_finished_spans()
    assert n == len(spans) == 5  # run + sample + model + tool + score

    by_prefix = {s.name.split()[0]: s for s in spans}
    assert by_prefix["eval"].attributes[GEN_AI_OPERATION_NAME] == "invoke_workflow"
    assert by_prefix["invoke_agent"].attributes[GEN_AI_OPERATION_NAME] == "invoke_agent"

    chat = next(s for s in spans if s.name.startswith("chat "))
    assert chat.attributes[GEN_AI_OPERATION_NAME] == "chat"
    assert chat.attributes[GEN_AI_REQUEST_MODEL] == "openai/gpt-4o"
    assert chat.attributes[GEN_AI_USAGE_INPUT_TOKENS] == 10

    tool = next(s for s in spans if s.name.startswith("execute_tool "))
    assert tool.attributes[GEN_AI_TOOL_NAME] == "search"
    assert tool.status.status_code.name == "ERROR"  # tool error propagates

    assert any(s.name.startswith("agon.score") for s in spans)


def test_score_span_carries_gen_ai_evaluation_attributes():
    from agon.observability.semconv import (
        GEN_AI_EVALUATION_EXPLANATION,
        GEN_AI_EVALUATION_NAME,
        GEN_AI_EVALUATION_SCORE_LABEL,
        GEN_AI_EVALUATION_SCORE_VALUE,
    )

    score_event = NS(
        event="score", timestamp=T0, scorer="agon_scorer",
        score=NS(value=1.0, explanation="exact_match=1.00"),
    )
    sample = NS(id="s1", events=[score_event])
    log = NS(
        eval=NS(run_id="r1", task="demo", model=None, created="2026-01-01T00:00:00"),
        samples=[sample],
    )

    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)
    score = next(s for s in exporter.get_finished_spans() if s.name.startswith("agon.score"))
    assert score.attributes[GEN_AI_EVALUATION_NAME] == "agon_scorer"
    assert score.attributes[GEN_AI_EVALUATION_SCORE_VALUE] == 1.0
    assert score.attributes[GEN_AI_EVALUATION_SCORE_LABEL] == "pass"
    assert score.attributes[GEN_AI_EVALUATION_EXPLANATION] == "exact_match=1.00"


def test_non_numeric_score_value_omits_evaluation_score_value():
    from agon.observability.semconv import (
        GEN_AI_EVALUATION_NAME,
        GEN_AI_EVALUATION_SCORE_VALUE,
    )

    score_event = NS(
        event="score", timestamp=T0, scorer="agon_scorer", score=NS(value={"k": 1}),
    )
    sample = NS(id="s1", events=[score_event])
    log = NS(
        eval=NS(run_id="r1", task="demo", model=None, created="2026-01-01T00:00:00"),
        samples=[sample],
    )

    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)
    score = next(s for s in exporter.get_finished_spans() if s.name.startswith("agon.score"))
    assert score.attributes[GEN_AI_EVALUATION_NAME] == "agon_scorer"
    assert GEN_AI_EVALUATION_SCORE_VALUE not in score.attributes


def test_span_tree_is_nested():
    tracer, exporter = in_memory_tracer()
    export_eval_log(_fake_log(), tracer)
    spans = {s.name.split()[0]: s for s in exporter.get_finished_spans()}
    run, sample, chat = spans["eval"], spans["invoke_agent"], spans["chat"]
    # run is root; sample's parent is run; chat's parent is sample.
    assert run.parent is None
    assert sample.parent.span_id == run.context.span_id
    assert chat.parent.span_id == sample.context.span_id


def test_export_real_eval(tmp_path):
    from inspect_ai import Task, eval
    from inspect_ai.model import ModelOutput, get_model

    from agon.dataset import case_to_sample
    from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
    from agon.scoring.inspect_scorer import agon_scorer
    from agon.sut import agon_generate_solver

    case = AgonCase(
        test_id="t1", name="n", category="c", input={"user_message": "hi"},
        expected=ExpectedBehavior(expected_answer="hello world"),
        scoring=[ScoringSpec(type="exact_match")],
    )
    model = get_model(
        "mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm", "hello world")]
    )
    task = Task(dataset=[case_to_sample(case)], solver=agon_generate_solver(), scorer=agon_scorer())
    log = eval(task, model=model, log_dir=str(tmp_path), display="none")[0]

    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)
    names = [s.name for s in exporter.get_finished_spans()]
    assert any(n.startswith("eval ") for n in names)
    assert any(n.startswith("chat mockllm/model") for n in names)
    assert any(n.startswith("agon.score") for n in names)


def test_score_value_and_tool_error_are_redacted_in_spans(monkeypatch):
    from agon.observability.semconv import AGON_SCORE_VALUE

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SPANLEAK0000000000")
    leak = "model said sk-ant-SPANLEAK0000000000"
    model_event = NS(
        event="model", timestamp=T0, completed=T1, model="openai/gpt-4o",
        output=NS(usage=NS(input_tokens=1, output_tokens=1)),
    )
    tool_event = NS(
        event="tool", timestamp=T0, completed=T1, id="c1", function="search",
        error="boom sk-ant-SPANLEAK0000000000",
    )
    score_event = NS(event="score", timestamp=T0, scorer="agon_scorer", score=NS(value=leak))
    sample = NS(id="s1", events=[model_event, tool_event, score_event])
    log = NS(
        eval=NS(run_id="r1", task="demo", model="openai/gpt-4o", created="2026-01-01T00:00:00"),
        samples=[sample],
    )

    tracer, exporter = in_memory_tracer()
    export_eval_log(log, tracer)
    spans = exporter.get_finished_spans()

    score = next(s for s in spans if s.name.startswith("agon.score"))
    assert "sk-ant-SPANLEAK0000000000" not in score.attributes[AGON_SCORE_VALUE]
    assert "sk-ant-...0000" in score.attributes[AGON_SCORE_VALUE]

    tool = next(s for s in spans if s.name.startswith("execute_tool "))
    assert "sk-ant-SPANLEAK0000000000" not in (tool.status.description or "")
