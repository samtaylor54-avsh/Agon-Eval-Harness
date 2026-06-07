from inspect_ai import Task, eval
from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver

from agon.evals.gait_triage.task import gait_dataset, gait_route_scorer


def test_dataset_has_ten_cases_with_critical_gait_004():
    samples = list(gait_dataset())
    assert len(samples) == 10
    by_id = {s.id: s for s in samples}
    crit = by_id["gait_004"]
    assert crit.metadata["risk_level"] == "critical"
    assert crit.target == "urgent_review"


@solver
def _fixed_routes(routes: dict[str, str]) -> Solver:
    """Test-only solver: emit a predetermined route per sample id (deterministic, safe)."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output = ModelOutput.from_content("mockllm/model", routes[str(state.sample_id)])
        return state

    return solve


def _gold_routes() -> dict[str, str]:
    # NOTE: Sample.target is a plain str in this Inspect version; read s.target, not s.target.text.
    return {str(s.id): s.target for s in gait_dataset()}


def _metrics(log):
    return {m.name: m for sc in log.results.scores for m in sc.metrics.values()}


def test_all_correct_passes_gate():
    task = Task(
        dataset=gait_dataset(), solver=_fixed_routes(_gold_routes()), scorer=gait_route_scorer()
    )
    log = eval(task, model="mockllm/model", display="none")[0]
    m = _metrics(log)
    assert m["critical_safety_gate"].value == 1.0
    assert m["accuracy"].value == 1.0


def test_single_critical_under_escalation_fails_gate_above_accuracy_floor():
    routes = _gold_routes()
    routes["gait_004"] = "routine"  # under-escalate the one CRITICAL case
    task = Task(dataset=gait_dataset(), solver=_fixed_routes(routes), scorer=gait_route_scorer())
    log = eval(task, model="mockllm/model", display="none")[0]
    m = _metrics(log)
    assert m["accuracy"].value == 0.9  # 9/10 correct -> would PASS on rate alone
    assert m["critical_safety_gate"].value == 0.0  # ...but the gate forces failure


def test_task_runs_end_to_end_offline():
    from agon.evals.gait_triage.task import gait_triage

    log = eval(gait_triage(), model="mockllm/model", display="none")[0]
    assert log.status == "success"
    metric_names = {m.name for sc in log.results.scores for m in sc.metrics.values()}
    assert "critical_safety_gate" in metric_names
