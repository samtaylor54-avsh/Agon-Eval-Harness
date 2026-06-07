"""Phase 3 M8 - error visibility + categorization in the digest."""

from agon.analysis.logs import _record_from_score, digest
from agon.schemas import AgonCase, AgonDataset, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval


def test_record_from_score_tags_scorer_error():
    rec = _record_from_score("t1", 0.0, {"errored": True, "category": "c", "risk_level": "low"})
    assert rec.errored is True
    assert rec.error_category == "scorer"


def test_record_from_score_clean_has_no_category():
    rec = _record_from_score("t1", 1.0, {"category": "c"})
    assert rec.errored is False
    assert rec.error_category is None


async def _boom_fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _two_case_ds():
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
    return AgonDataset(name="tax", dataset_version="v0", test_cases=cases)


def test_solver_error_is_visible_and_categorized(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_two_case_ds(), cfg, callable_fn=_boom_fn, display="none")
    d = digest(log)
    assert {r.test_id for r in d.records} == {"good", "bad"}  # "bad" no longer vanishes
    bad = d.record_map()["bad"]
    assert bad.errored is True
    # "connection refused" matches the NETWORK classifier's \bconnect\b marker
    assert bad.error_category == "network"
    assert d.error_count == 1
    assert d.error_count_by_category == {"network": 1}
