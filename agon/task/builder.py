"""Assemble and run an Inspect ``Task`` from an ``AgonDataset`` + ``RunConfig`` (T7)."""

from __future__ import annotations

from inspect_ai import Epochs, Task, eval
from inspect_ai.dataset import MemoryDataset
from inspect_ai.log import EvalLog

from agon.dataset import to_samples
from agon.schemas import AgonDataset, RunConfig
from agon.scoring import JudgeClient, flake_reducer
from agon.scoring.inspect_scorer import agon_scorer
from agon.sut import build_solver
from agon.sut.solvers import SUTCallable


def resolve_model(config: RunConfig) -> str:
    """Resolve the Inspect model string for the configured adapter.

    For ``http`` / ``callable`` adapters the solver overrides the output, so a mock model is
    used as a no-op. ``mockllm`` is the offline default; ``litellm`` uses the configured model.
    """
    adapter = config.sut.adapter
    if adapter == "litellm":
        if not config.sut.model:
            raise ValueError("litellm adapter requires sut.model (e.g. 'openai/gpt-4o')")
        return config.sut.model
    return "mockllm/model"


def agon_task(
    dataset: AgonDataset,
    config: RunConfig,
    *,
    callable_fn: SUTCallable | None = None,
    judge: JudgeClient | None = None,
) -> Task:
    judge = judge or JudgeClient(config.judge)
    solver = build_solver(config.sut, callable_fn=callable_fn)
    scorer = agon_scorer(judge=judge)

    epochs: int | Epochs = config.epochs
    if config.epochs > 1:
        epochs = Epochs(config.epochs, flake_reducer(config.flake_rule, config.epochs))

    return Task(
        dataset=MemoryDataset(samples=to_samples(dataset), name=dataset.name),
        solver=solver,
        scorer=scorer,
        epochs=epochs,
        name=dataset.name,
        metadata={
            "dataset_version": dataset.dataset_version,
            "system_version": config.system_version,
        },
    )


def run_eval(
    dataset: AgonDataset,
    config: RunConfig,
    *,
    callable_fn: SUTCallable | None = None,
    judge: JudgeClient | None = None,
    display: str = "none",
) -> EvalLog:
    """Run the eval and return the (single) EvalLog. Per-sample errors never abort the run."""
    task = agon_task(dataset, config, callable_fn=callable_fn, judge=judge)
    logs = eval(
        task,
        model=resolve_model(config),
        log_dir=config.log_dir,
        display=display,
        max_connections=config.max_connections,
        fail_on_error=config.fail_fast,  # False → contain per-sample failures
    )
    return logs[0]
