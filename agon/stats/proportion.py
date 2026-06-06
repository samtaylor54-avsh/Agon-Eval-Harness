"""Closed-form proportion statistics: Wilson score interval + two-proportion z-test."""

from __future__ import annotations

import math

from agon.schemas import Interval, ProportionTest
from agon.stats.normal import normal_cdf, z_critical

SMALL_SAMPLE_N = 30


def small_sample(n: int, min_n: int = SMALL_SAMPLE_N) -> bool:
    """True when n is below the rule-of-thumb threshold for the normal approximation."""
    return n < min_n


def _check_count(successes: int, n: int) -> None:
    """Guard a successes/total pair so callers get a clear error, not a math domain error."""
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be in [0, {n}], got {successes}")


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion (stable at small n and at 0%/100%)."""
    if n <= 0:
        return Interval(point=0.0, low=0.0, high=1.0, confidence=confidence)
    _check_count(successes, n)
    z = z_critical(confidence)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Interval(
        point=p,
        low=max(0.0, center - margin),
        high=min(1.0, center + margin),
        confidence=confidence,
    )


def two_proportion_test(
    s1: int, n1: int, s2: int, n2: int, confidence: float = 0.95
) -> ProportionTest:
    """Pooled two-proportion z-test. ``diff = p1 - p2`` (e.g. current - baseline)."""
    if n1 <= 0 or n2 <= 0:
        return ProportionTest(
            diff=0.0, z=0.0, p_value=1.0, significant=False, confidence=confidence
        )
    _check_count(s1, n1)
    _check_count(s2, n2)
    p1, p2 = s1 / n1, s2 / n2
    pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0.0:
        return ProportionTest(
            diff=p1 - p2, z=0.0, p_value=1.0, significant=False, confidence=confidence
        )
    z = (p1 - p2) / se
    p_value = 2.0 * (1.0 - normal_cdf(abs(z)))
    return ProportionTest(
        diff=p1 - p2,
        z=z,
        p_value=p_value,
        significant=p_value < (1.0 - confidence),
        confidence=confidence,
    )
