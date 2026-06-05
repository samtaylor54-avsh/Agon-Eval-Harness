"""Inspect retriever solver + IR scorer (dict-valued, grouped metrics)."""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import Generate, Solver, TaskState, solver

from agon.retrieval.interface import Retriever
from agon.retrieval.metrics import (
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RETRIEVED_KEY = "retrieved_ids"


@solver
def retriever_solver(retriever: Retriever, k: int) -> Solver:
    """Run the (pre-indexed) retriever for each query; stash ranked IDs on the state."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        ranked = retriever.retrieve(state.input_text, k)
        if state.metadata is None:
            state.metadata = {}
        state.metadata[RETRIEVED_KEY] = ranked
        return state

    return solve


def _gold(target: Target) -> set[str]:
    raw = target.target
    if isinstance(raw, list):
        return set(raw)
    return set(iter(target))


@scorer(
    metrics={
        "recall": [mean(), stderr()],
        "precision": [mean()],
        "mrr": [mean(), stderr()],
        "ndcg": [mean()],
        "hit": [mean()],
    }
)
def ir_scorer(k: int = 10):
    """Score ranked retrieval against gold qrels. Reports each metric distinctly."""

    async def score(state: TaskState, target: Target) -> Score:
        ranked = list((state.metadata or {}).get(RETRIEVED_KEY, []))
        gold = _gold(target)
        grades = (state.metadata or {}).get("relevance_grades") or None
        value = {
            "recall": recall_at_k(ranked, gold, k),
            "precision": precision_at_k(ranked, gold, k),
            "mrr": reciprocal_rank(ranked, gold),
            "ndcg": ndcg_at_k(ranked, gold, k, grades),
            "hit": hit_at_k(ranked, gold, k),
        }
        return Score(
            value=value,
            answer=", ".join(ranked[:k]),
            explanation=f"recall@{k}={value['recall']:.2f} mrr={value['mrr']:.2f}",
            metadata={"k": k, "retrieved": ranked[:k], "gold": sorted(gold)},
        )

    return score
