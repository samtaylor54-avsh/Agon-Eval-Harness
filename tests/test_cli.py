"""T7 — end-to-end CLI run/report/compare (offline via mockllm)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agon.analysis import latest_run
from agon.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def test_run_emits_artifacts_and_gate_code(tmp_path):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "run", str(FIXTURES / "mini.yaml"),
            "--log-dir", str(logs),
            "--report-dir", str(reports),
            "--display", "none",
        ],
    )
    # mockllm default output fails every case → fail gate (exit 1), deterministically.
    assert result.exit_code == 1, result.stdout
    md = list(reports.glob("*.report.md"))
    xml = list(reports.glob("*.report.junit.xml"))
    js = list(reports.glob("*.report.json"))
    assert md and xml and js
    assert "Agon Eval Report" in md[0].read_text(encoding="utf-8")


def test_report_command_regenerates(tmp_path):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    runner.invoke(
        app,
        ["run", str(FIXTURES / "mini.yaml"), "--log-dir", str(logs),
         "--report-dir", str(reports), "--display", "none"],
    )
    run_id = latest_run(logs).eval.run_id
    result = runner.invoke(
        app,
        ["report", run_id, "--log-dir", str(logs), "--report-dir", str(reports / "regen")],
    )
    assert result.exit_code == 0, result.stdout
    assert "recommendation:" in result.stdout


def test_compare_two_identical_runs_no_regression(tmp_path):
    logs = tmp_path / "logs"
    for _ in range(2):
        runner.invoke(
            app,
            ["run", str(FIXTURES / "mini.yaml"), "--log-dir", str(logs),
             "--report-dir", str(tmp_path / "r"), "--display", "none"],
        )
    from inspect_ai.log import list_eval_logs, read_eval_log

    run_ids = [read_eval_log(i.name).eval.run_id for i in list_eval_logs(str(logs))]
    assert len(run_ids) == 2
    result = runner.invoke(
        app, ["compare", run_ids[0], run_ids[1], "--log-dir", str(logs)]
    )
    # Identical mockllm runs → no new failures → no regression → exit 0.
    assert result.exit_code == 0, result.stdout
    assert "regression detected: False" in result.stdout


def test_run_missing_dataset_aborts(tmp_path):
    result = runner.invoke(
        app, ["run", str(tmp_path / "nope.yaml"), "--display", "none"]
    )
    assert result.exit_code == 2


def test_retrieve_command_offline(tmp_path):
    pytest.importorskip("rank_bm25")
    result = runner.invoke(
        app,
        [
            "retrieve",
            str(EXAMPLES / "retrieval" / "corpus.yaml"),
            str(EXAMPLES / "retrieval" / "qrels.yaml"),
            "--k", "5",
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(tmp_path / "reports"),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "recall@5=" in result.stdout
    assert list((tmp_path / "reports").glob("*.retrieval.md"))
