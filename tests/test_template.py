"""M7 — the copy-me template must keep running offline (anti-rot guard)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "your-eval"


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, str(TEMPLATE_DIR / filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_template_runs_and_produces_a_digest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_mod = _load_module("tmpl_run_under_test", "run.py")

    from agon.schemas import RunConfig, SUTConfig
    from agon.task import run_eval

    dataset = run_mod.load_dataset(str(TEMPLATE_DIR / "dataset.yaml"))
    config = RunConfig(system_version="t", sut=SUTConfig(adapter="callable"))
    log = run_eval(dataset, config, callable_fn=run_mod.my_sut, display="none")
    assert log.status == "success"
