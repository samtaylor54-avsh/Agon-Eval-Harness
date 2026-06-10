"""T6 — composite scoring, label derivation, flake reducers, orchestrating scorer."""

import pytest
from inspect_ai import Task, eval
from inspect_ai.scorer import Score

from agon.dataset import load_dataset, to_samples
from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
from agon.scoring import derive_labels, evaluate, flake_reducer
from agon.scoring.base import ScoreOutcome
from agon.scoring.inspect_scorer import agon_scorer
from agon.sut import SUTRequest, SUTResponse, callable_solver
from tests.test_dataset import FIXTURES


def _case(**kw) -> AgonCase:
    return AgonCase(
        test_id="t", name="n", category="c", input={"user_message": "q"},
        expected=kw.pop("expected", ExpectedBehavior()),
        failure_labels=kw.pop("failure_labels", []),
        scoring=[ScoringSpec(type="exact_match")],
    )


def _pair(scorer_type, normalized, *, weight=1.0, threshold=0.5, advisory=False, labels=None):
    spec = ScoringSpec(
        type=scorer_type,
        weight=weight,
        pass_threshold=1.0 if scorer_type == "safety" else threshold,
        advisory=advisory,
    )
    out = ScoreOutcome(
        scorer_type=scorer_type, native_score=normalized,
        normalized_score=normalized, labels=labels or [],
    )
    return spec, out


# ------------------------------- composite math ------------------------------- #
def test_weighted_composite():
    res = evaluate(_case(), [_pair("exact_match", 1.0), _pair("rubric", 0.5, weight=1.5)])
    # (1*1.0 + 1.5*0.5) / (1 + 1.5) = 1.75 / 2.5 = 0.7
    assert res.composite_score == pytest.approx(0.7)


def test_and_logic_one_fail_fails_case():
    res = evaluate(_case(), [_pair("exact_match", 1.0), _pair("rubric", 0.4, threshold=0.5)])
    assert res.passed is False


def test_retrieval_excluded_from_composite_but_still_gates():
    res = evaluate(
        _case(),
        [_pair("exact_match", 1.0), _pair("faithfulness", 0.5, threshold=0.5)],
    )
    # composite ignores faithfulness (retrieval), so it's just exact_match = 1.0
    assert res.composite_score == pytest.approx(1.0)
    assert res.retrieval_scores == {"faithfulness": 0.5}
    # faithfulness 0.5 >= 0.5 threshold, exact passes → case passes
    assert res.passed is True


def test_retrieval_below_threshold_fails_case():
    res = evaluate(
        _case(),
        [_pair("exact_match", 1.0), _pair("faithfulness", 0.3, threshold=0.5)],
    )
    assert res.passed is False
    assert res.composite_score == pytest.approx(1.0)  # composite still ignores retrieval


def test_advisory_scorer_excluded_from_gating():
    res = evaluate(
        _case(),
        [_pair("exact_match", 1.0), _pair("rouge_l", 0.0, advisory=True)],
    )
    assert res.passed is True
    assert res.composite_score == pytest.approx(1.0)


# ------------------------------- label derivation ------------------------------- #
def test_labels_intersect_allow_list():
    case = _case(failure_labels=["missing_citation"])
    pairs = [_pair("citation_check", 0.0, labels=["missing_citation", "wrong_citation"])]
    assert derive_labels(case, pairs) == ["missing_citation"]


def test_safety_labels_always_retained():
    case = _case(failure_labels=["missing_citation"])
    pairs = [_pair("safety", 0.0, threshold=1.0, labels=["unsafe_answer"])]
    assert "unsafe_answer" in derive_labels(case, pairs)


def test_no_allow_list_keeps_all_labels():
    case = _case(failure_labels=[])
    pairs = [_pair("citation_check", 0.0, labels=["missing_citation", "wrong_citation"])]
    assert set(derive_labels(case, pairs)) == {"missing_citation", "wrong_citation"}


# ------------------------------- flake reducers ------------------------------- #
def test_flake_reducer_all_requires_every_epoch():
    reducer = flake_reducer("all", 2)
    assert reducer([Score(value=1.0), Score(value=0.0)]).value == 0
    assert reducer([Score(value=1.0), Score(value=1.0)]).value == 1


