"""Phase 3 M6 -- calibration reports a confidence interval on Cohen's kappa."""

from agon.calibrate.runner import kappa_components
from agon.schemas import Interval
from agon.stats import kappa_interval


def test_kappa_components_basic():
    human = [True, True, True, False, False]
    judge = [True, True, False, False, False]
    po, pe = kappa_components(human, judge)
    assert po == 0.8  # 4 of 5 agree
    # p_h = 3/5, p_j = 2/5 -> pe = 0.6*0.4 + 0.4*0.6 = 0.48
    assert abs(pe - 0.48) < 1e-9


def test_kappa_interval_from_components():
    human = [True, True, True, False, False]
    judge = [True, True, False, False, False]
    po, pe = kappa_components(human, judge)
    iv = kappa_interval(po, pe, len(human))
    assert isinstance(iv, Interval)
    assert -1.0 <= iv.low <= iv.point <= iv.high <= 1.0
