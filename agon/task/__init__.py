"""Task assembly: build an Inspect Task from an AgonDataset + RunConfig and run it."""

from agon.task.builder import (
    agent_task,
    agon_task,
    resolve_model,
    run_agent_eval,
    run_eval,
)

__all__ = [
    "agent_task",
    "agon_task",
    "resolve_model",
    "run_agent_eval",
    "run_eval",
]
