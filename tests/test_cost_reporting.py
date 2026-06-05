"""Phase 3 M5 — cost summary flows into the RunDigest and the md/json reports."""

import json

from inspect_ai import eval
from inspect_ai.model import get_model

from agon.analysis.logs import digest
from agon.cost import CostSummary
from agon.reporting.generator import render_json, render_markdown
from agon.schemas import AgonCase, AgonDataset, Recommendation, RunConfig, ScoringSpec
from agon.task import agon_task


def _offline_log(tmp_path):
    dataset = AgonDataset(
        name="cost_suite",
        dataset_version="v0",
        test_cases=[
            AgonCase(
                test_id="c1",
                name="c1",
                category="c",
                input={"user_message": "hi"},
                scoring=[ScoringSpec(type="exact_match")],
            )
        ],
    )
    task = agon_task(dataset, RunConfig(log_dir=str(tmp_path)))
    return eval(task, model=get_model("mockllm/model"), log_dir=str(tmp_path), display="none")[0]


def test_digest_carries_cost_summary(tmp_path):
    d = digest(_offline_log(tmp_path))
    assert isinstance(d.cost, CostSummary)
    # Offline mockllm -> no priced usage burned -> $0.
    assert d.cost.total_usd == 0.0


def test_markdown_has_cost_section(tmp_path):
    d = digest(_offline_log(tmp_path))
    md = render_markdown(d, None, Recommendation.PASS)
    assert "Cost & usage" in md
    assert "Total tokens" in md


def test_json_has_cost_block(tmp_path):
    d = digest(_offline_log(tmp_path))
    payload = json.loads(render_json(d, None, Recommendation.PASS))
    assert "cost" in payload
    assert payload["cost"]["total_usd"] == 0.0
    assert "as_of" in payload["cost"]
