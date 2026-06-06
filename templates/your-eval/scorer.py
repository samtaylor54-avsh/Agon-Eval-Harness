"""Your custom scorer. Register it here, then use it via:
    uv run agon run --plugin templates/your-eval/scorer.py templates/your-eval/dataset.yaml

A scorer maps (AgonCase, SUTResponse, ScoringSpec) -> ScoreOutcome with a normalized_score in
[0.0, 1.0]. Keep the comparison logic pure and unit-test it (see test_scorer.py).
"""

from __future__ import annotations

from agon.scoring.base import ScoreOutcome, register


@register
class MyScorer:
    scorer_type = "my_scorer"      # TODO: rename; must match `type:` in dataset.yaml
    requires_judge = False         # set True only if you need an LLM judge (real provider)

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        # TODO: replace this stub. Compare response.final_answer against
        # case.expected.* and/or spec.params.*, then normalize to [0.0, 1.0].
        expected = (case.expected.expected_answer or "").strip().lower()
        actual = response.final_answer.strip().lower()
        passed = bool(expected) and expected in actual
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[] if passed else ["my_failure_label"],  # TODO: your failure labels
        )
