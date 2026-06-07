"""Assemble and run an Inspect ``Task`` from an ``AgonDataset`` + ``RunConfig`` (T7)."""

from __future__ import annotations

from typing import Any

from inspect_ai import Epochs, Task, eval
from inspect_ai.dataset import MemoryDataset
from inspect_ai.log import EvalLog

from agon.dataset import to_samples
from agon.schemas import AgonDataset, RunConfig
from agon.scoring import JudgeClient, flake_reducer
from agon.scoring.inspect_scorer import agon_scorer
from agon.sut import build_solver, react_sut
from agon.sut.solvers import SUTCallable


def resilience_eval_kwargs(config: RunConfig) -> dict[str, Any]:
    """Map RunConfig resilience knobs to inspect_ai.eval() kwargs.

    Generation knobs (max_retries/timeout/attempt_timeout/max_connections) ride eval()'s
    **GenerateConfigArgs; orchestration knobs (retry_on_error/time_limit/fail_on_error) are
    explicit eval() params. Optional (None) knobs are omitted so Inspect keeps its own defaults.
    """
    r = config.resilience
    kwargs: dict[str, Any] = {
        "max_connections": config.max_connections,
        "max_retries": r.max_retries,
        "retry_on_error": r.retry_on_error,
        "fail_on_error": r.fail_on_error,
    }
    if r.request_timeout is not None:
        kwargs["timeout"] = r.request_timeout
    if r.attempt_timeout is not None:
        kwargs["attempt_timeout"] = r.attempt_timeout
    # sample_time_limit is enforced per-sample in the solver (so per-case overrides win),
    # not via eval()'s global time_limit.
    return kwargs


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
    solver = build_solver(
        config.sut,
        callable_fn=callable_fn,
        default_time_limit=config.resilience.sample_time_limit,
    )
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
        **resilience_eval_kwargs(config),
    )
    return logs[0]


def agent_task(
    dataset: AgonDataset,
    tools: list[Any],
    config: RunConfig,
    *,
    prompt: str | None = None,
    attempts: int = 1,
    judge: JudgeClient | None = None,
) -> Task:
    """Build a Task whose SUT is a native ReAct agent over the given tools (M2)."""
    judge = judge or JudgeClient(config.judge)
    epochs: int | Epochs = config.epochs
    if config.epochs > 1:
        epochs = Epochs(config.epochs, flake_reducer(config.flake_rule, config.epochs))
    return Task(
        dataset=MemoryDataset(samples=to_samples(dataset), name=dataset.name),
        solver=react_sut(tools, prompt=prompt, attempts=attempts),
        scorer=agon_scorer(judge=judge),
        epochs=epochs,
        name=dataset.name,
        metadata={
            "dataset_version": dataset.dataset_version,
            "system_version": config.system_version,
        },
    )


def run_agent_eval(
    dataset: AgonDataset,
    tools: list[Any],
    config: RunConfig,
    *,
    prompt: str | None = None,
    attempts: int = 1,
    judge: JudgeClient | None = None,
    display: str = "none",
) -> EvalLog:
    """Run a ReAct-agent eval and return the EvalLog."""
    task = agent_task(dataset, tools, config, prompt=prompt, attempts=attempts, judge=judge)
    logs = eval(
        task,
        model=resolve_model(config),
        log_dir=config.log_dir,
        display=display,
        **resilience_eval_kwargs(config),
    )
    return logs[0]
