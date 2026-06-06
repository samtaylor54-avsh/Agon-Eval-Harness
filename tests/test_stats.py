"""Phase 3 M6 — closed-form statistics (stats core, textbook values)."""

import pytest

from agon.schemas import Interval, ProportionTest
from agon.stats import normal_cdf, z_critical


def test_interval_and_proportiontest_construct():
    iv = Interval(point=0.8, low=0.49, high=0.94)
    assert iv.confidence == 0.95
    pt = ProportionTest(diff=0.1, z=1.98, p_value=0.048, significant=True)
    assert pt.significant is True
    assert pt.confidence == 0.95


def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_z_critical():
    assert z_critical(0.95) == pytest.approx(1.95996, abs=1e-4)
    assert z_critical(0.90) == pytest.approx(1.64485, abs=1e-4)
    with pytest.raises(ValueError):
        z_critical(0.5)


from agon.stats import small_sample, two_proportion_test, wilson_interval  # noqa: E402


def test_wilson_interval_textbook():
    iv = wilson_interval(8, 10)
    assert iv.point == pytest.approx(0.8)
    assert iv.low == pytest.approx(0.4902, abs=1e-3)
    assert iv.high == pytest.approx(0.9433, abs=1e-3)


def test_wilson_interval_boundaries():
    empty = wilson_interval(0, 0)
    assert empty.low == 0.0 and empty.high == 1.0 and empty.point == 0.0
    full = wilson_interval(10, 10)
    assert full.point == 1.0 and full.high == pytest.approx(1.0, abs=1e-9)
    zero = wilson_interval(0, 10)
    assert zero.point == 0.0 and zero.low == 0.0


def test_two_proportion_test_significant():
    pt = two_proportion_test(90, 100, 80, 100)
    assert pt.diff == pytest.approx(0.1)
    assert pt.z == pytest.approx(1.980, abs=1e-2)
    assert pt.p_value == pytest.approx(0.0477, abs=1e-3)
    assert pt.significant is True


def test_two_proportion_test_not_significant():
    pt = two_proportion_test(45, 50, 40, 50)
    assert pt.p_value == pytest.approx(0.1614, abs=1e-3)
    assert pt.significant is False


def test_two_proportion_test_degenerate():
    pt = two_proportion_test(0, 0, 5, 10)
    assert pt.p_value == 1.0 and pt.significant is False


def test_small_sample():
    assert small_sample(10) is True
    assert small_sample(30) is False
    assert small_sample(100) is False


def test_proportion_rejects_out_of_range_counts():
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
    with pytest.raises(ValueError):
        two_proportion_test(11, 10, 5, 10)


from agon.stats import kappa_interval  # noqa: E402


def test_kappa_interval_textbook():
    iv = kappa_interval(0.85, 0.5, 25)
    assert iv.point == pytest.approx(0.70, abs=1e-9)
    assert iv.low == pytest.approx(0.4201, abs=1e-3)
    assert iv.high == pytest.approx(0.9799, abs=1e-3)


def test_kappa_interval_degenerate():
    perfect = kappa_interval(1.0, 1.0, 10)  # pe >= 1 -> degenerate perfect agreement
    assert perfect.point == 1.0 and perfect.low == 1.0 and perfect.high == 1.0
    empty = kappa_interval(0.5, 0.5, 0)  # n = 0
    assert empty.low == empty.high == empty.point


def test_kappa_interval_clamps():
    # Wide SE on a high kappa pushes the raw upper bound past 1.0; assert the clamp fired.
    iv = kappa_interval(0.95, 0.5, 5)
    assert iv.high == pytest.approx(1.0)
