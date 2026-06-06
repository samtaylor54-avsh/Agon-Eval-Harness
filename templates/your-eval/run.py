"""Run your eval offline against your SUT adapter + your scorer.

    uv run python templates/your-eval/run.py

Uses the `callable` adapter (your my_sut). Swap in your real scorer by editing scorer.py;
this launcher imports it so its @register fires.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.task import run_eval

# Make this folder importable, then pull in your scorer (side-effect: registers my_scorer) and
# your SUT adapter. agon imports stay above to satisfy ruff isort; these locals sit after the
# sys.path mutation, hence the E402 noqa.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import scorer  # noqa: E402,F401  (registers my_scorer)
from sut_adapter import my_sut  # noqa: E402


def main() -> None:
    dataset = load_dataset(str(HERE / "dataset.yaml"))
    config = RunConfig(
        system_version="your_eval_v1",
        sut=SUTConfig(adapter="callable"),
        log_dir="logs",
        report_dir="reports",
    )
    log = run_eval(dataset, config, callable_fn=my_sut, display="none")
    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    passed = sum(r.passed for r in digest.records)
    recommendation = result["recommendation"].value
    print(f"{dataset.name}: {passed}/{len(digest.records)} passed -> {recommendation}")
    for path in result["written"].values():
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
