"""Information-retrieval metrics, computed from ranked doc IDs vs gold qrels.

Implemented natively (no ranx/numba) to stay dependency-light and Windows-friendly.
All take a ranked list of doc IDs (best first) and the set of gold relevant doc IDs.
nDCG uses the linear-gain numerator (rel_i, not 2^rel_i - 1) — documented in ADR-0002.
"""

from __future__ import annotations

from math import log2


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = len(set(ranked[:k]) & relevant)
    return hits / len(relevant)


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = len(set(ranked[:k]) & relevant)
    return hits / k


def hit_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant doc (0.0 if none present)."""
    for i, doc_id in enumerate(ranked):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(
    ranked: list[str], relevant: set[str], k: int, grades: dict[str, int] | None = None
) -> float:
    """nDCG@k. Binary relevance (grade 1) unless graded ``grades`` are supplied."""
    grade = grades or {d: 1 for d in relevant}

    def dcg(order: list[str]) -> float:
        return sum(grade.get(d, 0) / log2(i + 2) for i, d in enumerate(order[:k]))

    actual = dcg(ranked)
    ideal_order = sorted(grade, key=lambda d: grade[d], reverse=True)
    ideal = dcg(ideal_order)
    return actual / ideal if ideal > 0 else 0.0
