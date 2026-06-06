"""Offline text-to-SQL eval against a canned NL->SQL SUT.

No API key, no model downloads. Demonstrates the custom `sql_result_match` scorer producing a
mixed report: one equivalent-but-different query passes (string match would fail), one query is
wrong, and one is malformed.

    uv run python examples/text_to_sql/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse
from agon.task import run_eval

# Make this folder importable whether run as a script or imported by a test, then register
# the custom scorer via its import side-effect. (Keep agon imports above to satisfy ruff isort;
# this lone local import sits after the sys.path mutation, hence the E402/F401 noqa.)
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sql_scorer  # noqa: E402,F401  (registers sql_result_match)

# Canned SQL per test_id. Note sql_001 is equivalent-but-different (passes on rows),
# sql_004 is wrong (wrong_rows), sql_006 is malformed (sql_error).
RESPONSES: dict[str, str] = {
    "sql_001": "SELECT name FROM employees WHERE dept IN ('engineering')",
    "sql_002": "SELECT COUNT(*) FROM employees",
    "sql_003": "SELECT AVG(salary) FROM employees",
    "sql_004": "SELECT name FROM employees WHERE salary > 50000",
    "sql_005": "SELECT name FROM employees ORDER BY salary DESC",
    "sql_006": "SELECT DISTINCT department FROM employees",
}


async def stub_sut(req: SUTRequest) -> SUTResponse:
    test_id = req.session_id.rsplit("_", 1)[0]
    return SUTResponse(final_answer=RESPONSES.get(test_id, "SELECT 1"))


def main() -> None:
    dataset = load_dataset(str(HERE / "dataset.yaml"))
    config = RunConfig(
        system_version="text_to_sql_v1",
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
    for path in result["written"].values():
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
