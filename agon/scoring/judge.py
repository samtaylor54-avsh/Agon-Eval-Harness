"""JudgeClient — deterministic LLM-as-judge gateway (PRD §25.6, Task 6).

Wraps an Inspect model with ``temperature=0`` + fixed seed, enforces strict JSON parsing
with exactly one retry, and raises ``JudgeParseError`` on persistent failure so the engine
can mark the result ``ERROR`` rather than silently scoring zero.

A judge is itself an evaluated component (see calibration, T10) — never a ground truth.
"""

from __future__ import annotations

import json
import re
from typing import Any

from inspect_ai.model import GenerateConfig, Model, get_model

from agon.schemas import JudgeConfig

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


class JudgeParseError(Exception):
    """Raised when the judge output cannot be parsed as JSON after a retry."""


class JudgeClient:
    def __init__(self, config: JudgeConfig | None = None, model: Model | None = None) -> None:
        self.config = config or JudgeConfig()
        self._model = model  # injectable for tests (e.g. a mockllm Model)

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = get_model(self.config.model)
        return self._model

    async def generate_json(self, prompt: str, *, retries: int = 1) -> dict[str, Any]:
        """Generate and parse a JSON object, retrying once on parse failure."""
        gen_config = GenerateConfig(
            temperature=self.config.temperature,
            seed=self.config.seed,
            max_tokens=self.config.max_tokens,
        )
        last_text = ""
        for _attempt in range(retries + 1):
            output = await self.model.generate(prompt, config=gen_config)
            last_text = output.completion or ""
            parsed = _try_parse(last_text)
            if parsed is not None:
                return parsed
        raise JudgeParseError(
            f"judge did not return valid JSON after {retries + 1} attempt(s): {last_text!r}"
        )


def _try_parse(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    match = _JSON_OBJ.search(text)
    if match:
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None
