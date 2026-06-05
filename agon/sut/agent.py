"""Native Inspect ReAct agent as a System-Under-Test (robust, offline-capable).

Wraps Inspect's ``react()`` agent and normalizes its trajectory into the harness SUT contract,
so agent runs are scored by the same scorers as any other SUT. This is the offline/CI agent
path; the LangGraph bridge (``agon/sut/langgraph.py``) is the opt-in production path.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.agent import as_solver, react
from inspect_ai.solver import Generate, Solver, TaskState, solver

from agon.sut.agent_messages import attach_agent_response

DEFAULT_AGENT_PROMPT = (
    "You are a capable assistant. Use the available tools to gather the information you "
    "need, then submit a concise, accurate final answer."
)


@solver
def react_sut(tools: list[Any], *, prompt: str | None = None, attempts: int = 1) -> Solver:
    """A ReAct-agent SUT: run the agent, then normalize its trajectory to a SUTResponse."""
    agent_solver = as_solver(
        react(prompt=prompt or DEFAULT_AGENT_PROMPT, tools=tools, attempts=attempts)
    )

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state = await agent_solver(state, generate)
        attach_agent_response(
            state, trace_id=f"{state.sample_id}_{getattr(state, 'epoch', 1)}"
        )
        return state

    return solve
