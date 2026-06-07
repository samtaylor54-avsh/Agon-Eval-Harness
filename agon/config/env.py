"""Load a .env at CLI entry so preflight/doctor see those keys (Inspect only loads it at eval time).

Process env always wins (``override=False``); a real shell-exported key is never clobbered by a
stale .env.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv


def load_env() -> str | None:
    """Load a .env from the cwd, walking up the tree. Return its path, or None if none found."""
    path = find_dotenv(usecwd=True)
    if not path:
        return None
    load_dotenv(path, override=False)
    return path
