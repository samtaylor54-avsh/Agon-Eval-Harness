# ADR-0004 — Native ReAct agent for offline eval; LangGraph bridge experimental

- **Status:** Accepted
- **Date:** 2026-06-05
- **Deciders:** Samuel R. Taylor
- **Context:** Phase 2 M2 (agent evaluation)

## Context

M2 evaluates tool-using agents. The Phase 2 scope chose to **bridge the real LangGraph
`create_react_agent`** via Inspect's `agent_bridge()` (highest external validity). On building it,
the offline path hit concrete, current incompatibilities (inspect-ai 0.3.235, langgraph 1.0):

1. **inspect-ai bridge bug:** `init_google_request_patch()` calls
   `importlib.util.find_spec("google.genai")`, which *raises* `ModuleNotFoundError` (rather than
   returning `None`) when the `google` namespace isn't installed at all — crashing the bridge.
2. **langchain-openai ↔ bridge mismatch:** current `langchain-openai` calls an OpenAI client
   method the bridge doesn't implement (`'ChatCompletion' object has no attribute 'parse'`), so
   the offline `mockllm` path through the bridge fails.
3. **Deprecation:** `langgraph.prebuilt.create_react_agent` is deprecated in langgraph 1.0 in
   favor of `langchain.agents.create_agent`.

This is the version-churn fragility the Phase 2 research flagged.

## Decision

**Two-track agent SUT:**

1. **Native Inspect `react()` is the primary, offline/CI agent SUT** (`agon/sut/agent.py:react_sut`).
   It runs cleanly offline (driven deterministically by a `mockllm` callable policy), needs no
   provider keys, and isn't coupled to the langchain/openai version matrix.
2. **LangGraph bridge is shipped as experimental** (`agon/sut/langgraph.py:langgraph_react_sut`)
   for evaluating a *real deployed* LangGraph agent against a real provider. Its limitations
   (above) are documented inline; it prefers `langchain.agents.create_agent` when available and
   falls back to the deprecated entrypoint. Its end-to-end test is **gated/skipped** offline.

The crucial point: **the agent scorers are identical regardless of which agent produced the
trajectory.** Both SUTs normalize their message history to the same `SUTResponse` (via
`agon/sut/agent_messages.py`), so `tool_use`, `planning`, and `step_efficiency` score either one.

## What M2 delivers

- `tool_use` scorer (PRD §25.11, deferred from Phase 1): selection / forbidden / valid-args /
  recovery over the tool-call trajectory.
- `planning` (gather-before-acting) and `step_efficiency` (penalize redundant calls) scorers.
- `react_sut` (native agent SUT) + message normalization so agents are first-class SUTs.
- Offline example (`examples/agent_quickstart.py`, `examples/datasets/agent_smoke.yaml`): a
  ReAct agent over one tool, with a deliberately-failing case the harness catches as
  `tool_omission`.

## Consequences

- **Positive:** agent evaluation works offline and in CI today; robust to dependency updates.
- **Negative:** the headline "evaluate your real LangGraph agent" path is experimental until the
  inspect-ai/langchain ecosystem aligns. Revisit when (a) inspect-ai fixes the google `find_spec`
  bug and the OpenAI `.parse` gap, and (b) the `create_agent` migration settles.
- **Workaround note:** to try the bridge, install a `google` namespace provider (e.g.
  `googleapis-common-protos`) and use a real provider model rather than `mockllm`.
