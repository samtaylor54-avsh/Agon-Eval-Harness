"""T1 — schema validation tests."""

import pytest
from pydantic import ValidationError

from agon.schemas import (
    AgonCase,
    CaseInput,
    RiskLevel,
    RunConfig,
    ScoringSpec,
)


def _minimal_case(**overrides) -> dict:
    base = {
        "test_id": "rag_001",
        "name": "grounded answer",
        "category": "RAG factuality",
        "input": {"user_message": "What does the policy say?", "documents": ["hr.pdf"]},
        "scoring": [{"type": "exact_match"}],
    }
    base.update(overrides)
    return base


def test_minimal_case_validates_with_defaults():
    case = AgonCase.model_validate(_minimal_case())
    assert case.test_id == "rag_001"
    assert case.risk_level is RiskLevel.MEDIUM
    assert case.input.user_message.startswith("What")
    assert case.expected.citation_required is False
    assert case.scoring[0].weight == 1.0


def test_extra_keys_are_rejected():
    with pytest.raises(ValidationError):
        AgonCase.model_validate(_minimal_case(unknown_field="boom"))


def test_extra_keys_rejected_on_input_block():
    with pytest.raises(ValidationError):
        AgonCase.model_validate(
            _minimal_case(input={"user_message": "hi", "typo_field": 1})
        )


def test_test_id_pattern_enforced():
    with pytest.raises(ValidationError):
        AgonCase.model_validate(_minimal_case(test_id="HasUppercase Spaces"))


def test_scoring_requires_at_least_one_spec():
    with pytest.raises(ValidationError):
        AgonCase.model_validate(_minimal_case(scoring=[]))


def test_safety_scorer_must_have_threshold_one():
    # Forcing a sub-1.0 threshold on a safety scorer is rejected.
    with pytest.raises(ValidationError):
        ScoringSpec(type="safety", pass_threshold=0.5)
    # A safety scorer with threshold 1.0 is fine.
    ok = ScoringSpec(type="safety", pass_threshold=1.0)
    assert ok.pass_threshold == 1.0


def test_advisory_defaults_false():
    spec = ScoringSpec(type="rubric")
    assert spec.advisory is False


def test_case_input_requires_user_message():
    with pytest.raises(ValidationError):
        CaseInput.model_validate({"documents": ["x.pdf"]})


def test_run_config_flake_rule_validation():
    with pytest.raises(ValidationError):
        RunConfig(flake_rule="sometimes")
    cfg = RunConfig(flake_rule="majority")
    assert cfg.flake_rule == "majority"


def test_run_config_threshold_ordering():
    with pytest.raises(ValidationError):
        RunConfig(pass_threshold=0.80, investigate_threshold=0.90)


def test_run_config_offline_defaults():
    cfg = RunConfig()
    assert cfg.sut.adapter == "mockllm"
    assert cfg.judge.model == "mockllm/model"
    assert cfg.epochs == 1
