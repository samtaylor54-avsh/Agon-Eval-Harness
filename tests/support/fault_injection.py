"""Deterministic offline mockllm policies that simulate provider faults (Phase 3 M5 tests).

No randomness, no wall-clock: failures are decided by the user message text and a per-sample
call counter, so runs are fully reproducible. A raised exception surfaces as a model/sample error.
"""

from __future__ import annotations

from inspect_ai.model import ModelOutput

PERMANENT_FAIL_TAG = "[boom]"


def _last_user(messages) -> str:
    items = [m for m in messages if getattr(m, "role", None) == "user"]
    return items[-1].text if items else ""


class FlakyPolicy:
    """Raise on the first ``transient_failures`` calls *per sample*, then succeed.

    Samples whose message contains ``PERMANENT_FAIL_TAG`` always raise.
    """

    def __init__(self, transient_failures: int = 0):
        self.transient_failures = transient_failures
        self._calls: dict[str, int] = {}

    def __call__(self, messages, tools, tool_choice, config) -> ModelOutput:
        user = _last_user(messages)
        if PERMANENT_FAIL_TAG in user:
            raise RuntimeError("simulated permanent model error")
        seen = self._calls.get(user, 0)
        self._calls[user] = seen + 1
        if seen < self.transient_failures:
            raise RuntimeError("simulated transient model error")
        return ModelOutput.from_content("mockllm", "ok")
