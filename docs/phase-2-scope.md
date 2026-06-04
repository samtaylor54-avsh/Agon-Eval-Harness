# Phase 2 Scope — Observability & Real Agentic Systems

**Status:** Scoped (not started) · **Date:** 2026-06-04 · **Builds on:** Phase 1 MVP (`agon/`)

## Context

Phase 1 delivered a CLI-first, offline evaluation harness on Inspect AI: typed YAML cases,
11 scorers, composite/flake scoring, regression detection, judge calibration, and reporting.
Phase 2 (per the README) adds the three things that turn it from a scorer into a real
agentic-systems eval platform: **isolated retrieval evals**, **agent evaluation**, and
**OpenTelemetry observability**.

**Decisions locked this session:**
1. **Sequence:** Retrieval → Agent → Observability (retrieval is offline, self-contained, and
   extends the RAG scorers we already have).
2. **Vector store:** LanceDB default (embedded, offline), pgvector as an optional adapter.
3. **Observability backend:** LangSmith via its native OTLP endpoint.
4. **Agent SUT:** bridge the *real* LangGraph `create_react_agent` via Inspect's `agent_bridge()`.

**Guardrails carried from Phase 1 (non-negotiable):** offline-first default (no key, no
downloads, <20-min clone-and-run); heavy deps behind extras; **retrieval scored independently
of generation**; failure → permanent test case; schema-first; judges validated before trust.
Each workstream ends with an independently reproducible milestone.

---

## Workstream 1 — Isolated Retrieval Evals  *(milestone M1, ~1 week)*

**Objective:** measure retriever quality on its own — `recall@k`, `MRR`, `nDCG@k`, `hit@k` —
against gold relevant doc IDs, with **no LLM in the loop**, so retrieval quality can never be
masked by (or blamed on) generation. Closes the README Phase-2 item "retrieval evals isolated
from generation evals (recall@k, MRR)."

