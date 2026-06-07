"""Phase 3 M8 - resume building blocks (select / reconstruct / merge)."""

from types import SimpleNamespace

from inspect_ai.scorer import Score

from agon.analysis.logs import SampleRecord, build_digest
from agon.cost import CostSummary
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval
from agon.task.resume import cases_from_log, merge_digests, select_incomplete


async def _boom_fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
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


def _record(test_id, passed, errored=False, category=None):
    return SampleRecord(
        test_id=test_id, passed=passed, composite_score=1.0 if passed else 0.0,
        category="c", risk_level="medium", errored=errored, error_category=category,
    )


def test_select_incomplete_picks_only_errored(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds(), cfg, callable_fn=_boom_fn, display="none")
    incomplete = select_incomplete(log)
    assert [str(s.id) for s in incomplete] == ["bad"]


def test_cases_from_log_rebuilds_failed_cases(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds(), cfg, callable_fn=_boom_fn, display="none")
    sub = cases_from_log(log, select_incomplete(log))
    assert [c.test_id for c in sub.test_cases] == ["bad"]


def test_merge_digests_prefers_rerun_and_recomputes():
    prior = build_digest(
        [_record("good", True), _record("bad", False, errored=True, category="network")],
        run_id="r0", task="t", model="m", system_version="v", dataset_version="d",
        created="t0", cost=CostSummary(),
    )
    rerun = build_digest(
        [_record("bad", True)],
        run_id="r1", task="t", model="m", system_version="v", dataset_version="d",
        created="t1", cost=CostSummary(),
    )
    merged = merge_digests(prior, rerun)
    assert merged.run_id == "r1"
    assert merged.record_map()["bad"].passed is True
    assert merged.overall_pass_rate == 1.0
    assert merged.error_count == 0
    assert merged.error_count_by_category == {}
    assert merged.n_cases == 2  # prior-only "good" survived the merge, not just rerun's "bad"
    assert "good" in merged.record_map()


def test_select_incomplete_handles_score_without_metadata():
    # A scored sample whose Score.metadata is None must not crash (Inspect allows None metadata).
    from agon.analysis.logs import AGON_SCORER

    sample = SimpleNamespace(
        id="s1", error=None, limit=None, scores={AGON_SCORER: Score(value=1.0)}
    )
    log = SimpleNamespace(samples=[sample])
    # Clean pass with no metadata -> not incomplete, and no AttributeError.
    assert select_incomplete(log) == []


def test_select_incomplete_picks_limited_sample():
    from agon.analysis.logs import AGON_SCORER

    # A sample that hit a limit must be selected even if it has a (zero) score.
    sample = SimpleNamespace(
        id="s1", error=None, limit=object(), scores={AGON_SCORER: Score(value=0.0)}
    )
    assert select_incomplete(SimpleNamespace(samples=[sample])) == [sample]


def test_select_incomplete_picks_scorer_error():
    from agon.analysis.logs import AGON_SCORER

    # A scored sample whose scorer metadata says errored=True must be selected.
    score = Score(value=0.0, metadata={"errored": True})
    sample = SimpleNamespace(id="s1", error=None, limit=None, scores={AGON_SCORER: score})
    assert select_incomplete(SimpleNamespace(samples=[sample])) == [sample]
