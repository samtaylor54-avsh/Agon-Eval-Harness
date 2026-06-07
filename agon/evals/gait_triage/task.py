"""Registrable Inspect task for gait-sensor escalation triage.

The model reads a gait-signal summary and recommends one escalation tier. Scoring is
asymmetric-ordinal (see routing.py): under-escalation is `unsafe_answer`. A custom metric,
`critical_safety_gate`, fails the run if ANY critical-risk case is under-escalated -- even when
overall accuracy is high. This is an escalation RECOMMENDATION a human acts on, not a diagnosis.

Run offline:  inspect eval agon/evals/gait_triage/task.py --model mockllm/model
"""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai.dataset import MemoryDataset, Sample

_DATA = Path(__file__).parent / "dataset.json"


def gait_dataset() -> MemoryDataset:
    cases = json.loads(_DATA.read_text(encoding="utf-8"))
    return MemoryDataset(
        [
            Sample(
                input=c["input"],
                target=c["target"],
                id=c["test_id"],
                metadata={"risk_level": c["risk_level"]},
            )
            for c in cases
        ]
    )
