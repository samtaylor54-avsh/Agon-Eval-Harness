"""Closed-form confidence interval for Cohen's kappa (normal approximation)."""

from __future__ import annotations

import math

from agon.schemas import Interval
from agon.stats.normal import z_critical


def kappa_interval(po: float, pe: float, n: int, confidence: float = 0.95) -> Interval:
    """Normal-approximation CI for Cohen's kappa.

    ``po`` = observed agreement, ``pe`` = chance agreement, ``n`` = number of items.
    ``kappa = (po - pe) / (1 - pe)``; ``SE = sqrt(po(1-po)) / ((1-pe) sqrt(n))``. The interval
    is clamped to ``[-1, 1]``. Degenerate inputs return a zero-width interval at a sentinel
    kappa: ``1.0`` when ``pe >= 1`` (perfect chance agreement), else ``0.0`` when ``n <= 0``
    (no sample to analyse) -- in neither case is a real CI meaningful.
    """
    if n <= 0 or pe >= 1.0:
        k = 1.0 if pe >= 1.0 else 0.0  # sentinel, not a computed kappa
        return Interval(point=k, low=k, high=k, confidence=confidence)
    kappa = (po - pe) / (1.0 - pe)
    z = z_critical(confidence)
    se = math.sqrt(po * (1.0 - po)) / ((1.0 - pe) * math.sqrt(n))
    return Interval(
        point=kappa,
        low=max(-1.0, kappa - z * se),
        high=min(1.0, kappa + z * se),
        confidence=confidence,
    )
