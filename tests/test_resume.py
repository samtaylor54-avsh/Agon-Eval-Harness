"""Phase 3 M8 - resume orchestrator (end to end, offline via the callable adapter)."""

from agon.analysis.logs import digest
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval
from agon.task.resume import resume_run


async def _failing(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


async def _healthy(req):
    return SUTResponse(final_answer="the answer")


def _ds():
    cases = [
        AgonCase(
            test_id="good", name="good", category="c", input={"user_message": "hi"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
        AgonCase(
            test_id="bad", name="bad", category="c", input={"user_message": "boom"},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        ),
    ]
    return AgonDataset(name="resume_suite", dataset_version="v0", test_cases=cases)


def _cfg(tmp_path):
    return RunConfig(
        log_dir=str(tmp_path),
        report_dir=str(tmp_path / "reports"),
        sut=SUTConfig(adapter="callable"),
    )


def test_resume_recovers_errored_case(tmp_path):
    cfg = _cfg(tmp_path)
    first = run_eval(_ds(), cfg, callable_fn=_failing, display="none")
    assert digest(first).record_map()["bad"].errored is True
    run_id = first.eval.run_id

    result = resume_run(cfg, run_id, callable_fn=_healthy, display="none")
    assert result["resumed"] == 1
    merged = result["digest"]
    assert merged.record_map()["bad"].passed is True   # recovered
    assert merged.record_map()["good"].passed is True   # carried over from the prior run
    assert merged.error_count == 0
    assert merged.run_id != run_id
    assert result["written"]  # merged report files were written


def test_resume_latest_when_no_run_id(tmp_path):
    cfg = _cfg(tmp_path)
    run_eval(_ds(), cfg, callable_fn=_failing, display="none")
    result = resume_run(cfg, None, callable_fn=_healthy, display="none")
    assert result["resumed"] == 1
    assert result["digest"].record_map()["bad"].passed is True


def test_resume_nothing_to_resume(tmp_path):
    cfg = _cfg(tmp_path)
    run_eval(_ds(), cfg, callable_fn=_healthy, display="none")  # all complete
    result = resume_run(cfg, None, callable_fn=_healthy, display="none")
    assert result["resumed"] == 0