**Design (grounded in Inspect's API):**
- **Retriever interface** `Retriever.retrieve(query, k) -> list[doc_id]` (ranked). Keeps the
  scorer store-agnostic. Adapters: `LanceDBRetriever` (default), `BM25Retriever` (pure-lexical,
  zero-model **offline default**), optional `PgVectorRetriever`.
- **Corpus fixture** built once, deterministically (fixed chunking; embeddings only when dense
  mode is on). Lives outside the `Sample`, shared across queries; content-addressed like datasets.
- **Inspect mapping:** `Sample.input` = query, `Sample.target` = gold doc IDs (Inspect `Target`
  accepts a list), `metadata` = graded relevances + `query_id`. A **retriever solver** (an
  arbitrary async solver, *not* a model call) writes ranked IDs to `state.metadata["retrieved_ids"]`.
- **IR scorer** `@scorer(metrics={"recall@k":[mean(),stderr()], "mrr":[mean()], ...})` returning
  a **dict-valued `Score`** so every metric shows up distinctly (honors "no single number").
  Wrap a maintained IR lib (`ranx`) for the math rather than hand-rolling.

**New code:** `agon/retrieval/{interface.py, lancedb_store.py, bm25.py, corpus.py}`,
`agon/scoring/ir.py`. **Extras:** `[retrieval]` = `lancedb`, `rank_bm25`, `ranx`; dense/rerank
reuse `[semantic]` + a new `[rerank]` (`sentence-transformers`, optional `FlagEmbedding`).

**Offline default = BM25 lexical** (no model download) so the default retrieval run stays inside
the <20-min budget; dense + hybrid + cross-encoder rerank are opt-in extras.

**Tasks (each ends green):**
- T2.1 Retriever interface + `BM25Retriever` + corpus builder + content hash. *DoD: build a tiny
  fixture corpus, retrieve ranked IDs offline, deterministic hash test.*
- T2.2 `LanceDBRetriever` (vector + native BM25 hybrid + RRF). *DoD: hybrid search returns ranked
  IDs; gated behind `[retrieval]`.*
- T2.3 IR `@scorer` (recall@k/MRR/nDCG/hit@k via `ranx`), dict value + grouped metrics. *DoD:
  boundary tests vs hand-computed values on a known qrel set.*
- T2.4 `agon retrieve` CLI subcommand + report section. *DoD: offline run over a fixture corpus
  emits a retrieval report with the four metrics, separate from generation reports.*
- T2.5 `examples/retrieval/` corpus + qrels (≥15 queries) + ADR-0002 (LanceDB vs pgvector).

**Verification:** `agon retrieve examples/retrieval/qrels.yaml` offline (BM25) prints recall@k/MRR;
LanceDB hybrid path tested behind the extra; pytest covers metric math at boundaries.

---

## Workstream 2 — Agent Evaluation (LangGraph)  *(milestone M2, ~1 week)*

**Objective:** evaluate a **real LangGraph ReAct agent** as the SUT — multi-turn tool use, tool
selection/arguments, error recovery, planning, and state across turns. Lights up the README
categories Tool Use, Planning, and State Management against an actual deployable agent.

**Design (grounded in Inspect's API):**
- **Bridge the real agent:** an Inspect `@agent` whose `execute` opens `agent_bridge(state)` from
  `inspect_ai.agent`, instantiates `langchain_openai.ChatOpenAI(model="inspect")` (the bridge
  proxies these calls to Inspect's current model — `mockllm` offline, real provider opt-in),
  runs `langgraph.prebuilt.create_react_agent(model, tools)`, and returns `bridge.state`. Tool
  calls and the final answer are captured automatically in `bridge.state.messages` / `.output`.
- **Normalize to our contract:** a `LangGraphAdapter` populates `SUTResponse.tool_calls` /
  `final_answer` from `state.messages` (`ChatMessageAssistant.tool_calls`, `ChatMessageTool`),
  so the existing `ToolUseScorer` (§25.11) and failure taxonomy work unchanged.
- **Inspect-native scorers over messages:** re-express tool-use/planning/recovery as `@scorer`s
  that read `state.messages` directly (tool selection, argument validity, `bad_recovery`,
  redundant-call detection). Add a lightweight **state-management** scorer (did the agent carry
  required context across turns) and a **planning** check (plan formed before acting).

**New code:** `agon/sut/langgraph.py` (bridge adapter), `agon/scoring/agent.py` (message-based
tool-use/planning/state/recovery scorers), example agent + tools under `examples/agent/`.
**Extras:** `[langgraph]` = `langgraph`, `langchain-openai`.

**Offline story:** the bridge routes the agent's model calls through `mockllm`, so agent-shaped
eval cases run in CI with no key (tool wiring + scorers exercised deterministically); real-provider
agent runs are opt-in.

**Tasks:**
- T2.6 `LangGraphAdapter` via `agent_bridge`; confirm `ChatMessageAssistant.tool_calls`
  attribute names against installed inspect-ai. *DoD: offline mockllm-bridged agent runs a 2-tool
  task; `SUTResponse.tool_calls` populated.*
- T2.7 Message-based `tool_use` / `planning` / `state_mgmt` / `recovery` `@scorer`s. *DoD:
  synthetic message histories score correctly at boundaries (tool_omission, tool_misuse,
  bad_recovery).*
- T2.8 Example ReAct agent + tools + ≥10 agent eval cases (incl. tool-misuse seeds that prefigure
  the Phase-3 OWASP suite). *DoD: `agon run` over the agent dataset offline produces per-category
  scores + traces in `inspect view`.*
- T2.9 ADR-0004 (bridge LangGraph vs native `react`); migration-watch note on
  `create_react_agent` → `langchain.agents.create_agent`.

**Verification:** offline bridged-agent run scores tool use / planning / state distinctly;
`inspect view` shows the multi-turn transcript with tool calls.

---

## Workstream 3 — Observability (OpenTelemetry → LangSmith)  *(milestone M3, ~1 week)*

**Objective:** emit OpenTelemetry **GenAI** spans for every LLM call, tool call, agent step, and
grader decision, exported to LangSmith (and, via the same OTLP, Grafana+Tempo). Makes eval runs
inspectable in a trace UI and links scores back to the exact calls that produced them.

**Design (grounded in research — Inspect emits no OTel, so we build the bridge):**
- **Hooks bridge:** register `inspect_ai.hooks` (`on_run_start`, `on_sample_start/end`,
  `on_before_model_generate`, `on_sample_event`, `on_sample_scoring`) and translate each into a
  `gen_ai.*` span via plain `opentelemetry-sdk`. Span/attr mapping: model call → `chat` span
  (`gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.{input,output}_tokens`); tool →
  `execute_tool {gen_ai.tool.name}`; agent → `invoke_agent`; grader/judge → a custom INTERNAL
  span tagged so **retrieval-vs-generation scores stay separable** in the trace.
- **Exporter:** OTLP → LangSmith `https://api.smith.langchain.com/otel` with
  `x-api-key=<LANGSMITH_API_KEY>` header; gate experimental attrs with
  `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`. Grafana+Tempo documented as a
  collector-target alternative (same OTLP, no LangSmith account).

**New code:** `agon/observability/{otel.py (tracer+exporter), hooks.py (Inspect hook bridge),
mapping.py (event→gen_ai.* span)}`. **Extras:** `[otel]` = `opentelemetry-sdk`,
`opentelemetry-exporter-otlp`, `opentelemetry-semantic-conventions-ai`.

**Opt-in, never on the offline path:** disabled by default; enabled via `RunConfig.observability`
+ env. CI's offline gate runs with it **off**. Tests use an **in-memory span exporter** so the
mapping is verified offline without any network or account.

**Tasks:**
- T2.10 OTel tracer/exporter setup + config flag + env wiring. *DoD: with an in-memory exporter,
  a run produces well-formed `gen_ai.*` spans.*
- T2.11 Inspect hooks → span mapping (model/tool/agent/grader). *DoD: a bridged-agent run yields
  nested chat/execute_tool/invoke_agent spans with correct attrs (asserted via in-memory exporter).*
- T2.12 LangSmith OTLP export (manual/integration, opt-in) + Grafana+Tempo `docker-compose` doc +
  ADR-0003. *DoD: documented end-to-end; spans visible in LangSmith with a real key.*

**Verification:** offline in-memory-exporter test asserts span tree + attributes; opt-in LangSmith
export confirmed manually; CI offline gate unaffected.

---

## Cross-cutting

**`pyproject.toml` extras after Phase 2:**

| Extra | Adds | Used by |
|---|---|---|
| `[retrieval]` | `lancedb`, `rank_bm25`, `ranx` | W1 retriever + IR scorer |
| `[rerank]` | `sentence-transformers`, `FlagEmbedding` (opt) | W1 dense/hybrid rerank |
| `[langgraph]` | `langgraph`, `langchain-openai` | W2 agent bridge |
| `[otel]` | `opentelemetry-sdk`, `-exporter-otlp`, `-semantic-conventions-ai` | W3 observability |
| `[pgvector]` | `psycopg`, `pgvector` | W1 optional Postgres adapter |

**New ADRs:** 0002 (LanceDB default), 0003 (custom OTel hooks bridge), 0004 (bridge LangGraph).

**Reproducibility:** retrieval (BM25) and agent (mockllm-bridged) milestones stay fully offline in
CI; observability and dense/real-provider paths are opt-in extras requiring keys/downloads.

## Out of scope (deferred to Phase 3)
OWASP Top-10-for-Agents adversarial suite (W2 only seeds tool-misuse cases), regulated-domain
harness, the methodology essay, an `inspect_evals` contribution, and pgvector-as-default.

## Open risks / watch items
- `create_react_agent` is being superseded by `langchain.agents.create_agent` — pin versions,
  budget a migration watch (ADR-0004).
- OTel GenAI semconv is still **experimental** (Development); gate behind the opt-in env var and
  expect `gen_ai.system` vs `gen_ai.provider.name` drift.
- Confirm Inspect `ChatMessageAssistant.tool_calls` attribute names (`.function`/`.arguments`) and
  the exact `agent_bridge` `ChatOpenAI` kwargs against installed `inspect-ai` before T2.6.
- Pin `ranx` / `rank_bm25` (and `bm25s` if used) versions; choose and document one nDCG numerator
  convention (`rel_i` vs `2^rel_i − 1`).
