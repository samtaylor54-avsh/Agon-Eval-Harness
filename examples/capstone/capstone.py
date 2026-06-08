"""Capstone — the whole Agon loop in one runnable script, fully offline.

Build a small system under test, watch it FAIL, localize the failure, fix it, watch
it PASS, then plant a regression and catch it against the fixed baseline. No API key,
no model downloads.

    uv run python examples/capstone/capstone.py

The one step this can't do offline — calibrating an LLM judge against human labels —
is pointed to at the end; it needs a real provider (see Manual Ch 9 / `agon calibrate`).
"""

from __future__ import annotations

from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse
from agon.task import run_eval

HERE = Path(__file__).parent
DATASET = load_dataset(str(HERE / "dataset.yaml"))

# --- Three versions of the system under test ------------------------------------------ #
# v1 (buggy): the HIGH-risk emergency-leave answer is correct but OMITS its citation.
ANSWERS_V1: dict[str, SUTResponse] = {
    "cap_001": SUTResponse(final_answer="Emergency leave requires supervisor approval."),
    "cap_002": SUTResponse(
        final_answer="Remote work requires manager approval.",
        citations=["hr_policy_2026.pdf#6"],
    ),
    "cap_003": SUTResponse(
        final_answer="The daily meal limit is $75.",
        citations=["travel_policy.pdf#2"],
    ),
}
# v2 (fixed): the same system, now citing its source on cap_001 — a one-line change.
ANSWERS_V2: dict[str, SUTResponse] = {
    **ANSWERS_V1,
    "cap_001": SUTResponse(
        final_answer="Emergency leave requires supervisor approval.",
        citations=["hr_policy_2026.pdf#4.2"],
    ),
}
# v3 (a planted regression): a later change drops the "$75" figure from cap_003.
ANSWERS_V3: dict[str, SUTResponse] = {
    **ANSWERS_V2,
    "cap_003": SUTResponse(
        final_answer="The daily meal limit is set by policy.",
        citations=["travel_policy.pdf#2"],
    ),
}


def _sut(answers: dict[str, SUTResponse]):
    """Wrap a {test_id: response} table as a callable SUT (Ch 7)."""

    async def sut(req: SUTRequest) -> SUTResponse:
        test_id = req.session_id.rsplit("_", 1)[0]
        return answers.get(test_id, SUTResponse(final_answer="I don't have that information."))

    return sut


def run(version: str, answers: dict[str, SUTResponse], baseline_log=None):
    config = RunConfig(system_version=version, sut=SUTConfig(adapter="callable"))
    log = run_eval(DATASET, config, callable_fn=_sut(answers), display="none")
    result = generate_reports(log, config=config, baseline_log=baseline_log, out_dir="reports")
    return log, result


def headline(result) -> str:
    d = result["digest"]
    passed = sum(r.passed for r in d.records)
    return (
        f"{passed}/{len(d.records)} passed ({d.overall_pass_rate * 100:.0f}%) "
        f"-> {result['recommendation'].value}"
    )


def localize(result) -> None:
    for r in result["digest"].records:
        if not r.passed:
            labels = ", ".join(r.detected_failure_labels) or "(none)"
            print(f"    - {r.test_id}  [{r.category}, risk={r.risk_level}]  labels: {labels}")


def main() -> None:
    print("=" * 72)
    print("ACT 1 - Build a small eval and run it. The system has a planted bug.")
    print("=" * 72)
    _log_v1, res_v1 = run("capstone_v1_buggy", ANSWERS_V1)
    print(f"  capstone_v1_buggy:  {headline(res_v1)}")
    print("  In CI this exits 1 - it does not ship.\n")

    print("ACT 2 - Localize. Where, exactly, did it fail?")
    localize(res_v1)
    print("  The HIGH-risk case failed with `missing_citation`: the answer was right")
    print("  but cited nothing. The label is the cause, before reading a single trace.\n")

    print("ACT 3 - Fix the system (add the citation) and re-run.")
    log_v2, res_v2 = run("capstone_v2_fixed", ANSWERS_V2)
    print(f"  capstone_v2_fixed:  {headline(res_v2)}")
    print("  Exit 0: a clean PASS. cap_001 is now a permanent regression guard.\n")

    print("ACT 4 - A later change regresses the suite. Catch it against the baseline.")
    log_v3, res_v3 = run("capstone_v3_regressed", ANSWERS_V3, baseline_log=log_v2)
    reg = res_v3["regression"]
    print(f"  capstone_v3_regressed:  {headline(res_v3)}")
    print(
        f"  regression vs baseline: detected={reg.regression_detected}  "
        f"new_failures={reg.new_failures or 'none'}"
    )
    print("  Exit 1: the gate caught a case that used to pass. The guard worked.\n")

    print("=" * 72)
    print("What needs a real provider (not run here - see Manual Ch 9 & 19):")
    print("  Calibrate an LLM judge before trusting it on open-ended cases:")
    print("    uv run agon calibrate <labeled>.yaml --judge-model openai/gpt-4o --min-kappa 0.6")
    print("  Export any run as a trace (offline console backend works now):")
    print(f"    uv run agon trace {log_v3.eval.run_id} --backend console")
    print("=" * 72)


if __name__ == "__main__":
    main()
