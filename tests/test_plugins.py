"""M7 — external scorer plugin loader (dotted module + .py file path)."""

from __future__ import annotations

import sys

import pytest

from agon.scoring import default_registry
from agon.scoring.plugins import PluginLoadError, load_plugins

DUMMY = '''
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


@pytest.fixture
def clean_registry():
    """Snapshot/restore the registry + sys.modules so plugin tests don't leak."""
    before_keys = set(default_registry.keys())
    before_mods = set(sys.modules)
    yield
    for key in set(default_registry.keys()) - before_keys:
        default_registry._scorers.pop(key, None)
    for mod in set(sys.modules) - before_mods:
        sys.modules.pop(mod, None)


def test_load_from_file_path(tmp_path, clean_registry):
    f = tmp_path / "my_scorer.py"
    f.write_text(DUMMY, encoding="utf-8")
    loaded = load_plugins([str(f)])
    assert loaded == ["dummy_plugin_scorer"]
    assert default_registry.has("dummy_plugin_scorer")


def test_load_from_dotted_module(tmp_path, clean_registry, monkeypatch):
    pkg = tmp_path / "myplugins.py"
    pkg.write_text(DUMMY, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = load_plugins(["myplugins"])
    assert loaded == ["dummy_plugin_scorer"]
    assert default_registry.has("dummy_plugin_scorer")


def test_bad_spec_raises_plugin_load_error(clean_registry):
    with pytest.raises(PluginLoadError) as exc:
        load_plugins(["no_such_module_xyz"])
    assert "no_such_module_xyz" in str(exc.value)


def test_empty_specs_returns_empty(clean_registry):
    assert load_plugins([]) == []
