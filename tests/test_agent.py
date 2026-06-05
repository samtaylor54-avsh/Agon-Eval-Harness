"""M2 — agent message normalization, agent scorers, and offline ReAct-agent eval."""

from inspect_ai import eval
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageTool,
    ModelOutput,
    get_model,
)
from inspect_ai.tool import ToolCall as InspectToolCall
from inspect_ai.tool import tool

from agon.schemas import AgonCase, AgonDataset, ExpectedBehavior, RunConfig, ScoringSpec
from agon.scoring import default_registry
from agon.sut import SUTResponse, extract_tool_calls
from agon.sut.agent_messages import extract_final_answer
from agon.sut.contract import ToolCall
from agon.task import agent_task


def spec(scorer_type: str) -> ScoringSpec:
    return ScoringSpec(type=scorer_type)


def make_case(expected: ExpectedBehavior) -> AgonCase:
    return AgonCase(
        test_id="t", name="n", category="tool_use",
        input={"user_message": "q"}, expected=expected,
        scoring=[ScoringSpec(type="tool_use")],
    )


def resp(*calls: ToolCall, answer: str = "") -> SUTResponse:
    return SUTResponse(final_answer=answer, tool_calls=list(calls))


async def run(scorer_type, case, response):
    return await default_registry.get(scorer_type).score(case, response, spec(scorer_type))


# ------------------------------- message extraction ------------------------------- #
def test_extract_tool_calls_pairs_results():
    messages = [
        ChatMessageAssistant(
            content="",
            tool_calls=[InspectToolCall(id="c1", function="search", arguments={"q": "x"})],
        ),
        ChatMessageTool(content="found it", tool_call_id="c1", function="search"),
        ChatMessageAssistant(
            content="",
            tool_calls=[InspectToolCall(id="c2", function="submit", arguments={"answer": "done"})],
        ),
    ]
    calls = extract_tool_calls(messages)
    # submit is filtered out; search is paired with its result.
    assert len(calls) == 1
    assert calls[0].tool_name == "search"
    assert calls[0].result == "found it"


def test_extract_final_answer_strips_mockllm_artifact():
    class _Out:
        completion = "tool call for tool submit\n\nThe answer is 42."

    class _State:
        messages: list = []
        output = _Out()

    assert extract_final_answer(_State()) == "The answer is 42."


# ------------------------------- tool_use scorer ------------------------------- #
async def test_tool_use_perfect():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search"]))
    out = await run("tool_use", case, resp(ToolCall(tool_name="search", arguments={"q": "x"})))
    assert out.normalized_score == 1.0


async def test_tool_use_omission():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search", "lookup"]))
    out = await run("tool_use", case, resp(ToolCall(tool_name="search", arguments={})))
    assert out.normalized_score < 1.0
    assert "tool_omission" in out.labels


async def test_tool_use_forbidden():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search"], forbidden_tools=["delete"]))
    out = await run(
        "tool_use", case,
        resp(
            ToolCall(tool_name="search", arguments={}),
            ToolCall(tool_name="delete", arguments={}),
        ),
    )
    assert "tool_misuse" in out.labels


async def test_tool_use_bad_recovery():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search"]))
    out = await run(
        "tool_use", case,
        resp(ToolCall(tool_name="search", arguments={}, error="boom")),
    )
    assert "bad_recovery" in out.labels


async def test_tool_use_recovers():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search"]))
    out = await run(
        "tool_use", case,
        resp(
            ToolCall(tool_name="search", arguments={}, error="boom"),
            ToolCall(tool_name="search", arguments={}, result="ok"),
        ),
    )
    assert "bad_recovery" not in out.labels


# ------------------------------- planning + step_efficiency ------------------------------- #
async def test_planning_acted_without_tools():
    case = make_case(ExpectedBehavior(expected_tool_calls=["search"]))
    out = await run("planning", case, resp(answer="blind answer"))
    assert out.normalized_score == 0.0
    assert "poor_reasoning_path" in out.labels


async def test_planning_no_expected_tools_passes():
    case = make_case(ExpectedBehavior())
    out = await run("planning", case, resp(answer="fine"))
    assert out.normalized_score == 1.0


async def test_step_efficiency_penalizes_duplicates():
    case = make_case(ExpectedBehavior())
    out = await run(
        "step_efficiency", case,
        resp(
            ToolCall(tool_name="search", arguments={"q": "x"}),
            ToolCall(tool_name="search", arguments={"q": "x"}),  # duplicate
        ),
    )
    assert out.normalized_score == 0.5
    assert "redundant_tool_call" in out.labels


async def test_step_efficiency_clean():
    case = make_case(ExpectedBehavior())
    out = await run(
        "step_efficiency", case,
        resp(
            ToolCall(tool_name="search", arguments={"q": "x"}),
            ToolCall(tool_name="lookup", arguments={"id": 1}),
        ),
    )
    assert out.normalized_score == 1.0


# ------------------------------- end-to-end ReAct agent (offline) ------------------------------- #
@tool
def get_weather():
    async def execute(city: str):
        """Get the weather for a city.

        Args:
            city: the city name
        """
        return f"It is sunny in {city}."

    return execute


def test_react_agent_eval_offline(tmp_path):
    case = AgonCase(
        test_id="agent_weather",
        name="weather lookup",
        category="tool_use",
        input={"user_message": "what is the weather in Paris?"},
        expected=ExpectedBehavior(
            expected_tool_calls=["get_weather"], answer_contains=["sunny"]
        ),
        scoring=[
            spec("tool_use"), spec("planning"),
            spec("step_efficiency"), spec("keyword_containment"),
        ],
    )
    dataset = AgonDataset(name="agent_smoke", dataset_version="v", test_cases=[case])
    task = agent_task(dataset, [get_weather()], RunConfig(log_dir=str(tmp_path)))
    # Script the agent: call get_weather, then submit.
    model = get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.for_tool_call("inspect", "get_weather", {"city": "Paris"}),
            ModelOutput.for_tool_call("inspect", "submit", {"answer": "It is sunny in Paris."}),
        ],
    )
    log = eval(task, model=model, log_dir=str(tmp_path), display="none")[0]
    assert log.status == "success"
    meta = log.samples[0].scores["agon_scorer"].metadata
    scores = {s["scorer_type"]: s["normalized_score"] for s in meta["scores"]}
    assert scores["tool_use"] == 1.0
    assert scores["planning"] == 1.0
    assert scores["step_efficiency"] == 1.0
    assert meta["passed"] is True
