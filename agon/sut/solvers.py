"""Inspect solvers implementing the SUT adapters (PRD §22.1, §8.3).

- ``agon_generate_solver`` — default path: run the configured model (``mockllm`` offline,
  or a real provider opt-in) via Inspect's ``generate`` and normalize the output.
- ``callable_solver`` — wrap an in-process ``async fn(SUTRequest) -> SUTResponse`` (tests,
  homegrown pipelines).
- ``http_solver`` — POST the request to an external RAG/agent service and field-map the JSON.

Every solver attaches a normalized ``SUTResponse`` to ``state.metadata`` so scorers are
agnostic to how the response was produced.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import time_limit

from agon.dataset import METADATA_CASE_KEY
from agon.schemas import SUTConfig
from agon.sut.contract import (
    SUT_RESPONSE_KEY,
    SUTRequest,
    SUTResponse,
    TokenUsage,
    map_http_response,
)

SUTCallable = Callable[[SUTRequest], Awaitable[SUTResponse]]


def _build_request(state: TaskState) -> SUTRequest:
    meta = state.metadata or {}
    documents = list(meta.get("documents", []) or [])
    session_id = f"{state.sample_id}_{getattr(state, 'epoch', 1)}"
    return SUTRequest(
        user_message=state.input_text,
        documents=documents,
        session_id=session_id,
    )


def _attach(state: TaskState, response: SUTResponse) -> None:
    if state.metadata is None:  # defensive; Inspect always provides a dict
        state.metadata = {}
    state.metadata[SUT_RESPONSE_KEY] = response.model_dump(mode="json")


def _time_limit_ctx(
    state: TaskState, default_time_limit: float | None
) -> AbstractContextManager[None]:
    """Per-sample wall-clock guard: the case's override wins, else the run-level default.

    A breach raises inspect's LimitExceededError, which surfaces as sample.limit(type="time").
    """
    case = (state.metadata or {}).get(METADATA_CASE_KEY) or {}
    effective = case.get("sample_time_limit") or default_time_limit
    return time_limit(effective) if effective else nullcontext()


@solver
def agon_generate_solver(default_time_limit: float | None = None) -> Solver:
    """Default solver: generate with the configured model, then normalize the output."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        with _time_limit_ctx(state, default_time_limit):
            state = await generate(state)
        usage = getattr(state.output, "usage", None)
        token_usage = (
            TokenUsage(
                input=usage.input_tokens,
                output=usage.output_tokens,
                total=usage.total_tokens,
            )
            if usage is not None
            else TokenUsage()
        )
        response = SUTResponse(
            final_answer=state.output.completion or "",
            trace_id=f"{state.sample_id}_{getattr(state, 'epoch', 1)}",
            token_usage=token_usage,
            error=state.output.error,
        )
        _attach(state, response)
        return state

    return solve


@solver
def callable_solver(fn: SUTCallable, default_time_limit: float | None = None) -> Solver:
    """Wrap an in-process async callable as the SUT."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        request = _build_request(state)
        with _time_limit_ctx(state, default_time_limit):
            response = await fn(request)
        if not response.trace_id:
            response = response.model_copy(update={"trace_id": request.session_id})
        state.output = ModelOutput.from_content(model="callable", content=response.final_answer)
        _attach(state, response)
        return state

    return solve


@solver
def http_solver(config: SUTConfig, default_time_limit: float | None = None) -> Solver:
    """POST the normalized request to an external service and field-map the response."""

    if not config.endpoint_url:
        raise ValueError("http adapter requires endpoint_url")

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        import httpx  # transitive dep via inspect-ai; imported lazily (opt-in path)

        request = _build_request(state)
        async with httpx.AsyncClient(timeout=60.0) as client:
            with _time_limit_ctx(state, default_time_limit):
                resp = await client.post(
                    config.endpoint_url,
                    json=request.model_dump(),
                    headers=config.headers,
                )
                resp.raise_for_status()
                payload = resp.json()
        response = map_http_response(payload, config.field_map)
        if not response.trace_id:
            response = response.model_copy(update={"trace_id": request.session_id})
        state.output = ModelOutput.from_content(model="http", content=response.final_answer)
        _attach(state, response)
        return state

    return solve


def build_solver(
    config: SUTConfig,
    *,
    callable_fn: SUTCallable | None = None,
    default_time_limit: float | None = None,
) -> Solver:
    """Construct the solver for a given SUT configuration."""
    adapter = config.adapter
    if adapter in ("mockllm", "litellm"):
        return agon_generate_solver(default_time_limit)
    if adapter == "callable":
        if callable_fn is None:
            raise ValueError("callable adapter requires a callable_fn")
        return callable_solver(callable_fn, default_time_limit)
    if adapter == "http":
        return http_solver(config, default_time_limit)
    raise ValueError(f"unknown SUT adapter: {adapter!r}")


async def health_check(config: SUTConfig, *, callable_fn: SUTCallable | None = None) -> bool:
    """Pre-flight reachability check (PRD §22.1). Called once per run."""
    if config.adapter in ("mockllm", "litellm", "callable"):
        return True
    if config.adapter == "http":
        if not config.endpoint_url:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(config.endpoint_url, headers=config.headers)
                return resp.status_code < 500
        except Exception:
            return False
    return False
