# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current State

**Phase 1 MVP is built** on Inspect AI. The shipped package is `agon/` (not the long-term
"Repository Structure (Target)" layout in the README, which is the Phase 2/3 plan). It depends on
the decision recorded in `docs/decisions/ADR-0001-inspect-vs-custom.md`: we build on **Inspect AI**
and treat the PRD's hand-rolled SQLite/LiteLLM runner as superseded.

Commands (run via `uv`):

```bash
uv sync                                   # install deps (Python pinned to 3.12 via .python-version)
uv run pytest                             # full test suite (offline; uses mockllm)
uv run ruff check agon tests              # lint
uv run agon run examples/datasets/rag_smoke.yaml --display none   # offline smoke eval + reports
uv run python examples/quickstart.py      # offline mixed-result demo via a stub SUT
uv run python examples/agent_quickstart.py  # offline ReAct-agent eval (tool_use/planning/step_efficiency)
uv sync --extra retrieval && uv run agon retrieve examples/retrieval/corpus.yaml examples/retrieval/qrels.yaml  # isolated retrieval eval
uv run agon trace <run_id> --backend console   # export a run as OpenTelemetry spans (needs [otel] extra)
uv run python examples/adversarial_quickstart.py  # offline OWASP adversarial suite (4 attacks caught, 4 controls pass)
uv run agon run suite.yaml --model anthropic/claude-sonnet-4-5 --fail-on-error 0.1  # real-provider run (needs [providers] + a key); see docs/running-real-evals.md
```

Key layout: `agon/{schemas,dataset,sut,scoring,analysis,reporting,calibrate,review,retrieval,task,config,cli}`,
tests under `tests/`, fixtures/examples under `examples/`. The offline path uses Inspect's
`mockllm/model` provider — no API key or model downloads — which is what keeps the run inside the
<20-minute reproducibility budget. Judge-based and semantic scorers are opt-in (real provider /
`[semantic]` extra). When adding a scorer, register it on `agon.scoring.default_registry` and add
boundary tests; when fixing a failure mode, add the case that catches it to a dataset.

## What This Project Is

`Agon-Eval-Harness` is an evaluation harness for AI systems (models, prompts, retrieval/RAG, agents, end-to-end workflows). The guiding principle — "excellence emerges through opposition" — translates into concrete engineering commitments that should shape every contribution:

- **Failure is data, not noise.** Every discovered failure is meant to become a permanent test case + regression check. When you fix a failure mode, add the case that catches it; don't just patch and move on.
- **Evidence over claims.** Results must be backed by metrics, traces, and reproducible runs. Avoid anything that reports success by assertion rather than by measured output.
- **Reproducibility is a hard requirement.** The stated bar is that a reviewer can clone and run the harness in under 20 minutes. Keep setup and example runs within that budget.
- **Separate concerns the README treats as separate.** Notably, **retrieval evals must be isolated from generation evals** (recall@k / MRR measured independently from answer quality). Don't conflate them in a single score.
- **No single-number obsession.** The seven evaluation categories (Functional Correctness, Tool Use, Planning, State Management, Robustness, Reliability, Safety) are tracked distinctly.

## Intended Architecture (planned, per README)

The data flow the harness is being built around — keep new components aligned to one of these stages rather than inventing parallel structures:

```
Eval Suite (benchmark / adversarial / regression / production)
  → Agent Harness (model · prompt · tools · memory · state · planning)
  → Evaluation Layer (metrics · scorers · judges · human review)
  → Results (scores · traces · reports · regression tracking)
  → Continuous Improvement (failure discovery feeds new tests back into the Eval Suite)
```

Production traces are intended to continuously harvest new eval cases (`evals/production/`), so the suite grows over time. The adversarial suite (`evals/adversarial/`) is mapped to the **OWASP Top 10 for Agentic Applications** (prompt injection, goal hijacking, memory poisoning, tool misuse).

Planned top-level dirs: `docs/` (incl. `decisions/` for ADRs), `evals/`, `harness/`, `judges/` (rule_based / llm_judge / hybrid), `traces/` (OpenTelemetry GenAI schemas + examples), `reports/`, `experiments/`.

## Target Tech Stack

When adding code, default to this stack (chosen deliberately in the README) rather than introducing alternatives without discussion:

- **Eval framework:** Inspect AI (UK AISI)
- **Agent orchestration:** LangGraph / LangChain
- **Observability:** OpenTelemetry GenAI Semantic Conventions → LangSmith / Grafana + Tempo
- **Retrieval:** pgvector / LanceDB, hybrid search, reranking
- **Runtime:** FastAPI · Pydantic · asyncio
- **Quality + tooling:** pytest · **uv** (package/env manager) · **ruff** (lint/format)
- **Packaging + CI:** Docker · GitHub Actions
- **Cloud:** AWS (S3, IAM, ECR, App Runner, Secrets Manager, Bedrock)

LLM-as-judge graders must be **validated against held-out human labels** before being trusted (Phase 1 requirement) — a judge is itself an evaluated component, not a ground truth.
