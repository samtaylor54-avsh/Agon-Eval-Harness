"""DatasetLoader — PRD §22.3 / Task 2, adapted for Inspect.

Loads ``.yaml`` / ``.yml`` / ``.json`` / ``.jsonl`` files, validates every record against
``AgonCase`` (aggregating *all* errors, not just the first), computes a deterministic
``dataset_version`` = sha256 of the canonicalized cases, and maps each case to an Inspect
``Sample`` carrying the full case in ``metadata`` so scorers can read expectations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from inspect_ai.dataset import MemoryDataset, Sample
from pydantic import ValidationError

from agon.schemas import AgonCase, AgonDataset

# Key under Sample.metadata that holds the full serialized AgonCase.
METADATA_CASE_KEY = "agon_case"


class DatasetValidationError(Exception):
    """Raised when one or more records fail validation. Aggregates every failure."""

    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        joined = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"{len(errors)} invalid case(s) in {path}:\n{joined}")


def _read_records(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Return (dataset_name, raw_records) from a file, format-agnostic."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        return path.stem, records

    if suffix == ".json":
        data = json.loads(text)
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"Unsupported dataset format: {suffix} ({path})")

    # Accept either a bare list of cases, or a mapping {name, test_cases: [...]}.
    if isinstance(data, list):
        return path.stem, data
    if isinstance(data, dict):
        name = data.get("name", path.stem)
        records = data.get("test_cases") or data.get("cases") or []
        if not isinstance(records, list):
            raise ValueError(f"'test_cases' must be a list in {path}")
        return name, records
    raise ValueError(f"Unrecognized dataset structure in {path}")


def _canonical_version(cases: list[AgonCase]) -> str:
    """sha256 over cases sorted by test_id, dumped canonically (order-independent)."""
    ordered = sorted(cases, key=lambda c: c.test_id)
    payload = [c.model_dump(mode="json") for c in ordered]
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dataset(path: str | Path) -> AgonDataset:
    """Load and validate a dataset file into an ``AgonDataset``.

    Raises ``DatasetValidationError`` aggregating every invalid case, or ``FileNotFoundError``
    / ``ValueError`` for missing or structurally-malformed files.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    name, records = _read_records(path)
    cases: list[AgonCase] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record #{idx}: expected a mapping, got {type(record).__name__}")
            continue
        try:
            case = AgonCase.model_validate(record)
        except ValidationError as exc:
            rid = record.get("test_id", f"#{idx}")
            errors.append(f"case '{rid}': {_summarize(exc)}")
            continue
        if case.test_id in seen_ids:
            errors.append(f"case '{case.test_id}': duplicate test_id")
            continue
        seen_ids.add(case.test_id)
        cases.append(case)

    if errors:
        raise DatasetValidationError(str(path), errors)

    return AgonDataset(name=name, dataset_version=_canonical_version(cases), test_cases=cases)


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def case_to_sample(case: AgonCase) -> Sample:
    """Map an ``AgonCase`` to an Inspect ``Sample``.

    The full case is preserved under ``metadata[METADATA_CASE_KEY]`` so scorers can
    reconstruct expectations; convenience keys are mirrored for filtering in ``inspect view``.
    """
    metadata: dict[str, Any] = {
        METADATA_CASE_KEY: case.model_dump(mode="json"),
        "category": case.category,
        "risk_level": case.risk_level.value,
        "difficulty_level": case.difficulty_level.value,
        "documents": list(case.input.documents),
        "tags": list(case.tags),
    }
    return Sample(
        input=case.input.user_message,
        target=case.expected.expected_answer or "",
        id=case.test_id,
        metadata=metadata,
    )


def to_samples(dataset: AgonDataset) -> list[Sample]:
    return [case_to_sample(c) for c in dataset.test_cases]


def to_memory_dataset(dataset: AgonDataset) -> MemoryDataset:
    return MemoryDataset(samples=to_samples(dataset), name=dataset.name)
