"""Offline quickstart — run the smoke suite against an in-process stub SUT.

No API key, no model downloads. Demonstrates a realistic mixed report (PASS/FAIL/INVESTIGATE)
using the `callable` adapter, which the CLI can't wire (it needs a Python function).

    uv run python examples/quickstart.py
"""

from __future__ import annotations

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse
from agon.task import run_eval

# Stub answers keyed by test_id. ~17/20 are answered well → ~85% → INVESTIGATE.
RESPONSES: dict[str, SUTResponse] = {
    "rag_001": SUTResponse(
        final_answer="Emergency leave requires supervisor approval.",
        citations=["hr_policy_2026.pdf#4.2"],
    ),
    "rag_002": SUTResponse(
        final_answer="Remote work requires manager approval.",
        citations=["hr_policy_2026.pdf#6.1"],
    ),
    "rag_003": SUTResponse(
        final_answer="The daily meal limit is $75.", citations=["travel_policy.pdf#2"]
    ),
    "rag_004": SUTResponse(
        final_answer="Parental leave is 12 weeks.", citations=["hr_policy_2026.pdf#8"]
    ),
    "smoke_005": SUTResponse(final_answer="hello"),
    "smoke_006": SUTResponse(final_answer="Paris"),
    "format_007": SUTResponse(final_answer='{"risk": "high"}'),
    "format_008": SUTResponse(final_answer="revenue growth and rising costs"),
    "robust_009": SUTResponse(final_answer="There is no policy on lunar leave."),
    "robust_010": SUTResponse(final_answer="Which deadline do you mean?"),
    "rag_011": SUTResponse(
        final_answer="Enrollment opens in November.", citations=["benefits_2026.pdf#1"]
    ),
    "rag_012": SUTResponse(
        final_answer="PTO accrues 1.5 days per month.", citations=["hr_policy_2026.pdf#3"]
    ),
    "smoke_013": SUTResponse(final_answer="4"),
    "format_014": SUTResponse(final_answer="yes"),
    "rag_015": SUTResponse(
        final_answer="Report immediately to security.", citations=["security_policy.pdf#5"]
    ),
    "rag_018": SUTResponse(
        final_answer="Reimbursement takes 5 business days.", citations=["travel_policy.pdf#7"]
    ),
    "smoke_019": SUTResponse(final_answer="ACK"),
    # rag_016, format_017, rag_020 intentionally left to the fallback → they fail.
}


async def stub_sut(req: SUTRequest) -> SUTResponse:
    test_id = req.session_id.rsplit("_", 1)[0]
    return RESPONSES.get(test_id, SUTResponse(final_answer="I don't have that information."))


def main() -> None:
    dataset = load_dataset("examples/datasets/rag_smoke.yaml")
    config = RunConfig(
        system_version="quickstart_v1",
        sut=SUTConfig(adapter="callable"),
        log_dir="logs",
        report_dir="reports",
    )
    log = run_eval(dataset, config, callable_fn=stub_sut, display="none")
    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    print(
        f"{dataset.name}: pass {digest.overall_pass_rate * 100:.0f}% "
        f"-> {result['recommendation'].value}"
    )
    for path in result["written"].values():
        print(f"  wrote {path}")
    print("\nInspect the traces with:  uv run inspect view --log-dir logs")


if __name__ == "__main__":
    main()
