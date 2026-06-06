"""M7 — `agon run --plugin` loads a user scorer; missing scorer aborts with a hint."""

from __future__ import annotations

import sys

from typer.testing import CliRunner

from agon.cli import app
from agon.scoring import default_registry

runner = CliRunner()

DATASET = """
name: plugin_demo
test_cases:
  - test_id: p_001
    name: uses a plugin scorer
    category: demo
    input:
      user_message: "hi"
    expected:
      expected_answer: "hi"
    scoring:
      - {type: dummy_plugin_scorer, weight: 1.0, pass_threshold: 1.0}
"""

SCORER = '''
from agon.scoring.base import ScoreOutcome, register


@register
class _DummyPluginScorer:
    scorer_type = "dummy_plugin_scorer"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        return ScoreOutcome(
            scorer_type=self.scorer_type, native_score=True, normalized_score=1.0
        )
'''


def _cleanup():
    default_registry._scorers.pop("dummy_plugin_scorer", None)
    for mod in [m for m in sys.modules if m.startswith("agon_plugin_")]:
        sys.modules.pop(mod, None)


def test_run_with_plugin_resolves_scorer(tmp_path):
    ds = tmp_path / "ds.yaml"
    ds.write_text(DATASET, encoding="utf-8")
    sc = tmp_path / "sc.py"
    sc.write_text(SCORER, encoding="utf-8")
    try:
        result = runner.invoke(
            app,
            ["run", str(ds), "--plugin", str(sc),
             "--log-dir", str(tmp_path / "logs"),
             "--report-dir", str(tmp_path / "reports"),
             "--display", "none"],
        )
        # Scorer resolved -> no abort (exit 2). dummy scorer passes -> not exit 2 either way.
        assert result.exit_code != 2, result.output
        assert "loaded plugin scorers: dummy_plugin_scorer" in result.output
    finally:
        _cleanup()


def test_run_without_plugin_aborts_with_hint(tmp_path):
    ds = tmp_path / "ds.yaml"
    ds.write_text(DATASET, encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", str(ds),
         "--log-dir", str(tmp_path / "logs"),
         "--report-dir", str(tmp_path / "reports"),
         "--display", "none"],
    )
    assert result.exit_code == 2, result.output
    assert "dummy_plugin_scorer" in result.output
    assert "--plugin" in result.output
