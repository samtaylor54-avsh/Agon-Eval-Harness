"""Load a ``RunConfig`` from a TOML, YAML, or JSON file."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from agon.schemas import RunConfig


def load_run_config(path: str | Path) -> RunConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Run config not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = tomllib.loads(text)
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported config format: {suffix} ({path})")
    return RunConfig.model_validate(data or {})
