"""Closed-form statistics for agon (Phase 3 M6) — pure Python, no scipy."""

from agon.stats.kappa import kappa_interval
from agon.stats.normal import normal_cdf, z_critical
from agon.stats.proportion import (
    SMALL_SAMPLE_N,
    small_sample,
    two_proportion_test,
    wilson_interval,
)

__all__ = [
    "SMALL_SAMPLE_N",
    "kappa_interval",
    "normal_cdf",
    "small_sample",
    "two_proportion_test",
    "wilson_interval",
    "z_critical",
]
