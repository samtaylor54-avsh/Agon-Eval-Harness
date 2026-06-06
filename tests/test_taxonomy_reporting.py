"""Phase 3 M8 - error taxonomy in markdown / json / junit reports."""

import json

from agon.analysis.logs import digest
from agon.reporting.generator import render_json, render_junit_xml, render_markdown
from agon.schemas import AgonCase, AgonDataset, Recommendation, RunConfig, ScoringSpec, SUTConfig
from agon.sut.contract import SUTResponse
from agon.task.builder import run_eval


async def _boom_fn(req):
    if "boom" in req.user_message:
        raise RuntimeError("connection refused")
    return SUTResponse(final_answer="the answer")


def _ds(messages):
    cases = [
        AgonCase(
            test_id=tid, name=tid, category="c", input={"user_message": msg},
            expected={"expected_answer": "the answer"}, scoring=[ScoringSpec(type="exact_match")],
        )
        for tid, msg in messages.items()
    ]
    return AgonDataset(name="tax", dataset_version="v0", test_cases=cases)


def _digest_with_error(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds({"good": "hi", "bad": "boom"}), cfg, callable_fn=_boom_fn, display="none")
    return digest(log)


def _digest_clean(tmp_path):
    cfg = RunConfig(log_dir=str(tmp_path), sut=SUTConfig(adapter="callable"))
    log = run_eval(_ds({"good": "hi"}), cfg, callable_fn=_boom_fn, display="none")
    return digest(log)


def test_json_has_error_by_category(tmp_path):
    d = _digest_with_error(tmp_path)
    payload = json.loads(render_json(d, None, Recommendation.FAIL))
    assert payload["error_count_by_category"] == {"network": 1}


def test_markdown_breakdown_present_when_errors(tmp_path):
    d = _digest_with_error(tmp_path)
    md = render_markdown(d, None, Recommendation.FAIL)
    assert "Errors by category" in md
    assert "network: 1" in md


def test_markdown_breakdown_absent_when_clean(tmp_path):
    d = _digest_clean(tmp_path)
    md = render_markdown(d, None, Recommendation.PASS)
    assert "Errors by category" not in md


def test_junit_error_message_uses_category(tmp_path):
    d = _digest_with_error(tmp_path)
    xml = render_junit_xml(d)
    assert 'message="network"' in xml
