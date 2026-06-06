"""Load external scorer modules so their ``@register`` side-effects populate the registry.

A plugin "spec" is either a dotted module name (importable, on ``sys.path`` / CWD) or a path
to a ``.py`` file. Importing it runs the module top-level, which is where ``@register`` fires.
Used by ``agon run --plugin`` so a user's own scorer is usable without forking agon core.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path

from agon.scoring.base import default_registry


class PluginLoadError(Exception):
    """A --plugin spec could not be imported."""

    def __init__(self, spec: str, original: Exception) -> None:
        self.spec = spec
        self.original = original
        super().__init__(f"could not load plugin {spec!r}: {original}")


def _looks_like_file(spec: str) -> bool:
    return spec.endswith(".py") or Path(spec).exists()


def _load_file(spec: str) -> None:
    path = Path(spec).resolve()
    if not path.exists():
        raise FileNotFoundError(f"no such plugin file: {path}")
    mod_name = f"agon_plugin_{path.stem}"
    import_spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if import_spec is None or import_spec.loader is None:
        raise ImportError(f"cannot build import spec for {path}")
    module = importlib.util.module_from_spec(import_spec)
    sys.modules[mod_name] = module
    import_spec.loader.exec_module(module)


def _load_module(spec: str) -> None:
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    importlib.import_module(spec)


def load_plugins(specs: Iterable[str]) -> list[str]:
    """Import each spec; return the sorted scorer_types that newly appeared on the registry."""
    loaded: list[str] = []
    for spec in specs:
        before = set(default_registry.keys())
        try:
            if _looks_like_file(spec):
                _load_file(spec)
            else:
                _load_module(spec)
        except Exception as exc:
            raise PluginLoadError(spec, exc) from exc
        loaded.extend(sorted(set(default_registry.keys()) - before))
    return loaded
