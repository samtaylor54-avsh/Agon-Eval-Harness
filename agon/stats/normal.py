"""Normal-distribution helpers (stdlib only) for agon's closed-form statistics."""

from __future__ import annotations

import math

# Two-sided z critical values for common confidence levels.
_Z_CRITICAL = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def normal_cdf(z: float) -> float:
    """Standard-normal CDF via the error function (no scipy)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def z_critical(confidence: float = 0.95) -> float:
    """Two-sided z critical value for a confidence level (0.90 / 0.95 / 0.99 supported)."""
    try:
        return _Z_CRITICAL[confidence]
    except KeyError as exc:
        raise ValueError(
            f"unsupported confidence {confidence}; use one of {sorted(_Z_CRITICAL)}"
        ) from exc
