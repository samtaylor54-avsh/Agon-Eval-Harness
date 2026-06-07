"""Phase 3 M9 — .env loading at CLI entry; process env wins over .env."""

import os

from agon.config import load_env


def test_load_env_reads_dotenv_from_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("AGON_M9_PROBE", raising=False)
    (tmp_path / ".env").write_text("AGON_M9_PROBE=from_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    loaded = load_env()
    assert loaded is not None
    assert os.environ["AGON_M9_PROBE"] == "from_dotenv"


def test_load_env_does_not_override_process_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGON_M9_PROBE", "from_process")
    (tmp_path / ".env").write_text("AGON_M9_PROBE=from_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    load_env()
    assert os.environ["AGON_M9_PROBE"] == "from_process"


def test_load_env_no_dotenv_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # tmp_path has no .env and (being a temp dir) no ancestor .env.
    assert load_env() is None
