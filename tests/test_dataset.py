"""T2 — dataset loader tests."""

from pathlib import Path

import pytest

from agon.dataset import (
    METADATA_CASE_KEY,
    DatasetValidationError,
    case_to_sample,
    load_dataset,
    to_samples,
)
from agon.dataset.loader import _canonical_version
from agon.schemas import AgonCase

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_valid_dataset():
    ds = load_dataset(FIXTURES / "mini.yaml")
    assert ds.name == "mini_suite"
    assert len(ds.test_cases) == 2
    assert {c.test_id for c in ds.test_cases} == {"rag_001", "smoke_002"}
    assert len(ds.dataset_version) == 64  # sha256 hex


def test_dataset_version_is_deterministic_and_order_independent():
    ds = load_dataset(FIXTURES / "mini.yaml")
    # Reversing case order must not change the version (canonicalization sorts by test_id).
    reversed_cases = list(reversed(ds.test_cases))
    assert _canonical_version(reversed_cases) == ds.dataset_version


def test_dataset_version_changes_on_content_change():
    ds = load_dataset(FIXTURES / "mini.yaml")
    mutated = [c.model_copy(deep=True) for c in ds.test_cases]
    mutated[0].name = "different name"
    assert _canonical_version(mutated) != ds.dataset_version


def test_malformed_file_aggregates_all_errors():
    with pytest.raises(DatasetValidationError) as exc_info:
        load_dataset(FIXTURES / "bad.yaml")
    err = exc_info.value
    # Three problems: uppercase id, empty scoring, duplicate id.
    assert len(err.errors) == 3
    blob = "\n".join(err.errors)
    assert "GOOD_is_bad_case" in blob
    assert "missing_scoring" in blob
    assert "duplicate test_id" in blob


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_dataset(FIXTURES / "does_not_exist.yaml")


def test_case_to_sample_carries_full_case_in_metadata():
    ds = load_dataset(FIXTURES / "mini.yaml")
    rag = next(c for c in ds.test_cases if c.test_id == "rag_001")
    sample = case_to_sample(rag)
    assert sample.id == "rag_001"
    assert sample.input == "What does the policy say about emergency leave?"
    assert sample.metadata["risk_level"] == "high"
    # Round-trip the embedded case back into a model.
    restored = AgonCase.model_validate(sample.metadata[METADATA_CASE_KEY])
    assert restored.expected.citation_required is True
    assert restored.input.documents == ["hr_policy_2026.pdf"]


def test_to_samples_count_matches():
    ds = load_dataset(FIXTURES / "mini.yaml")
    assert len(to_samples(ds)) == len(ds.test_cases)
