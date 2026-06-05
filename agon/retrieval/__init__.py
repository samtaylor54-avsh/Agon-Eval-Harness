"""Retrieval evals: measure retriever quality independently of generation (Phase 2 M1).

The retriever is scored on its own — ranked doc IDs vs gold relevant IDs (qrels) — with no
LLM in the loop. This keeps retrieval quality from being masked by (or blamed on) generation
(CLAUDE.md hard rule). BM25 is the offline default; LanceDB adds vector + hybrid search.
"""

from agon.retrieval.bm25 import BM25Retriever
from agon.retrieval.corpus import (
    load_corpus,
    load_retrieval_dataset,
    tokenize,
)
from agon.retrieval.hybrid import HybridRetriever, rrf_fuse
from agon.retrieval.interface import (
    Corpus,
    Document,
    RetrievalCase,
    RetrievalDataset,
    Retriever,
)
from agon.retrieval.lancedb_store import LanceDBRetriever
from agon.retrieval.report import generate_retrieval_reports, retrieval_digest
from agon.retrieval.scorer import ir_scorer, retriever_solver
from agon.retrieval.task import retrieval_task, run_retrieval_eval

__all__ = [
    "BM25Retriever",
    "Corpus",
    "Document",
    "HybridRetriever",
    "LanceDBRetriever",
    "RetrievalCase",
    "RetrievalDataset",
    "Retriever",
    "generate_retrieval_reports",
    "ir_scorer",
    "load_corpus",
    "load_retrieval_dataset",
    "retrieval_digest",
    "retrieval_task",
    "retriever_solver",
    "rrf_fuse",
    "run_retrieval_eval",
    "tokenize",
]
