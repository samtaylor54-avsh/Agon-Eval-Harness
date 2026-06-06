"""Phase 3 M6 — closed-form statistics (stats core, textbook values)."""

import pytest

from agon.schemas import Interval, ProportionTest
from agon.stats import normal_cdf, z_critical


def test_interval_and_proportiontest_construct():
    iv = Interval(point=0.8, low=0.49, high=0.94)
    assert iv.confidence == 0.95
    pt = ProportionTest(diff=0.1, z=1.98, p_value=0.048, significant=True)
    assert pt.significant is True and pt.confidence == 0.95


def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_z_critical():
    assert z_critical(0.95) == pytest.approx(1.95996, abs=1e-4)
    assert z_critical(0.90) == pytest.approx(1.64485, abs=1e-4)
    with pytest.raises(ValueError):
        z_critical(0.5)
