"""Your System-Under-Test adapter: an async function mapping a request to a response.

The harness calls this once per test case. Put your real system behind it (HTTP call,
in-process model, agent, ...). The CLI cannot wire a Python callable, so use run.py to drive it.
"""

from __future__ import annotations

from agon.sut import SUTRequest, SUTResponse


async def my_sut(req: SUTRequest) -> SUTResponse:
    # req.user_message is the case input; req.documents / req.session_id are also available.
    # TODO: call your system here and return its answer.
    answer = f"echo: {req.user_message}"
    return SUTResponse(final_answer=answer)
