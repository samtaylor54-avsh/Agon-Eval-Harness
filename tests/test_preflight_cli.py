"""Phase 3 M9 -- preflight aborts a real-provider run with a missing key; offline unaffected."""

from pathlib import Path

from typer.testing import CliRunner

from agon.cli import app
from agon.cli.app import _preflight

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_preflight_helper_aborts_on_missing_key(monkeypatch):
    import typer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    raised = False
    try:
        _preflight("anthropic/claude-x", "litellm")
    except typer.Exit as exc:
        raised = True
        assert exc.exit_code == 2
    assert raised


def test_preflight_helper_passes_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _preflight("mockllm/model", "mockllm")  # no raise


def test_run_aborts_when_real_provider_key_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "run", str(FIXTURES / "mini.yaml"),
            "--model", "anthropic/claude-sonnet-4-5",
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(tmp_path / "reports"),
            "--display", "none",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "ANTHROPIC_API_KEY" in result.output
    assert "anthropic" in result.output
    assert not (tmp_path / "logs").exists() or not list((tmp_path / "logs").glob("*.eval"))
