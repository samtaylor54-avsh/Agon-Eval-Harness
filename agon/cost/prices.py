"""Dated, advisory model price table -- USD per 1,000,000 tokens (Phase 3 M5).

These prices are a POINT-IN-TIME snapshot (see PRICES_AS_OF), NOT billing truth. They drift;
treat any reported cost as an estimate. Unknown models are simply not priced (cost omitted, never
an error). Override by passing your own ``prices`` mapping to the cost functions.
"""

from __future__ import annotations

PRICES_AS_OF = "2026-06-05"

# model key (provider prefix stripped, lowercased) -> (usd_per_mtok_input, usd_per_mtok_output).
# Representative/advisory values -- verify against current provider pricing before relying on them.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}

# Offline / mock providers cost nothing by construction (their tokens are synthetic).
FREE_PROVIDERS: frozenset[str] = frozenset({"mockllm"})


def normalize_model(model: str) -> str:
    """Strip a provider prefix and lowercase. 'Anthropic/Claude-Opus-4-5' -> 'claude-opus-4-5'."""
    key = model.split("/", 1)[1] if "/" in model else model
    return key.lower()


def price_for(
    model: str, prices: dict[str, tuple[float, float]] = DEFAULT_PRICES
) -> tuple[float, float] | None:
    """Return (input_rate, output_rate) per 1M tokens, or None if the model is not in the table.

    Offline/mock providers (FREE_PROVIDERS) price at zero so a default offline run reports a clean
    $0.00 rather than as an unpriced unknown model.
    """
    provider = model.split("/", 1)[0] if "/" in model else ""
    if provider in FREE_PROVIDERS:
        return (0.0, 0.0)
    return prices.get(normalize_model(model))