def test_flake_reducer_any_needs_one():
    reducer = flake_reducer("any", 3)
    assert reducer([Score(value=0.0), Score(value=0.0), Score(value=1.0)]).value == 1.0


def test_flake_reducer_majority():
    reducer = flake_reducer("majority", 3)
    assert reducer([Score(value=1.0), Score(value=1.0), Score(value=0.0)]).value == 1
    assert reducer([Score(value=1.0), Score(value=0.0), Score(value=0.0)]).value == 0


# ------------------------------- scorer-error containment ------------------------------- #
def test_agon_scorer_contains_scorer_errors(tmp_path):
    """A scorer that raises ValueError fails its case (errored + scorer_error label)
    instead of aborting the run."""
    from agon.schemas import AgonDataset
    from agon.scoring.base import ScorerRegistry

    class BoomScorer:
        scorer_type = "boom"
        requires_judge = False

        async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
            raise ValueError("misconfigured on purpose")

    registry = ScorerRegistry()
    registry.register(BoomScorer())

    case = AgonCase(
        test_id="boom_001", name="n", category="c", input={"user_message": "q"},
        scoring=[ScoringSpec(type="boom")],
    )
    dataset = AgonDataset(name="boom", dataset_version="test", test_cases=[case])

    async def sut(req: SUTRequest) -> SUTResponse:
        return SUTResponse(final_answer="fine")

    task = Task(
        dataset=to_samples(dataset),
        solver=callable_solver(sut),
        scorer=agon_scorer(registry=registry),
    )
    log = eval(task, model="mockllm/model", log_dir=str(tmp_path), display="none")[0]
    assert log.status == "success"  # the run survives
    score = log.samples[0].score
    assert score.value == 0.0
    assert score.metadata["errored"] is True
    scores = {s["scorer_type"]: s for s in score.metadata["scores"]}
    assert "scorer error: misconfigured on purpose" in scores["boom"]["rationale"]
    assert "scorer_error" in scores["boom"]["labels"]


def test_agon_scorer_contains_type_errors_too(tmp_path):
    """Adversarial-review pin: a judge returning {"score": null} used to raise TypeError,
    which escaped the (ValueError, KeyError) containment and killed the entire run."""
    from agon.schemas import AgonDataset
    from agon.scoring.base import ScorerRegistry

    class NullScorer:
        scorer_type = "nullboom"
        requires_judge = False

        async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
            return int(None)  # TypeError, the exact shape of int(result["score"]) on null

    registry = ScorerRegistry()
    registry.register(NullScorer())
    case = AgonCase(
        test_id="null_001", name="n", category="c", input={"user_message": "q"},
        scoring=[ScoringSpec(type="nullboom")],
    )
    dataset = AgonDataset(name="nullboom", dataset_version="test", test_cases=[case])

    async def sut(req: SUTRequest) -> SUTResponse:
        return SUTResponse(final_answer="fine")

    task = Task(
        dataset=to_samples(dataset),
        solver=callable_solver(sut),
        scorer=agon_scorer(registry=registry),
    )
    log = eval(task, model="mockllm/model", log_dir=str(tmp_path), display="none")[0]
    assert log.status == "success"  # previously "error": run dead, zero samples scored
    assert log.samples[0].score.metadata["errored"] is True


# ------------------------------- end-to-end orchestration ------------------------------- #
def test_agon_scorer_end_to_end(tmp_path):
    dataset = load_dataset(FIXTURES / "mini.yaml")

    async def sut(req: SUTRequest) -> SUTResponse:
        if "emergency leave" in req.user_message:
            return SUTResponse(
                final_answer="Emergency leave requires supervisor approval.",
                citations=["hr_policy_2026.pdf#4.2"],
            )
        return SUTResponse(final_answer="hello")

    task = Task(
        dataset=to_samples(dataset),
        solver=callable_solver(sut),
        scorer=agon_scorer(),
    )
    logs = eval(task, model="mockllm/model", log_dir=str(tmp_path), display="none")
    log = logs[0]
    assert log.status == "success"
    by_id = {s.id: s for s in log.samples}
    assert by_id["rag_001"].score.value == 1.0
    assert by_id["smoke_002"].score.value == 1.0
    assert by_id["rag_001"].score.metadata["detected_failure_labels"] == []
