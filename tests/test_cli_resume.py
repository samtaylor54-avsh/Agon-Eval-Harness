"""Phase 3 M8 - `agon resume` CLI wiring (offline)."""

from typer.testing import CliRunner

from agon.cli.app import app

runner = CliRunner()


def test_cli_resume_nothing_to_resume(tmp_path):
    log_dir = str(tmp_path / "logs")
    report_dir = str(tmp_path / "reports")
    # A clean mockllm run: cases pass/fail by score but none error -> nothing to resume.
    runner.invoke(
        app,
        ["run", "examples/datasets/rag_smoke.yaml", "--log-dir", log_dir,
         "--report-dir", report_dir, "--display", "none"],
    )
    result = runner.invoke(
        app,
        [
            "resume", "--latest", "--log-dir", log_dir,
            "--report-dir", report_dir, "--display", "none",
        ],
    )
    assert result.exit_code == 0
    assert "nothing to resume" in result.output


def test_cli_resume_unknown_run_id_aborts(tmp_path):
    result = runner.invoke(
        app, ["resume", "nope", "--log-dir", str(tmp_path), "--display", "none"]
    )
    assert result.exit_code == 2
    assert "[abort]" in result.output
