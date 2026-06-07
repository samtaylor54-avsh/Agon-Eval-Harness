"""Phase 3 M9 -- `agon doctor` masks secrets and never prints a raw key."""

from typer.testing import CliRunner

from agon.cli import app

runner = CliRunner()


def test_doctor_masks_set_key_and_marks_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-DOCTORKEY00000000")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "sk-ant-DOCTORKEY00000000" not in result.output  # raw key never printed
    assert "sk-ant-...0000" in result.output
    assert "OPENAI_API_KEY: (not set)" in result.output


def test_doctor_model_flag_reports_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor", "--model", "anthropic/claude-x"])
    assert result.exit_code == 0, result.output
    assert "MISSING" in result.output
    assert "ANTHROPIC_API_KEY" in result.output


def test_doctor_model_flag_reports_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PRESENTKEY0000000")
    result = runner.invoke(app, ["doctor", "--model", "anthropic/claude-x"])
    assert result.exit_code == 0, result.output
    assert "keys present" in result.output
