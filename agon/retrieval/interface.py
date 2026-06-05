"""Retrieval schemas + the store-agnostic Retriever protocol.

A ``Retriever`` indexes a ``Corpus`` once, then returns a ranked list of ``doc_id`` for a
query. Keeping this behind a protocol means the IR scorer never depends on which store
(BM25, LanceDB, pgvector) produced the ranking.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    corpus_version: str  # sha256, computed by the loader
    documents: list[Document] = Field(min_length=1)

    def doc_ids(self) -> list[str]:
        return [d.doc_id for d in self.documents]


class RetrievalCase(BaseModel):
    """One query with its gold relevance judgments (qrels)."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    query: str
    relevant_doc_ids: list[str] = Field(min_length=1)
    # Optional graded relevance (doc_id -> grade) for nDCG; binary qrels otherwise.
    relevance_grades: dict[str, int] = Field(default_factory=dict)


class RetrievalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    dataset_version: str
    cases: list[RetrievalCase] = Field(min_length=1)


@runtime_checkable
class Retriever(Protocol):
    name: str

    def index(self, corpus: Corpus) -> None:
        """Build the index over the corpus. Called once before retrieval."""
        ...

    def retrieve(self, query: str, k: int) -> list[str]:
        """Return up to ``k`` ranked ``doc_id`` for the query (best first)."""
        ...
