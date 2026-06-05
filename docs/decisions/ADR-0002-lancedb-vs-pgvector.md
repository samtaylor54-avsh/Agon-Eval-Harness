# ADR-0002 — LanceDB default, pgvector optional; native IR metrics

- **Status:** Accepted
- **Date:** 2026-06-04
- **Deciders:** Samuel R. Taylor
- **Context:** Phase 2 M1 (isolated retrieval evals)

## Context

The harness needs a vector store for retrieval evals. The project's target stack
(`CLAUDE.md`) lists **pgvector**, but pgvector requires a running PostgreSQL server plus the
extension (Docker for clone-and-run), and lacks native BM25/hybrid search. The harness's hard
constraint is **offline-first, clone-and-run in under 20 minutes**.

## Decision

1. **LanceDB is the default vector store**, behind the `[retrieval]` extra. It runs **embedded**
   (no server, "like SQLite"), ships a Python-native API, and keeps the offline budget intact.
2. **pgvector stays an optional adapter** (future `[pgvector]` extra) for teams already running
   Postgres/AWS. The `Retriever` protocol (`index` / `retrieve(query, k) -> ranked ids`) keeps the
   IR scorer **store-agnostic**, so adding pgvector touches no scoring code.
3. **BM25 (`rank-bm25`) is the offline default retriever** — pure-Python, no embeddings, no model
   downloads — so the default retrieval eval runs with zero credentials and zero weights. Dense
   (LanceDB) and hybrid retrieval are opt-in; the LanceDB embedder is injectable (tests use a
   deterministic fake; real use lazily loads `sentence-transformers` via `[semantic]`).
4. **Hybrid = portable RRF fusion**, not a store's native hybrid API. `HybridRetriever` fuses any
   two retrievers (typically LanceDB dense + BM25 lexical) via Reciprocal Rank Fusion
   (`score(d) = Σ 1/(rrf_k + rank)`, `rrf_k=60`). This avoids coupling to LanceDB's
   version-specific hybrid query surface and keeps fusion store-agnostic.

## Deviation from the Phase 2 scope

The scope suggested wrapping **`ranx`** for the IR metric math. `ranx` pulls in **`numba`**
(heavy, occasionally finicky on Windows). The four metrics (recall@k, precision@k, MRR, nDCG@k,
hit@k) are ~40 lines of well-defined math, so we **implement them natively** (boundary-tested
against hand-computed values) — keeping retrieval scoring dependency-light and in the base
install. `ranx`/`pytrec_eval` remain available as an optional cross-check if ever needed.

**nDCG convention:** we use the **linear-gain numerator** (`rel_i / log2(i+1)`), not
`(2^rel_i − 1)`. Binary relevance (grade 1) is assumed unless graded `relevance_grades` are given.

## Consequences

- **Positive:** retrieval evals run fully offline (BM25); the IR scorer is store-agnostic; no
  server/infra for the default path; metric math has no heavy deps.
- **Negative:** dense/hybrid still need embeddings (model download via `[semantic]`), so the
  *dense* path isn't zero-download — but it's opt-in, not the default.
- **Known limitation:** BM25 here uses a simple alphanumeric tokenizer with **no stemming**, so
  morphological mismatches (e.g. "rotation" vs "rotated") can miss. This is expected lexical-search
  behavior; dense/hybrid retrieval mitigates it. Real corpora are also large enough that BM25 IDF
  is well-behaved (it degenerates only on tiny toy corpora).
