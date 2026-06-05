"""LanceDB dense (vector) retriever — embedded, offline-capable, opt-in via [retrieval].

The embedding function is injectable: tests pass a deterministic fake; real use lazily loads
``sentence-transformers`` (the [semantic] extra). The vector store itself runs embedded (no
server), keeping with the offline-first design.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable

from agon.retrieval.interface import Corpus

EmbedFn = Callable[[list[str]], list[list[float]]]


class LanceDBRetriever:
    name = "lancedb"

    def __init__(
        self,
        embed_fn: EmbedFn | None = None,
        *,
        model: str = "all-MiniLM-L6-v2",
        uri: str | None = None,
    ) -> None:
        self._embed_fn = embed_fn
        self._model_name = model
        self._st_model = None
        self._uri = uri
        self._tbl = None

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - only without [semantic]
                raise ImportError(
                    "LanceDBRetriever needs an embed_fn, or the [semantic] extra "
                    "for the default sentence-transformers embedder"
                ) from exc
            self._st_model = SentenceTransformer(self._model_name)
        vectors = self._st_model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vectors]

    def index(self, corpus: Corpus) -> None:
        import lancedb

        uri = self._uri or tempfile.mkdtemp(prefix="agon_lancedb_")
        db = lancedb.connect(uri)
        vectors = self._embed([d.text for d in corpus.documents])
        data = [
            {"doc_id": d.doc_id, "text": d.text, "vector": v}
            for d, v in zip(corpus.documents, vectors, strict=True)
        ]
        self._tbl = db.create_table("corpus", data=data, mode="overwrite")

    def retrieve(self, query: str, k: int) -> list[str]:
        if self._tbl is None:
            raise RuntimeError("LanceDBRetriever.index() must be called before retrieve()")
        qvec = self._embed([query])[0]
        results = self._tbl.search(qvec).limit(k).to_list()
        return [r["doc_id"] for r in results]
