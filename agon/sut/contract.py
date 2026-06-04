"""Normalized SUT request/response contract (PRD §8.3, §23.2).

The harness must not care whether the SUT is a hosted model, a RAG service, or an
in-process function. Adapters speak this contract; scorers read ``SUTResponse`` from the
Inspect ``TaskState`` metadata (synthesizing a minimal one from the model output if absent).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Key under TaskState.metadata that holds the normalized SUTResponse.
SUT_RESPONSE_KEY = "sut_response"


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    error: str | None = None


class SUTRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: str
    documents: list[str] = Field(default_factory=list)
    session_id: str
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class SUTResponse(BaseModel):
    """Normalized output of any System-Under-Test."""

    model_config = ConfigDict(extra="forbid")

    final_answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    retrieved_documents: list[str] = Field(default_factory=list)
    trace_id: str = ""
    latency_ms: float = 0.0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    raw_trace: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None  # model-level error (non-fatal)


def map_http_response(payload: dict[str, Any], field_map: dict[str, str]) -> SUTResponse:
    """Map an arbitrary HTTP JSON body to ``SUTResponse`` via ``field_map``.

    ``field_map`` maps SUTResponse field name -> dotted path into ``payload``. Unmapped
    fields fall back to the same key in ``payload`` when present. Missing keys use defaults.
    """
    resolved: dict[str, Any] = {}
    targets = [
        "final_answer",
        "citations",
        "tool_calls",
        "retrieved_documents",
        "trace_id",
        "latency_ms",
    ]
    for field in targets:
        path = field_map.get(field, field)
        value = _dig(payload, path)
        if value is not None:
            resolved[field] = value
    resolved.setdefault("final_answer", "")
    return SUTResponse.model_validate(resolved)


def _dig(payload: dict[str, Any], dotted: str) -> Any:
    cur: Any = payload
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def get_sut_response(state: Any) -> SUTResponse:
    """Read the normalized SUTResponse from a TaskState, or synthesize from the output.

    Scorers call this so they never depend on how the response was produced.
    """
    meta = getattr(state, "metadata", None) or {}
    stored = meta.get(SUT_RESPONSE_KEY)
    if stored is not None:
        if isinstance(stored, SUTResponse):
            return stored
        return SUTResponse.model_validate(stored)
    # Fall back to the model completion.
    completion = ""
    output = getattr(state, "output", None)
    if output is not None:
        completion = getattr(output, "completion", "") or ""
    return SUTResponse(final_answer=completion)
