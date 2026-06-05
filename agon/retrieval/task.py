"""Assemble and run an isolated retrieval eval as an Inspect Task."""

from __future__ import annotations

from inspect_ai import Task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import EvalLog

from agon.retrieval.bm25 import BM25Retriever
from agon.retrieval.interface import Corpus, RetrievalDataset, Retriever
from agon.retrieval.scorer import ir_scorer, retriever_solver


def retrieval_to_samples(dataset: RetrievalDataset) -> list[Sample]:
    return [
        Sample(
            input=case.query,
            target=case.relevant_doc_ids,
            id=case.query_id,
            metadata={
                "query_id": case.query_id,
                "relevance_grades": case.relevance_grades,
            },
        )
        for case in dataset.cases
    ]


def retrieval_task(
    corpus: Corpus,
    dataset: RetrievalDataset,
    *,
    retriever: Retriever | None = None,
    k: int = 10,
) -> Task:
    """Build a retrieval eval Task. The retriever is indexed over the corpus once here."""
    retriever = retriever or BM25Retriever()
    retriever.index(corpus)
    return Task(
        dataset=MemoryDataset(samples=retrieval_to_samples(dataset), name=dataset.name),
        solver=retriever_solver(retriever, k),
        scorer=ir_scorer(k),
        name=dataset.name,
        metadata={
            "corpus_version": corpus.corpus_version,
            "dataset_version": dataset.dataset_version,
            "retriever": retriever.name,
            "k": k,
        },
    )


def run_retrieval_eval(
    corpus: Corpus,
    dataset: RetrievalDataset,
    *,
    retriever: Retriever | None = None,
    k: int = 10,
    log_dir: str = "logs",
    display: str = "none",
) -> EvalLog:
    """Run the retrieval eval offline (no model is actually called by the retriever solver)."""
    task = retrieval_task(corpus, dataset, retriever=retriever, k=k)
    logs = eval(task, model="mockllm/model", log_dir=log_dir, display=display)
    return logs[0]
