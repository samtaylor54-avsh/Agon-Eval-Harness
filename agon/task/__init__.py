"""Task assembly: build an Inspect Task from an AgonDataset + RunConfig and run it."""

from agon.task.builder import agon_task, resolve_model, run_eval

__all__ = ["agon_task", "resolve_model", "run_eval"]
