"""BM25 lexical retriever — the offline default (pure-Python, no model downloads)."""

from __future__ import annotations

from agon.retrieval.corpus import tokenize
from agon.retrieval.interface import Corpus


class BM25Retriever:
    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_ids: list[str] = []
        self._bm25 = None

    def index(self, corpus: Corpus) -> None:
        from rank_bm25 import BM25Okapi

        self._doc_ids = corpus.doc_ids()
        tokenized = [tokenize(d.text) for d in corpus.documents]
        self._bm25 = BM25Okapi(tokenized, k1=self.k1, b=self.b)

    def retrieve(self, query: str, k: int) -> list[str]:
        if self._bm25 is None:
            raise RuntimeError("BM25Retriever.index() must be called before retrieve()")
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self._doc_ids, scores, strict=True), key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _score in ranked[:k]]
