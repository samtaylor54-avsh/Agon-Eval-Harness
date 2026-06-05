"""EXPERIMENTAL: bridge a real LangGraph ReAct agent as the SUT via Inspect's agent_bridge.

This evaluates the *actual* LangGraph agent you would deploy — highest external validity.
Requires the ``[langgraph]`` extra.

⚠️  CURRENT LIMITATIONS (see ADR-0004), verified against inspect-ai 0.3.x + langgraph 1.0:
  1. inspect-ai's bridge patches the Google client via ``find_spec("google.genai")``, which
     RAISES (not returns None) when the ``google`` namespace is absent. Install any provider of
     it (e.g. ``googleapis-common-protos``) if you hit ``ModuleNotFoundError: No module named
     'google'``.
  2. Current ``langchain-openai`` calls an OpenAI client method the bridge doesn't implement
     (``'ChatCompletion' object has no attribute 'parse'``), so the *offline mockllm* path does
     not work today. Use this against a REAL provider.
  3. ``langgraph.prebuilt.create_react_agent`` is deprecated in langgraph 1.0 in favor of
     ``langchain.agents.create_agent`` — this adapter prefers the new entrypoint when available.

For offline/CI agent evaluation, use the native ``react_sut`` (``agon/sut/agent.py``); the agent
scorers are identical regardless of which agent produced the trajectory.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.agent import AgentState, agent, agent_bridge, as_solver
from inspect_ai.solver import Generate, Solver, TaskState, solver

from agon.sut.agent import DEFAULT_AGENT_PROMPT
from agon.sut.agent_messages import attach_agent_response


def _build_langgraph(llm: Any, tools: list[Any], prompt: str | None) -> Any:
    """Construct a LangGraph ReAct agent, preferring the non-deprecated entrypoint."""
    try:
        from langchain.agents import create_agent  # langgraph/langchain >= 1.0

        return create_agent(llm, tools, system_prompt=prompt)
    except Exception:
        from langgraph.prebuilt import create_react_agent  # deprecated fallback

        return create_react_agent(llm, tools, prompt=prompt)


@solver
def langgraph_react_sut(
    tools: list[Any], *, model: str = "inspect", prompt: str | None = None
) -> Solver:
    """SUT solver wrapping a bridged LangGraph ReAct agent. Real provider recommended."""

    @agent
    def _agent():
        async def execute(state: AgentState) -> AgentState:
            from langchain_openai import ChatOpenAI

            async with agent_bridge(state) as bridge:
                llm = ChatOpenAI(model=model, api_key="inspect", base_url="http://localhost/v1")
                graph = _build_langgraph(llm, tools, prompt or DEFAULT_AGENT_PROMPT)
                user = state.messages[-1].text
                await graph.ainvoke({"messages": [{"role": "user", "content": user}]})
            return bridge.state

        return execute

    agent_solver = as_solver(_agent())

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state = await agent_solver(state, generate)
        attach_agent_response(
            state, trace_id=f"{state.sample_id}_{getattr(state, 'epoch', 1)}"
        )
        return state

    return solve
