"""Judge calibration: validate LLM-judge scorers against held-out human labels.

A judge is an evaluated component, not a ground truth (CLAUDE.md / README Phase-1 requirement).
This module measures judge-vs-human agreement (accuracy + Cohen's kappa) and gates judge use
on a minimum agreement threshold.
"""

from agon.calibrate.runner import (
    CalibrationCase,
    CalibrationReport,
    CalibrationSet,
    cohen_kappa,
    load_calibration_set,
    run_calibration,
)

__all__ = [
    "CalibrationCase",
    "CalibrationReport",
    "CalibrationSet",
    "cohen_kappa",
    "load_calibration_set",
    "run_calibration",
]
