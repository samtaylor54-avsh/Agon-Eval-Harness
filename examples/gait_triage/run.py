"""Offline gait-sensor escalation-triage eval against a canned routing SUT.

No API key, no model downloads. Demonstrates the custom `gait_triage_route` scorer producing a
mixed report: correct routing at each tier, a CRITICAL under-escalation that forces a release FAIL
(binary-critical rule), an over-escalation, a correct defer, an over-deferral, a missed defer, and
an unparseable response.

    uv run python examples/gait_triage/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse
from agon.task import run_eval

# Make this folder importable, then register the custom scorer via its import side-effect.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import triage_scorer  # noqa: E402,F401  (registers gait_triage_route)

# Canned route per test_id, engineered to exercise every scorer outcome.
# gait_004 under-escalates a CRITICAL case -> unsafe_answer -> forces FAIL.
RESPONSES: dict[str, str] = {
    "gait_001": "routine",            # exact -> pass
    "gait_002": "notify_caregiver",   # exact -> pass
    "gait_003": "urgent_review",      # exact -> pass
    "gait_004": "routine",            # under-escalation on CRITICAL -> unsafe_answer (gates FAIL)
    "gait_005": "routine",            # under-escalation (high) -> unsafe_answer
    "gait_006": "urgent_review",      # over-escalation -> over_escalation
    "gait_007": "defer",              # exact defer -> pass
    "gait_008": "defer",              # over-deferral of a clear case -> over_deferral
    "gait_009": "notify_caregiver",   # missed defer -> missed_defer
    "gait_010": "uncertain",          # unparseable -> unparseable_route
}


async def stub_sut(req: SUTRequest) -> SUTResponse:
    test_id = req.session_id.rsplit("_", 1)[0]
    return SUTResponse(final_answer=RESPONSES.get(test_id, "uncertain"))


def main() -> None:
    dataset = load_dataset(str(HERE / "dataset.yaml"))
    config = RunConfig(
        system_version="gait_triage_v1",
        sut=SUTConfig(adapter="callable"),
        log_dir="logs",
        report_dir="reports",
    )
    log = run_eval(dataset, config, callable_fn=stub_sut, display="none")
    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    passed = sum(r.passed for r in digest.records)
    print(
        f"{dataset.name}: {passed}/{len(digest.records)} passed "
        f"-> {result['recommendation'].value}"
    )
    print(
        "  (the CRITICAL under-escalation gait_004 would force FAIL"
        " even if every other case passed)"
    )
    for path in result["written"].values():
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
