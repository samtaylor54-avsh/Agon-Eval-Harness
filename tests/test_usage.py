"""Phase 3 M5 — token usage is populated from the Inspect model output."""

from inspect_ai.model import ModelOutput, ModelUsage

from agon.sut import SUT_RESPONSE_KEY, SUTResponse
from agon.sut.solvers import agon_generate_solver


class _FakeState:
    """Minimal stand-in for an Inspect TaskState carrying a model output + metadata."""

    def __init__(self, output):
        self.output = output
        self.metadata = {}
        self.sample_id = "s1"
        self.epoch = 1


async def test_generate_solver_copies_token_usage():
    usage = ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    output = ModelOutput.from_content(model="mockllm", content="hello")
    output.usage = usage

    solver = agon_generate_solver()

    async def _generate(state):  # stand-in for Inspect's generate(); output already set
        return state

    state = _FakeState(output)
    state = await solver(state, _generate)

    stored = state.metadata[SUT_RESPONSE_KEY]
    response = SUTResponse.model_validate(stored)
    assert response.token_usage.input == 10
    assert response.token_usage.output == 4
    assert response.token_usage.total == 14


async def test_generate_solver_handles_missing_usage():
    output = ModelOutput.from_content(model="mockllm", content="hi")
    output.usage = None
    solver = agon_generate_solver()

    async def _generate(state):
        return state

    state = _FakeState(output)
    state = await solver(state, _generate)
    response = SUTResponse.model_validate(state.metadata[SUT_RESPONSE_KEY])
    assert response.token_usage.total == 0
