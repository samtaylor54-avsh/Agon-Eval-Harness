"""Hybrid retrieval via Reciprocal Rank Fusion (RRF).

Fuses any two retrievers (typically dense + lexical) without depending on a store's native
hybrid API — keeping fusion portable and the retriever interface store-agnostic.
RRF: score(d) = Σ_r 1 / (rrf_k + rank_r(d)), ranks 1-indexed; rrf_k=60 is the common default.
"""

from __future__ import annotations

from agon.retrieval.interface import Corpus, Retriever


def rrf_fuse(rankings: list[list[str]], rrf_k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


class HybridRetriever:
    name = "hybrid"

    def __init__(
        self,
        dense: Retriever,
        lexical: Retriever,
        *,
        rrf_k: int = 60,
        pool: int = 50,
    ) -> None:
        self.dense = dense
        self.lexical = lexical
        self.rrf_k = rrf_k
        self.pool = pool  # candidates pulled from each retriever before fusion

    def index(self, corpus: Corpus) -> None:
        self.dense.index(corpus)
        self.lexical.index(corpus)

    def retrieve(self, query: str, k: int) -> list[str]:
        dense_ranking = self.dense.retrieve(query, self.pool)
        lexical_ranking = self.lexical.retrieve(query, self.pool)
        return rrf_fuse([dense_ranking, lexical_ranking], self.rrf_k)[:k]
