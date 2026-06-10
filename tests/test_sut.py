"""T3 — SUT contract + solvers (offline via mockllm/callable)."""

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import exact, includes

from agon.schemas import SUTConfig
from agon.sut import (
    SUT_RESPONSE_KEY,
    SUTRequest,
    SUTResponse,
    build_solver,
    callable_solver,
    get_sut_response,
    map_http_response,
)
from agon.sut.solvers import agon_generate_solver


# ----------------------------- pure-function tests ----------------------------- #
def test_map_http_response_with_field_map():
    payload = {
        "answer": "the answer",
        "sources": ["a.pdf#1"],
        "meta": {"tid": "trace-9"},
    }
    field_map = {"final_answer": "answer", "citations": "sources", "trace_id": "meta.tid"}
    resp = map_http_response(payload, field_map)
    assert resp.final_answer == "the answer"
    assert resp.citations == ["a.pdf#1"]
    assert resp.trace_id == "trace-9"


def test_map_http_response_defaults_when_missing():
    resp = map_http_response({}, {})
    assert resp.final_answer == ""
    assert resp.citations == []


def test_get_sut_response_synthesizes_from_output():
    class _Out:
        completion = "fallback text"

    class _State:
        metadata: dict = {}
        output = _Out()

    resp = get_sut_response(_State())
    assert resp.final_answer == "fallback text"


def test_get_sut_response_reads_attached():
    stored = SUTResponse(final_answer="rich", citations=["c#1"]).model_dump(mode="json")

    class _State:
        metadata = {SUT_RESPONSE_KEY: stored}
        output = None

    resp = get_sut_response(_State())
    assert resp.final_answer == "rich"
    assert resp.citations == ["c#1"]


def test_build_request_passes_case_config_overrides():
    from types import SimpleNamespace as NS

    from agon.dataset import METADATA_CASE_KEY
    from agon.sut.solvers import _build_request

    state = NS(
        input_text="q",
        sample_id="t1",
        metadata={
            "documents": ["d1"],
            METADATA_CASE_KEY: {"input": {"config_overrides": {"temperature": 0.7}}},
        },
    )
    req = _build_request(state)
    assert req.config_overrides == {"temperature": 0.7}
    assert req.documents == ["d1"]
    assert req.session_id == "t1_1"


def test_build_request_defaults_without_case_metadata():
    from types import SimpleNamespace as NS

    from agon.sut.solvers import _build_request

    req = _build_request(NS(input_text="q", sample_id="t2", metadata={}))
    assert req.config_overrides == {}


def test_build_solver_requires_callable_for_callable_adapter():
    import pytest

    with pytest.raises(ValueError):
        build_solver(SUTConfig(adapter="callable"))


# ----------------------------- end-to-end (offline) ----------------------------- #
def test_callable_solver_runs_end_to_end(tmp_path):
    async def stub(req: SUTRequest) -> SUTResponse:
        assert req.user_message == "say hello"
        return SUTResponse(final_answer="hello", citations=["doc#1"])

    task = Task(
        dataset=[Sample(input="say hello", target="hello", id="t1")],
        solver=callable_solver(stub),
        scorer=exact(),
    )
    logs = eval(task, model="mockllm/model", log_dir=str(tmp_path), display="none")
    log = logs[0]
    assert log.status == "success"
    sample = log.samples[0]
    assert sample.output.completion == "hello"
    # The normalized SUTResponse was attached.
    attached = get_sut_response(sample)
    assert attached.citations == ["doc#1"]


def test_agon_generate_solver_uses_model_output(tmp_path):
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content("mockllm", "the answer contains hello")],
    )
    task = Task(
        dataset=[Sample(input="q", target="hello", id="g1")],
        solver=agon_generate_solver(),
        scorer=includes(),
    )
    logs = eval(task, model=model, log_dir=str(tmp_path), display="none")
    log = logs[0]
    assert log.status == "success"
    assert "hello" in log.samples[0].output.completion
