"""Normalize an Inspect agent message history into the harness SUT contract.

An agent (native ``react()`` or a bridged LangGraph agent) produces a conversation in
``state.messages``. This module flattens that into ``SUTResponse.tool_calls`` + ``final_answer``
so the existing ``tool_use`` scorer and failure taxonomy (Phase 1 §25.11) work on agents
unchanged — the harness stays agnostic to how the trajectory was produced.
"""

from __future__ import annotations

import re
from typing import Any

from agon.sut.contract import SUT_RESPONSE_KEY, SUTResponse, ToolCall

# react()'s built-in completion tool — not a real SUT tool call.
SUBMIT_TOOL = "submit"

# mockllm renders a tool-call output as "tool call for tool <name>\n\n<content>" in the
# completion text. Strip that offline artifact so the final answer is clean (no-op for real models).
_MOCK_TOOLCALL_PREFIX = re.compile(r"^tool call for tool \w+\s*", re.IGNORECASE)


def extract_tool_calls(messages: list[Any]) -> list[ToolCall]:
    """Flatten assistant tool calls + their tool results into ordered ToolCall records."""
    results_by_id: dict[str, Any] = {}
    for m in messages:
        if getattr(m, "role", None) == "tool":
            tcid = getattr(m, "tool_call_id", None)
            if tcid is not None:
                results_by_id[tcid] = m

    calls: list[ToolCall] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            if tc.function == SUBMIT_TOOL:
                continue
            result_msg = results_by_id.get(tc.id)
            result_text = None
            error_text = None
            if result_msg is not None:
                err = getattr(result_msg, "error", None)
                if err is not None:
                    error_text = getattr(err, "message", None) or str(err)
                else:
                    result_text = getattr(result_msg, "text", None)
            calls.append(
                ToolCall(
                    tool_name=tc.function,
                    arguments=dict(tc.arguments or {}),
                    result=result_text,
                    error=error_text,
                )
            )
    return calls


def extract_final_answer(state: Any) -> str:
    """The agent's final answer — the submit() argument if present, else the completion."""
    messages = getattr(state, "messages", []) or []
    for m in reversed(messages):
        for tc in getattr(m, "tool_calls", None) or []:
            if tc.function == SUBMIT_TOOL:
                answer = (tc.arguments or {}).get("answer")
                if answer:
                    return str(answer)
    output = getattr(state, "output", None)
    completion = (getattr(output, "completion", "") or "") if output else ""
    return _MOCK_TOOLCALL_PREFIX.sub("", completion).strip()


def messages_to_sut_response(state: Any, *, trace_id: str = "") -> SUTResponse:
    return SUTResponse(
        final_answer=extract_final_answer(state),
        tool_calls=extract_tool_calls(getattr(state, "messages", []) or []),
        trace_id=trace_id,
    )


def attach_agent_response(state: Any, *, trace_id: str = "") -> SUTResponse:
    """Normalize the agent trajectory and attach it to state.metadata for scorers."""
    response = messages_to_sut_response(state, trace_id=trace_id)
    if state.metadata is None:
        state.metadata = {}
    state.metadata[SUT_RESPONSE_KEY] = response.model_dump(mode="json")
    return response
