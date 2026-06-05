"""Agent-trajectory scorers (Phase 2 M2) — complement the Phase 1 ``tool_use`` scorer.

These read the normalized tool-call trajectory (``SUTResponse.tool_calls``, produced by the
agent message normalizer), so they work for any agent SUT — native ReAct or bridged LangGraph.
``tool_use`` (§25.11) already covers selection / forbidden / args / recovery; these add the
agentic dimensions it doesn't: planning (gather before acting) and step efficiency.
"""

from __future__ import annotations

import json

from agon.scoring.base import ScoreOutcome, register


@register
class ToolUseScorer:
    """Tool-use quality (PRD §25.11): selection, forbidden tools, valid args, recovery.

    Composite of four equally-weighted sub-dimensions over the tool-call trajectory.
    """

    scorer_type = "tool_use"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        calls = response.tool_calls
        called = [c.tool_name for c in calls]
        called_set = set(called)
        expected = set(case.expected.expected_tool_calls)
        forbidden = set(case.expected.forbidden_tools)

        s_selection = len(called_set & expected) / max(1, len(expected))
        s_no_forbidden = 0.0 if (called_set & forbidden) else 1.0
        errored = [c for c in calls if c.error]
        s_valid_args = (len(calls) - len(errored)) / len(calls) if calls else 1.0

        if not errored:
            s_recovery = 1.0
        else:
            recovered = True
            for i, c in enumerate(calls):
                if c.error and not any(
                    t.tool_name == c.tool_name and not t.error for t in calls[i + 1 :]
                ):
                    recovered = False
                    break
            s_recovery = 1.0 if recovered else 0.0

        normalized = (s_selection + s_no_forbidden + s_valid_args + s_recovery) / 4
        labels: list[str] = []
        if expected and s_selection < 1.0:
            labels.append("tool_omission")
        if called_set & forbidden:
            labels.append("tool_misuse")
        if errored and s_recovery < 1.0:
            labels.append("bad_recovery")
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=normalized,
            normalized_score=normalized,
            labels=labels,
            details={
                "selection": s_selection,
                "no_forbidden": s_no_forbidden,
                "valid_args": s_valid_args,
                "recovery": s_recovery,
                "called": called,
            },
        )


@register
class PlanningScorer:
    """Did the agent gather information before answering? (Planning / State Management)

    When a case expects tool use, an agent that answers with zero tool calls acted without
    gathering — a planning failure. With no expected tools, this is a no-op pass.
    """

    scorer_type = "planning"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        expected = case.expected.expected_tool_calls
        if not expected:
            return ScoreOutcome(
                scorer_type=self.scorer_type, native_score=1.0, normalized_score=1.0
            )
        gathered = len(response.tool_calls) > 0
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=gathered,
            normalized_score=1.0 if gathered else 0.0,
            labels=[] if gathered else ["poor_reasoning_path"],
            details={"tool_calls": len(response.tool_calls)},
        )


@register
class StepEfficiencyScorer:
    """Penalize redundant tool calls (same tool + identical arguments invoked more than once)."""

    scorer_type = "step_efficiency"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        calls = response.tool_calls
        if not calls:
            return ScoreOutcome(
                scorer_type=self.scorer_type, native_score=1.0, normalized_score=1.0
            )
        signatures = [
            (c.tool_name, json.dumps(c.arguments, sort_keys=True, default=str)) for c in calls
        ]
        total = len(signatures)
        unique = len(set(signatures))
        duplicates = total - unique
        normalized = unique / total
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=normalized,
            normalized_score=normalized,
            labels=["redundant_tool_call"] if duplicates else [],
            details={"total_calls": total, "unique_calls": unique, "duplicates": duplicates},
        )
