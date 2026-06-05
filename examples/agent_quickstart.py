"""Offline agent-evaluation quickstart — a native ReAct agent over one tool.

No API key, no model downloads. A deterministic "policy" mockllm drives the agent: call the
knowledge_base tool, then submit its result. Demonstrates the agent scorers (tool_use,
planning, step_efficiency) end to end, including a deliberately-failing case (ag_calc_omission)
where the agent uses the wrong tool.

    uv run python examples/agent_quickstart.py
"""

from __future__ import annotations

from inspect_ai import eval
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.tool import tool

from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig
from agon.task import agent_task

# Canned knowledge base — keyword-routed answers. Order matters: more specific keys first
# (e.g. "parental" before "leave", since "parental leave" contains both).
_KB = {
    "weather": "It is sunny today.",
    "parental": "Parental leave is twelve weeks of paid time off.",
    "leave": "Emergency leave requires supervisor approval.",
    "expense": "The daily meal expense limit is $75.",
    "pto": "PTO accrues 1.5 days per month.",
    "password": "Passwords must be at least sixteen characters.",
    "retained": "Customer data is retained for seven years.",
    "badge": "Report immediately to the security desk.",
    "benefits": "Open benefits enrollment runs each November.",
}


@tool
def knowledge_base():
    async def execute(query: str):
        """Look up an answer in the HR/policy knowledge base.

        Args:
            query: the user's question
        """
        q = query.lower()
        for key, answer in _KB.items():
            if key in q:
                return answer
        return "No information found."

    return execute


def policy(messages, tools, tool_choice, config) -> ModelOutput:
    """Deterministic fake model: call knowledge_base, then submit its result."""
    tool_results = [m for m in messages if getattr(m, "role", None) == "tool"]
    if tool_results:
        return ModelOutput.for_tool_call(
            "mockllm", "submit", {"answer": tool_results[-1].text}
        )
    user = [m for m in messages if getattr(m, "role", None) == "user"]
    question = user[-1].text if user else ""
    return ModelOutput.for_tool_call("mockllm", "knowledge_base", {"query": question})


def main() -> None:
    dataset = load_dataset("examples/datasets/agent_smoke.yaml")
    config = RunConfig(system_version="agent_v1", log_dir="logs", report_dir="reports")
    task = agent_task(dataset, [knowledge_base()], config)
    model = get_model("mockllm/model", custom_outputs=policy)
    log = eval(task, model=model, log_dir=config.log_dir, display="none")[0]

    result = generate_reports(log, config=config, out_dir=config.report_dir)
    digest = result["digest"]
    print(
        f"{dataset.name}: pass {digest.overall_pass_rate * 100:.0f}% "
        f"-> {result['recommendation'].value}"
    )
    if digest.top_failure_labels:
        print("top failure modes:", dict(digest.top_failure_labels))
    for path in result["written"].values():
        print(f"  wrote {path}")
    print("\nInspect the agent trajectories with:  uv run inspect view --log-dir logs")


if __name__ == "__main__":
    main()
