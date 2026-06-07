"""Phase 3 M9 — headline guard: a secret never lands in a written report artifact."""

from pathlib import Path

from typer.testing import CliRunner

from agon.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"

# An sk-ant- prefixed token with a >=16-char body so the prefix backstop catches it.
PLANTED = "sk-ant-ABCDEFGHIJKLMNOP1234"


def _run(tmp_path):
    reports = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "run", str(FIXTURES / "mini.yaml"),
            "--system-version", f"build-{PLANTED}",
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(reports),
            "--display", "none",
        ],
    )
    return reports, result


def test_planted_key_is_redacted_from_all_report_formats(tmp_path):
    reports, result = _run(tmp_path)
    assert result.exit_code in (0, 1), result.output  # gate code, not an abort
    written = list(reports.glob("*.report.md")) + \
        list(reports.glob("*.report.json")) + \
        list(reports.glob("*.report.junit.xml"))
    assert len(written) == 3
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert PLANTED not in text, f"raw key leaked into {path.name}"
    # prove the value actually reached the artifacts (md/json carry system_version) and was masked
    masked_seen = any("sk-ant-...1234" in p.read_text(encoding="utf-8") for p in written)
    assert masked_seen, "masked form not found -- redaction path not exercised"
