"""System-Under-Test layer: normalized request/response contract + Inspect solvers."""

from agon.sut.contract import (
    SUT_RESPONSE_KEY,
    SUTRequest,
    SUTResponse,
    TokenUsage,
    ToolCall,
    get_sut_response,
    map_http_response,
)
from agon.sut.solvers import (
    agon_generate_solver,
    build_solver,
    callable_solver,
    health_check,
)

__all__ = [
    "SUT_RESPONSE_KEY",
    "SUTRequest",
    "SUTResponse",
    "TokenUsage",
    "ToolCall",
    "agon_generate_solver",
    "build_solver",
    "callable_solver",
    "get_sut_response",
    "health_check",
    "map_http_response",
]
