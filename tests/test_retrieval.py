"""M1 — retrieval metrics, BM25 retriever, and end-to-end IR eval."""

import math

import pytest

from agon.retrieval import (
    BM25Retriever,
    Corpus,
    Document,
    HybridRetriever,
    LanceDBRetriever,
    RetrievalCase,
    RetrievalDataset,
    run_retrieval_eval,
)
from agon.retrieval.corpus import tokenize
from agon.retrieval.hybrid import rrf_fuse
from agon.retrieval.metrics import (
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from agon.retrieval.report import generate_retrieval_reports


def _bow_embed(vocab: list[str]):
    """Deterministic bag-of-words embedding (normalized) — offline, no model download."""

    def embed(texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            toks = tokenize(text)
            vec = [float(toks.count(w)) for w in vocab]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            out.append([x / norm for x in vec])
        return out

    return embed

RANKED = ["d1", "d2", "d3", "d4"]
GOLD = {"d2", "d4"}


# ------------------------------- metric math ------------------------------- #
def test_recall_at_k():
    assert recall_at_k(RANKED, GOLD, 4) == 1.0
    assert recall_at_k(RANKED, GOLD, 2) == 0.5  # only d2 in top 2
    assert recall_at_k(RANKED, set(), 4) == 0.0


def test_precision_at_k():
    assert precision_at_k(RANKED, GOLD, 2) == 0.5  # d2 of {d1,d2}
    assert precision_at_k(RANKED, GOLD, 4) == 0.5  # 2 of 4


def test_hit_at_k():
    assert hit_at_k(RANKED, GOLD, 2) == 1.0
    assert hit_at_k(["d1", "d3"], GOLD, 2) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(RANKED, GOLD) == 0.5  # first relevant d2 at rank 2
    assert reciprocal_rank(["d2", "d1"], GOLD) == 1.0
    assert reciprocal_rank(["d1", "d3"], GOLD) == 0.0


def test_ndcg_perfect_and_imperfect():
    # Perfect ranking: relevant docs first.
    assert ndcg_at_k(["d2", "d4", "d1"], GOLD, 3) == pytest.approx(1.0)
    # Relevant at ranks 2 and 4 → DCG = 1/log2(3) + 1/log2(5); IDCG = 1/log2(2)+1/log2(3).
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert ndcg_at_k(RANKED, GOLD, 4) == pytest.approx(dcg / idcg)


def test_ndcg_with_grades():
    grades = {"d2": 3, "d4": 1}
    # Putting the higher-graded doc first should score 1.0.
    assert ndcg_at_k(["d2", "d4"], {"d2", "d4"}, 2, grades) == pytest.approx(1.0)
    assert ndcg_at_k(["d4", "d2"], {"d2", "d4"}, 2, grades) < 1.0


# ------------------------------- BM25 retriever ------------------------------- #
def _corpus() -> Corpus:
    docs = [
        Document(doc_id="d1", text="the cat sat on the mat"),
        Document(doc_id="d2", text="emergency leave requires supervisor approval"),
        Document(doc_id="d3", text="quarterly revenue grew while costs rose"),
        Document(doc_id="d4", text="supervisor approval is needed for emergency travel"),
    ]
    return Corpus(name="c", corpus_version="v", documents=docs)


def test_bm25_ranks_relevant_first():
    pytest.importorskip("rank_bm25")
    r = BM25Retriever()
    r.index(_corpus())
    # Distinctive terms (unique to one doc) rank that doc first. (Terms shared by half a
    # tiny corpus get BM25 IDF ~ 0 — expected; real corpora are large enough to avoid this.)
    assert r.retrieve("leave", k=4)[0] == "d2"
    assert r.retrieve("revenue", k=4)[0] == "d3"


def test_bm25_requires_index():
    with pytest.raises(RuntimeError):
        BM25Retriever().retrieve("q", 5)


# ------------------------------- RRF + LanceDB + hybrid ------------------------------- #
def test_rrf_fuse_rewards_agreement():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
    assert set(fused[:2]) == {"a", "b"}  # ranked high in both lists


def test_lancedb_vector_retrieval(tmp_path):
    pytest.importorskip("lancedb")
    corpus = _corpus()
    vocab = sorted({w for d in corpus.documents for w in tokenize(d.text)})
    r = LanceDBRetriever(embed_fn=_bow_embed(vocab), uri=str(tmp_path / "lance"))
    r.index(corpus)
    assert r.retrieve("revenue costs", 4)[0] == "d3"


def test_lancedb_requires_index():
    with pytest.raises(RuntimeError):
        LanceDBRetriever(embed_fn=_bow_embed(["x"])).retrieve("q", 5)


def test_hybrid_fuses_dense_and_lexical(tmp_path):
    pytest.importorskip("lancedb")
    pytest.importorskip("rank_bm25")
    corpus = _corpus()
    vocab = sorted({w for d in corpus.documents for w in tokenize(d.text)})
    dense = LanceDBRetriever(embed_fn=_bow_embed(vocab), uri=str(tmp_path / "lance"))
    hybrid = HybridRetriever(dense, BM25Retriever(), pool=4)
    hybrid.index(corpus)
    assert "d3" in hybrid.retrieve("revenue costs", 4)[:2]


# ------------------------------- end-to-end eval ------------------------------- #
def test_retrieval_eval_end_to_end(tmp_path):
    pytest.importorskip("rank_bm25")
    corpus = _corpus()
    dataset = RetrievalDataset(
        name="qrels",
        dataset_version="v",
        cases=[
            RetrievalCase(
                query_id="q1",
                query="emergency leave supervisor approval",
                relevant_doc_ids=["d2", "d4"],
            ),
            RetrievalCase(
                query_id="q2",
                query="quarterly revenue costs",
                relevant_doc_ids=["d3"],
            ),
        ],
    )
    log = run_retrieval_eval(corpus, dataset, k=4, log_dir=str(tmp_path))
    assert log.status == "success"
    # Dict-valued score with grouped metrics → one aggregate per metric key.
    metric_names = {s.name for s in log.results.scores}
    assert {"recall", "precision", "mrr", "ndcg", "hit"} <= metric_names
    by_id = {s.id: s for s in log.samples}
    # q2's single relevant doc d3 should be retrieved → recall 1.0.
    assert by_id["q2"].scores["ir_scorer"].value["recall"] == 1.0


def test_retrieval_reports_redact_secret_in_query_id(tmp_path):
    """generate_retrieval_reports must mask key-prefixed tokens in both artifact surfaces."""
    pytest.importorskip("rank_bm25")
    corpus = _corpus()
    # Use a key-prefixed token as the query_id; it will appear verbatim in the digest/report.
    secret_token = "sk-ant-ABCDEFGHIJKLMNOP1234"
    dataset = RetrievalDataset(
        name="qrels-secret",
        dataset_version="v",
        cases=[
            RetrievalCase(
                query_id=secret_token,
                query="emergency leave supervisor approval",
                relevant_doc_ids=["d2", "d4"],
            ),
        ],
    )
    log = run_retrieval_eval(corpus, dataset, k=4, log_dir=str(tmp_path))
    result = generate_retrieval_reports(log)
    md = result["artifacts"]["retrieval.md"]
    js = result["artifacts"]["retrieval.json"]
    assert secret_token not in md, "raw token must be masked in retrieval.md"
    assert secret_token not in js, "raw token must be masked in retrieval.json"
    assert "sk-ant-...1234" in md, "masked form must appear in retrieval.md"
    assert "sk-ant-...1234" in js, "masked form must appear in retrieval.json"
