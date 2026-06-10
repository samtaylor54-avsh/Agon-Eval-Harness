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


# ------------------------------- state_consistency ------------------------------- #
async def run_state(answer: str, **params):
    case = make_case(ExpectedBehavior())
    s = ScoringSpec(type="state_consistency", params=params)
    return await default_registry.get("state_consistency").score(
        case, SUTResponse(final_answer=answer, tool_calls=[]), s
    )


async def test_state_consistency_all_facts_recalled():
    out = await run_state(
        "Per your Premium plan, the deductible is $500.",
        facts=["premium plan", "$500"],
    )
    assert out.normalized_score == 1.0
    assert out.labels == []


async def test_state_consistency_partial_recall_is_state_loss():
    out = await run_state("Your deductible is $500.", facts=["premium plan", "$500"])
    assert out.normalized_score == 0.5
    assert "state_loss" in out.labels


async def test_state_consistency_contradiction_gates_to_zero():
    out = await run_state(
        "You are on the Basic plan with a $500 deductible.",
        facts=["$500"],
        contradictions=["basic plan"],
    )
    assert out.normalized_score == 0.0
    assert "state_contradiction" in out.labels
    assert out.details["contradicted"] == ["basic plan"]


async def test_state_consistency_contradictions_only():
    out = await run_state("All good.", contradictions=["basic plan"])
    assert out.normalized_score == 1.0


async def test_state_consistency_requires_params():
    import pytest

    case = make_case(ExpectedBehavior())
    scorer = default_registry.get("state_consistency")
    empty = ScoringSpec(type="state_consistency")
    with pytest.raises(ValueError):
        await scorer.score(case, SUTResponse(final_answer="x", tool_calls=[]), empty)
    assert scorer.validate_spec(empty)  # pre-flight catches the same misconfig
    ok = ScoringSpec(type="state_consistency", params={"facts": ["a"]})
    assert scorer.validate_spec(ok) == []


# Adversarial-review pins.
async def test_state_consistency_scalar_facts_is_whole_string_not_characters():
    # A scalar string must not be iterated per-character (12 one-char "facts" scored
    # 0.58 on an unrelated answer — above the default pass threshold).
    out = await run_state("something entirely unrelated", facts="premium plan")
    assert out.normalized_score == 0.0
    assert "state_loss" in out.labels
    out = await run_state("you are on the Premium plan", facts="premium plan")
    assert out.normalized_score == 1.0


async def test_state_consistency_rejects_blank_entries():
    # An empty-string fact substring-matches every answer -> silent always-pass.
    import pytest

    with pytest.raises(ValueError):
        await run_state("anything", facts=[""])
    scorer = default_registry.get("state_consistency")
    assert scorer.validate_spec(ScoringSpec(type="state_consistency", params={"facts": [""]}))


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
