"""Append-only review store (JSONL), keyed by run_id."""

from __future__ import annotations

from pathlib import Path

from agon.schemas import ReviewRecord


def _path(reviews_dir: str | Path, run_id: str) -> Path:
    out = Path(reviews_dir)
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{run_id}.reviews.jsonl"


def save_review(review: ReviewRecord, reviews_dir: str | Path = "reviews") -> Path:
    """Append a review record. Overrides never edit prior rows (immutable history)."""
    path = _path(reviews_dir, review.run_id)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(review.model_dump_json() + "\n")
    return path


def load_reviews(run_id: str, reviews_dir: str | Path = "reviews") -> list[ReviewRecord]:
    path = _path(reviews_dir, run_id)
    if not path.exists():
        return []
    return [
        ReviewRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
