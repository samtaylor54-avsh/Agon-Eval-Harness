"""Phase 3 M6 — pass-rate confidence intervals flow into the digest and reports."""

import json
import re

from inspect_ai import eval
from inspect_ai.model import get_model

from agon.analysis.logs import digest
from agon.reporting.generator import render_json, render_markdown
from agon.schemas import AgonCase, AgonDataset, Interval, Recommendation, RunConfig, ScoringSpec
from agon.task import agon_task


def _offline_log(tmp_path, n=3):
    cases = [
        AgonCase(
            test_id=f"c{i}",
            name=f"c{i}",
            category="c",
            input={"user_message": "hi"},
            scoring=[ScoringSpec(type="exact_match")],
        )
        for i in range(n)
    ]
    dataset = AgonDataset(name="ci_suite", dataset_version="v0", test_cases=cases)
    task = agon_task(dataset, RunConfig(log_dir=str(tmp_path)))
    return eval(task, model=get_model("mockllm/model"), log_dir=str(tmp_path), display="none")[0]


def test_digest_has_pass_rate_ci(tmp_path):
    d = digest(_offline_log(tmp_path))
    assert isinstance(d.overall_pass_ci, Interval)
    assert d.n_cases == 3
    assert d.small_sample is True  # n=3 < 30
    assert 0.0 <= d.overall_pass_ci.low <= d.overall_pass_ci.high <= 1.0


def test_markdown_shows_ci_and_small_sample(tmp_path):
    d = digest(_offline_log(tmp_path))
    md = render_markdown(d, None, Recommendation.PASS)
    # The pass-rate row renders a [low%, high%] interval (not just any stray bracket).
    assert re.search(r"\[\d+\.\d+%, \d+\.\d+%\]", md)
    assert "Small sample" in md


def test_json_has_ci_block(tmp_path):
    d = digest(_offline_log(tmp_path))
    payload = json.loads(render_json(d, None, Recommendation.PASS))
    assert "overall_pass_ci" in payload
    assert payload["n_cases"] == 3
    assert payload["small_sample"] is True
