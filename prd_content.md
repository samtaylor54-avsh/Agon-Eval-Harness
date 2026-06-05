# Agon Eval Harness
## Product Requirements Document

**Document Type:** Hybrid PRD — Stakeholder-Facing + Implementation-Ready Technical Specification
**Target Consumers:** T&E Leads, Product Owners, Evals Engineers, AI Developers, LLM Coding Agents
**Primary Language:** Python 3.11+
**Status:** Implementation-Ready

---

# PART I: PRODUCT DEFINITION

---

## 1. Product Name

**Agon Eval Harness**
*A structured system for testing, scoring, comparing, and improving AI system behavior.*

---

## 2. Product Summary

The Evals Harness is a testing and measurement system for AI applications — especially LLM-powered agents, chatbots, RAG systems, tool-using workflows, and prompt-based applications.

Its purpose is to convert vague concerns like:

> "The model sometimes gives bad answers."

into specific, repeatable evaluation workflows like:

> "On this dataset of 200 test cases, the system must answer with at least 90% factual accuracy, cite the correct source in 95% of RAG cases, avoid unsafe recommendations 100% of the time, and complete tool-use tasks without regression compared to the previous version."

The harness allows developers, evaluators, product owners, and testers to run controlled evaluations against prompts, models, retrieval systems, agents, tools, memory, and workflows.

---

## 3. Problem Statement

AI systems are difficult to test using only traditional deterministic software testing methods.

Traditional software often behaves like this:

> Same input → same output.

AI systems often behave more like this:

> Same input → similar but not identical output.

That creates a measurement problem.

Without an eval harness, teams rely too heavily on manual spot-checking, vibes, demos, screenshots, and one-off testing. This leads to missed regressions, inconsistent quality, weak evidence, and poor confidence when changing prompts, models, tools, memory, or retrieval pipelines.

The Evals Harness exists to provide a repeatable, inspectable, evidence-based way to answer:

> "Did the AI system get better, worse, or just different?"

---

## 4. Target Users

### Primary Users

**Evals Engineer**
Designs tests, defines metrics, builds datasets, configures scorers, analyzes failures, and recommends improvements.

**AI Developer / Agent Developer**
Uses the harness to test prompt changes, model changes, tool changes, and agent behavior before deployment.

**Test & Evaluation Lead**
Uses harness outputs as evidence for quality, risk, reliability, and fielding recommendations.

### Secondary Users

**Product Owner**
Uses scorecards and summaries to understand whether the AI system is ready for users.

**Security / Safety Reviewer**
Uses focused evals to detect unsafe, policy-violating, or high-risk behavior.

**Domain Expert / SME**
Helps define correct answers, expected reasoning, rubric criteria, and realistic test cases.

---

## 5. Product Goals

The Evals Harness shall:

1. Provide repeatable testing for AI system behavior.
2. Support multiple eval types, including golden-answer, rubric-based, LLM-as-judge, tool-use, RAG, safety, and regression evals.
3. Capture evidence, traces, prompts, model versions, outputs, scores, and failure modes.
4. Help teams compare system versions over time.
5. Detect regressions before deployment.
6. Convert observed failures into reusable tests.
7. Support both automated scoring and human review.
8. Produce reports useful to developers, evaluators, and leadership.

---

## 6. Non-Goals

The Evals Harness is **not** intended to:

1. Replace all human evaluation.
2. Guarantee that the AI system is always correct.
3. Prove that the model "understands" in a human sense.
4. Fully eliminate stochastic variation.
5. Act as the production agent itself.
6. Replace system monitoring, observability, or incident response.
7. Decide business risk alone without human judgment.

This matters because an eval harness is not magic. It is a measurement machine. It improves confidence; it does not create certainty.

---

## 7. Core Concept

At its simplest, an eval harness has five major parts:

> Test Cases → System Under Test → Scorers → Results Store → Reports

Or in plain English:

> Give the AI a known challenge.
> Watch what it does.
> Score the result.
> Store the evidence.
> Use the results to improve the system.

---

## 8. What Comprises an Eval Harness?

### 8.1 Test Case Library

The test case library contains the inputs used to challenge the AI system.

Each test case may include:

- test_id
- name
- category
- user_input
- context_documents
- expected_answer
- expected_citations
- allowed_tools / forbidden_tools
- difficulty_level
- risk_level
- tags
- metadata

Example:

```json
{
  "test_id": "rag_policy_014",
  "category": "RAG factuality",
  "user_input": "What is the leave policy for emergency travel?",
  "context_documents": ["hr_policy_2026.pdf"],
  "expected_answer": "Emergency travel leave requires supervisor approval...",
  "expected_citations": ["hr_policy_2026.pdf#section-4.2"],
  "risk_level": "medium",
  "tags": ["RAG", "policy", "citation"]
}
```

This is the eval harness equivalent of a test procedure or test data sheet.

### 8.2 Dataset Manager

The dataset manager organizes test cases into meaningful groups.

Example datasets:

- smoke_tests
- regression_tests
- rag_factuality_tests
- tool_use_tests
- safety_tests
- long_context_tests
- adversarial_tests
- production_failure_replays

This allows the team to run different levels of evaluation.

Example:
- Before every commit: run smoke tests.
- Before every release: run full regression tests.
- After a production failure: add a replay test.
- Before model upgrade: run full comparison suite.

### 8.3 System Under Test Adapter

The harness needs a way to call the thing being tested.

The system under test could be: a prompt only, chatbot, RAG pipeline, agent, tool-using workflow, multi-agent system, API endpoint, local model, or hosted model.

The adapter standardizes how the harness sends inputs and receives outputs.

Example input:
```json
{
  "user_message": "Summarize this report and identify risks.",
  "documents": ["report.pdf"],
  "session_id": "eval_run_001"
}
```

Example output:
```json
{
  "final_answer": "The report identifies three major risks...",
  "citations": ["report.pdf#page-4"],
  "tool_calls": [],
  "trace_id": "abc123",
  "latency_ms": 3180,
  "token_usage": { "input": 4200, "output": 780 }
}
```

This adapter is important because the harness should not care whether the system is Claude, GPT, local Llama, a LangGraph agent, or a homegrown workflow.

### 8.4 Execution Engine

The execution engine runs the tests. It handles: which tests to run, how many times to run them, which model/prompt/configuration to use, whether to run in parallel, whether to retry failed calls, and how to log each run.

For AI systems, repeated runs can matter because outputs may vary.

Example:
> Run each critical test case 3 times.
> Pass only if all 3 attempts meet the safety threshold.
> This helps detect flaky behavior.

### 8.5 Scoring System

The scoring system determines whether the output was good, bad, or somewhere in between. This is the heart of the eval harness.

Scorers include: Exact Match, Semantic Similarity, Rubric, LLM-as-Judge, RAG Citation, Tool-Use, Safety, and Regression. See Section 16 for full implementation specifications.

### 8.6 Trace Capture

The harness should capture what happened during the run.

For simple systems, that includes: input, output, model, prompt version, score, latency, token count.

For agents, it should also include: planning steps, tool calls, tool inputs/outputs, memory reads, retrieval results, intermediate reasoning summaries, errors, retries, and final answer.

This is equivalent to having a flight recorder. Without trace capture, you may know the system failed, but not why.

### 8.7 Results Store

The results store keeps historical eval runs. It should preserve: run_id, timestamp, system_version, model_version, prompt_version, dataset_version, test_case_id, input, output, scores, judge rationale, trace_id, failure labels, and human review notes.

This allows trend analysis. Example questions the results store should answer:
- Are we improving over time?
- Which failure modes are most common?
- Did the new prompt reduce hallucinations?
- Did tool-use reliability improve?
- Did the new model increase cost?
- Did the system regress on safety?

### 8.8 Failure Taxonomy

The harness should categorize failures. This is critical.

A raw score tells you **how much pain** you have.
A failure taxonomy tells you **what kind of pain** you have.

Example failure categories:

| Category | Description |
|---|---|
| factual_error | Answer is factually incorrect |
| unsupported_claim | Claim not backed by retrieved context |
| wrong_citation | Citation present but incorrect |
| missing_citation | Required citation absent |
| tool_misuse | Wrong tool called or bad arguments |
| tool_omission | Required tool not called |
| bad_recovery | Failed to recover from tool error |
| unsafe_answer | Output violates safety/policy |
| over_refusal | Refused a benign request |
| under_refusal | Failed to refuse a policy-violating request |
| incomplete_answer | Answer missing key required details |
| format_failure | Output not in required format |
| instruction_following_failure | Ignored explicit instruction |
| latency_failure | Response exceeded latency budget |
| cost_failure | Response exceeded token/cost budget |
| memory_misuse | Incorrect use of memory/context |
| retrieval_miss | Retriever failed to return relevant document |
| poor_reasoning_path | Correct answer reached via flawed reasoning |

### 8.9 Reporting Layer

The reporting layer turns eval results into something humans can use.

Reports should include: overall pass rate, score by category, score by risk level, top failure modes, worst regressions, cost and latency trends, model/prompt comparison, recommended fixes, and evidence links.

Example summary:

```
Eval Run: 2026-06-04
Dataset: RAG Regression Suite v0.4
System Version: agent-rag-v1.7

Overall Pass Rate: 87%
Previous Pass Rate: 91%
Regression: Yes

Top Failure Modes:
  1. Missing citations: 14 failures
  2. Unsupported claims: 7 failures
  3. Incorrect tool use: 3 failures

Recommendation: Do not release v1.7 until citation behavior is corrected.
```

---

## 9. User Stories

### Evals Engineer

- As an Evals Engineer, I want to define reusable test cases so that known failure modes can be checked repeatedly.
- As an Evals Engineer, I want to run evals against different prompt and model versions so that I can measure whether changes improve or degrade behavior.
- As an Evals Engineer, I want failures categorized automatically or semi-automatically so that I can identify patterns instead of reviewing every failure from scratch.

### AI Developer

- As a developer, I want fast smoke evals before merging changes so that obvious regressions are caught early.
- As a developer, I want detailed traces for failed cases so that I can understand whether the issue came from the prompt, retrieval, tool use, memory, or model behavior.

### T&E Lead

- As a T&E Lead, I want summary reports with evidence so that I can support release recommendations.
- As a T&E Lead, I want risk-based scoring so that high-risk failures matter more than low-risk cosmetic issues.

### Product Owner

- As a Product Owner, I want to compare releases over time so that I can see whether quality is improving.

---

## 10. Functional Requirements

### 10.1 Test Case Management
The system shall allow users to create, edit, tag, version, and organize eval test cases. Each test case shall support input, expected behavior, scoring method, risk level, category, metadata, optional source documents, and optional tool constraints.

### 10.2 Dataset Execution
The system shall allow users to run: single test case, selected category, smoke suite, regression suite, full eval suite, and custom dataset.

### 10.3 System Configuration
The system shall allow eval runs against configurable system versions, including: model, prompt, retriever, tool definitions, memory settings, agent loop configuration, temperature, system instructions, and context documents.

### 10.4 Scoring
The system shall support: exact match, structured output validation, rubric scoring, LLM-as-judge scoring, human review, citation scoring, tool-use scoring, safety scoring, and regression comparison.

### 10.5 Evidence Capture
The system shall record: input, output, prompt version, model version, dataset version, scores, trace data, tool calls, retrieved documents, latency, token usage, and errors.

### 10.6 Reporting
The system shall generate: run summary, detailed failure report, trend report, regression report, risk report, model comparison report, and prompt comparison report.

### 10.7 Human Review
The system shall allow a human reviewer to: override a score, add notes, confirm failure category, mark a test case as ambiguous, recommend dataset changes, and approve scorer calibration.

### 10.8 Regression Detection
The system shall compare current results against a baseline and identify: new failures, fixed failures, unchanged failures, score drops, score improvements, and category-specific regressions.

---

## 11. Non-Functional Requirements

| Requirement | Description |
|---|---|
| Reliability | Produce consistent results when using deterministic settings where possible |
| Repeatability | Each eval run shall be reproducible based on saved configuration, dataset version, and system version |
| Auditability | Preserve enough evidence for a reviewer to understand what happened and why the score was assigned |
| Extensibility | Allow new scorers, datasets, models, and adapters to be added without redesigning the entire system |
| Security | Protect sensitive test data, prompts, documents, and outputs from unauthorized access |
| Performance | Support both quick local runs and larger batch runs |
| Usability | Support CLI usage first, with optional dashboard/reporting later |

---

## 12. MVP Scope

The first version should be small. Do not try to build the cathedral first.

### MVP Features

- YAML or JSON test case format
- Small test dataset (≥20 cases)
- CLI runner script
- System-under-test adapter
- Basic scorers (exact match, rubric, LLM-judge, citation)
- Results saved to SQLite + JSON
- Markdown summary report
- Failure categorization
- Regression comparison against previous run
- Human review field

### MVP Reports

- Overall pass rate
- Pass rate by category
- Failed test cases with failure labels
- Before/after comparison
- Recommendation: PASS / FAIL / INVESTIGATE

---

## 13. Risks and Tradeoffs

| Risk | Mitigation |
|---|---|
| Overtrusting LLM Judges — judges can be wrong or inconsistent | Use calibration datasets, human review, and multiple scoring methods |
| Testing Only Easy Cases — harness looks good if the dataset is weak | Include production failures, edge cases, adversarial cases, and high-risk scenarios |
| Optimizing for the Test Instead of the User — system gets better at passing evals without becoming more useful | Keep evals tied to real user workflows and observed failures |
| Too Much Complexity Too Early — teams build a huge harness before understanding their failure modes | Start with a small smoke suite and grow from real failures |
| Security / Data Sensitivity — test prompts, documents, and outputs may be sensitive | Enforce access controls on results store; avoid logging PII |

---

## 14. Recommended Build Sequence

### Phase 1: Basic Harness
- Define test case format
- Create 10–20 test cases
- Build runner
- Call system under test
- Save outputs
- Manually review results

### Phase 2: Scoring
- Add exact match
- Add rubric scoring
- Add LLM-as-judge
- Add citation checks
- Add failure labels

### Phase 3: Regression
- Save baseline runs
- Compare new runs to old runs
- Flag regressions
- Generate markdown report

### Phase 4: Agent Evaluation
- Capture tool calls
- Score tool selection
- Score tool arguments
- Score recovery from tool failure
- Score final answer quality

### Phase 5: Operational Use
- Add CI/CD gate
- Add dashboard
- Add trace viewer
- Add production failure replay
- Add risk-weighted release recommendation

---

## 15. Definition of Done — MVP

The MVP is complete when:

- A user can define at least 20 eval test cases.
- A user can run the eval suite from a command line.
- The harness can test one AI system endpoint or function.
- The harness stores inputs, outputs, scores, and metadata.
- The harness produces a readable markdown report.
- The harness identifies pass/fail by test case.
- The harness supports at least three scorer types.
- The harness can compare one run against a previous baseline.
- A human reviewer can inspect failures and add notes.

---

## 16. Success Metrics

The Evals Harness is successful if it helps the team answer:

- Are we better than last version?
- What broke?
- Why did it break?
- Where should we improve first?
- Is this safe enough to release?
- What evidence supports that decision?

Specific metrics:

- Regression detection rate
- Reduction in repeated failures
- Dataset coverage by failure mode
- Pass rate by risk category
- Human-review agreement with automated scores
- Time to diagnose failures
- Number of production failures converted into evals

---

## 17. Plain-English Mental Model

Think of the eval harness like a **test range for AI behavior**.

> The AI system is the aircraft.
> The test cases are the flight profiles.
> The scorers are the instruments.
> The trace logs are the black box.
> The reports are the test report.
> The failure taxonomy is the discrepancy reporting system.

And the regression suite is how you make sure yesterday's fix did not break tomorrow's mission.

---

## 18. Key Design Principle

The harness should follow this loop:

> Observe failure → Name failure → Create test → Run eval → Improve system → Re-run eval

That is the real engine. The harness is not just for scoring. It is for learning.

---

## 19. Future Scope

Later versions may include:

- Dashboard and trace visualization
- OpenTelemetry integration
- Prompt version registry
- Dataset versioning UI
- Human review queue
- Judge calibration suite
- Production failure replay
- Synthetic test generation
- Risk-weighted scoring
- Cost and latency budgets
- Agent plan verification
- Memory evaluation
- Tool-call graph analysis

---

# PART II: TECHNICAL SPECIFICATION

*Code-ready specification for implementation by a coding agent or developer.*

---

## 20. System Architecture

### 20.1 Mission Statement (Operationalized)

The Agon Eval Harness is a CLI-first, deterministic-where-possible, async-execution evaluation framework that ingests versioned test datasets, executes them against pluggable Systems-Under-Test (SUT) via a normalized adapter contract, scores outputs through composable scorers, persists immutable run artifacts to a SQLite store, and emits Markdown + JSON + JUnit-XML reports suitable for CI/CD gating.

### 20.2 Required Tech Stack

| Layer | Technology | Version Constraint | Rationale |
|---|---|---|---|
| Runtime | Python | >=3.11, <3.13 | asyncio.TaskGroup, tomllib, modern typing |
| Data Validation | Pydantic | >=2.6, <3.0 | Schema enforcement, serialization |
| LLM Gateway | LiteLLM | >=1.40 | Provider-agnostic SUT + judge calls |
| Async Concurrency | asyncio + anyio | anyio>=4.0 | Structured concurrency, semaphores |
| Retry/Backoff | tenacity | >=8.2 | Exponential backoff w/ jitter |
| Persistence | SQLite via sqlalchemy | >=2.0 (Core) | Zero-config local store, queryable |
| CLI | typer | >=0.12 | Typed command interface |
| Semantic Similarity | sentence-transformers | >=2.7 (optional extra) | Embedding-based scorers |
| Lexical Metrics | rouge-score, rapidfuzz | latest | ROUGE-L, Levenshtein |
| Testing | pytest, pytest-asyncio | latest | Self-test of harness |
| Reporting | jinja2 | >=3.1 | Markdown/HTML templating |
| Config | pyyaml + tomllib | latest | Dataset + run config |

### 20.3 System Boundary Diagram

```
flowchart TD
  CLI[Typer CLI: agon run / compare / report] --> ORCH[Orchestrator]
  ORCH --> DL[DatasetLoader]
  DL -->|validated TestCase[]| ORCH
  ORCH --> EE[ExecutionEngine: async + Semaphore]
  EE -->|TestCase| ADAPTER[ModelAdapter Protocol]
  ADAPTER -->|HTTP/SDK via LiteLLM| SUT[(System Under Test)]
  SUT -->|SUTResponse| EE
  EE -->|SUTResponse + TestCase| SCORE[ScorerRegistry]
  SCORE -->|judge calls| JUDGE[(Judge LLM via LiteLLM)]
  SCORE -->|ScoreResult[]| EE
  EE -->|EvalResult| STORE[ResultsStore: SQLite]
  STORE --> RG[ReportGenerator]
  RG --> ART[Artifacts: .md / .json / junit.xml]
  STORE --> REG[RegressionComparator]
  REG --> RG
```

### 20.4 Architectural Invariants (MUST enforce)

1. **Idempotent runs:** Every run produces an immutable run_id (UUIDv4) and is never mutated post-completion. Human overrides create new review rows, not edits.
2. **Adapter isolation:** The harness MUST NOT contain any provider-specific logic outside `adapters/`.
3. **Deterministic seeding:** When temperature=0 and seed is set, runs MUST be flagged `deterministic=true`.
4. **Failure containment:** A single test-case failure (exception) MUST NOT abort the run. It is captured as `status=ERROR`.
5. **Schema-first:** No data crosses a module boundary except as a validated Pydantic model.

---

## 21. Module Map

```
agon/
├── schemas/         # Pydantic models (Section 22)
├── loaders/         # DatasetLoader
├── adapters/        # ModelAdapter implementations
├── execution/       # ExecutionEngine, RateLimiter, RetryPolicy
├── scoring/         # Scorer protocol + concrete scorers (Section 25)
├── store/           # ResultsStore (SQLite)
├── regression/      # RegressionComparator
├── reporting/       # ReportGenerator
├── cli/             # Typer app
└── config/          # RunConfig loading
```

---

## 22. Core Module Interfaces

All interfaces below are normative. The coding agent MUST implement these exact signatures.

### 22.1 ModelAdapter (Protocol)

```python
from typing import Protocol, runtime_checkable
from agon.schemas import SUTRequest, SUTResponse

@runtime_checkable
class ModelAdapter(Protocol):
    """Normalizes how the harness talks to any System-Under-Test."""
    name: str  # e.g. "litellm_chat", "http_endpoint", "langgraph_agent"

    async def invoke(self, request: SUTRequest) -> SUTResponse:
        """
        Send a single normalized request to the SUT and return a normalized
        response. MUST NOT raise on model-level errors; instead populate
        SUTResponse.error. MAY raise only on unrecoverable transport errors
        (handled by RetryPolicy).
        """
        ...

    async def health_check(self) -> bool:
        """Pre-flight: confirm SUT is reachable. Called once per run."""
        ...
```

**Concrete adapters (MVP):**

| Adapter | Class | Purpose |
|---|---|---|
| LiteLLM Chat | LiteLLMChatAdapter | Call any hosted model (GPT/Claude/Llama) via litellm.acompletion |
| HTTP Endpoint | HTTPEndpointAdapter | POST JSON to a user RAG/agent service, map response fields |
| Python Callable | CallableAdapter | Wrap an in-process async def fn(req) -> resp |

### 22.2 Scorer (Protocol)

```python
from typing import Protocol, ClassVar
from agon.schemas import TestCase, SUTResponse, ScoreResult, ScorerConfig

class Scorer(Protocol):
    scorer_type: ClassVar[str]   # unique key, e.g. "exact_match"
    requires_judge: ClassVar[bool]  # True if it calls an LLM judge

    def __init__(self, config: ScorerConfig) -> None: ...

    async def score(
        self,
        test_case: TestCase,
        response: SUTResponse,
    ) -> ScoreResult:
        """
        Produce a normalized ScoreResult. MUST be pure w.r.t. inputs
        except for judge LLM calls. MUST normalize to [0.0, 1.0] in
        ScoreResult.normalized_score regardless of native scale.
        """
        ...
```

### 22.3 DatasetLoader

```python
class DatasetLoader:
    def load(self, path: str | Path) -> Dataset:
        """
        Load .yaml/.yml/.json/.jsonl. Validate each record against TestCase.
        Raise DatasetValidationError aggregating ALL errors (do not fail on
        first). Compute dataset_version = sha256 of canonicalized, sorted
        test-case content.
        """

    def load_glob(self, pattern: str) -> Dataset: ...
```

### 22.4 ExecutionEngine

```python
class ExecutionEngine:
    def __init__(
        self,
        adapter: ModelAdapter,
        scorers: list[Scorer],
        config: RunConfig,
        store: ResultsStore,
    ) -> None: ...

    async def run(self, dataset: Dataset) -> RunSummary:
        """
        Execute all test cases with bounded concurrency, repetition,
        retry, and per-case error isolation. Persist each EvalResult
        incrementally. Return aggregate RunSummary.
        """
```

### 22.5 ResultsStore, RegressionComparator, ReportGenerator

```python
class ResultsStore:
    def init_schema(self) -> None: ...
    def save_run(self, run: RunRecord) -> None: ...
    def save_result(self, result: EvalResult) -> None: ...
    def get_run(self, run_id: str) -> RunRecord: ...
    def get_results(self, run_id: str) -> list[EvalResult]: ...
    def latest_baseline(self, dataset_version: str) -> RunRecord | None: ...
    def add_review(self, review: HumanReview) -> None: ...

class RegressionComparator:
    def compare(self, current: str, baseline: str) -> RegressionReport: ...

class ReportGenerator:
    def markdown(self, run_id: str) -> str: ...
    def json(self, run_id: str) -> dict: ...
    def junit_xml(self, run_id: str) -> str: ...
```

---

## 23. Data Schemas

All schemas are **Pydantic v2 models**. `model_config = ConfigDict(extra="forbid")` everywhere except metadata fields.

### 23.1 Input — Test Case

```python
from enum import StrEnum
from pydantic import BaseModel, Field, ConfigDict
from typing import Any

class RiskLevel(StrEnum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class Difficulty(StrEnum):
    EASY = "easy"; MEDIUM = "medium"; HARD = "hard"; ADVERSARIAL = "adversarial"

class ScoringSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str                              # must match Scorer.scorer_type
    weight: float = Field(1.0, ge=0.0)    # relative weight in composite
    pass_threshold: float = Field(0.5, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)

class ExpectedBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_answer: str | None = None
    answer_contains: list[str] = Field(default_factory=list)
    answer_not_contains: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    citation_required: bool = False
    allowed_sources: list[str] = Field(default_factory=list)
    expected_tool_calls: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] | None = None  # for structured output validation

class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_id: str = Field(pattern=r"^[a-z0-9_\-]+$")
    name: str
    category: str
    user_input: str
    context_documents: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    difficulty_level: Difficulty = Difficulty.MEDIUM
    expected: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    scoring: list[ScoringSpec] = Field(min_length=1)
    failure_labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    repetitions: int | None = None   # overrides RunConfig default
    metadata: dict[str, Any] = Field(default_factory=dict)

class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    dataset_version: str             # sha256, computed by loader
    test_cases: list[TestCase] = Field(min_length=1)
```

### 23.2 SUT Request / Response

```python
class SUTRequest(BaseModel):
    user_message: str
    documents: list[str] = Field(default_factory=list)
    session_id: str
    config_overrides: dict[str, Any] = Field(default_factory=dict)

class TokenUsage(BaseModel):
    input: int = 0; output: int = 0; total: int = 0

class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None

class SUTResponse(BaseModel):
    final_answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    retrieved_documents: list[str] = Field(default_factory=list)
    trace_id: str
    latency_ms: float
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    raw_trace: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None   # model-level error (non-fatal)
```

### 23.3 Run Configuration

```python
class RetryConfig(BaseModel):
    max_attempts: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    jitter: bool = True

class JudgeConfig(BaseModel):
    model: str = "gpt-4o"         # LiteLLM model string
    temperature: float = 0.0
    seed: int | None = 42
    max_tokens: int = 1024

class SUTConfig(BaseModel):
    adapter: str                   # "litellm_chat" | "http_endpoint" | "callable"
    model: str | None = None
    temperature: float = 0.0
    seed: int | None = 42
    system_prompt: str | None = None
    prompt_version: str = "unversioned"
    endpoint_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    field_map: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_version: str            # e.g. "rag_agent_v1.7"
    sut: SUTConfig
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_concurrency: int = 8
    default_repetitions: int = 1
    rate_limit_rpm: int | None = None
    rate_limit_tpm: int | None = None
    fail_fast: bool = False
    baseline_run_id: str | None = None
    db_path: str = "agon_results.db"
    report_dir: str = "reports"
```

### 23.4 Output — Result Payloads

```python
class RunStatus(StrEnum):
    PASS = "pass"; FAIL = "fail"; ERROR = "error"

class ScoreResult(BaseModel):
    scorer_type: str
    native_score: float | str | bool
    normalized_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    weight: float
    rationale: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

class EvalResult(BaseModel):
    run_id: str
    test_id: str
    repetition_index: int             # 0-based
    status: RunStatus
    composite_score: float = Field(ge=0.0, le=1.0)
    passed: bool                      # ALL required scorers pass (AND logic)
    score_results: list[ScoreResult]
    detected_failure_labels: list[str] = Field(default_factory=list)
    sut_request: SUTRequest
    sut_response: SUTResponse | None = None
    error_message: str | None = None
    risk_level: RiskLevel
    category: str
    latency_ms: float = 0.0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    timestamp: str                    # ISO 8601 UTC

class RunRecord(BaseModel):
    run_id: str
    timestamp: str
    system_version: str
    prompt_version: str
    sut_model: str | None
    dataset_name: str
    dataset_version: str
    config_snapshot: dict[str, Any]
    deterministic: bool

class RunSummary(BaseModel):
    run: RunRecord
    total_cases: int
    total_executions: int
    overall_pass_rate: float
    pass_rate_by_category: dict[str, float]
    pass_rate_by_risk: dict[str, float]
    top_failure_labels: list[tuple[str, int]]
    error_count: int
    mean_latency_ms: float
    total_tokens: int
    recommendation: str              # "PASS" | "FAIL" | "INVESTIGATE"

class HumanReview(BaseModel):
    run_id: str
    test_id: str
    repetition_index: int
    reviewer: str
    override_score: float | None = None
    override_passed: bool | None = None
    confirmed_failure_labels: list[str] = Field(default_factory=list)
    ambiguous: bool = False
    notes: str
    timestamp: str

class RegressionReport(BaseModel):
    current_run_id: str
    baseline_run_id: str
    new_failures: list[str]
    fixed_failures: list[str]
    unchanged_failures: list[str]
    score_drops: list[tuple[str, float, float]]     # (test_id, old, new)
    score_improvements: list[tuple[str, float, float]]
    category_regressions: dict[str, tuple[float, float]]
    regression_detected: bool
```

---

## 24. Execution Pipeline

### 24.1 Concurrency Model

- Use `anyio.create_task_group()` for structured concurrency.
- Gate all SUT calls through a single `asyncio.Semaphore(max_concurrency)`.
- Results are persisted **incrementally** as each unit completes (crash-resilient).
- Scorers for a single response run concurrently via `asyncio.gather` (judge calls overlap).

### 24.2 Rate Limiting (Token-Bucket)

```python
class RateLimiter:
    """Dual token-bucket: RPM and TPM. acquire() before each SUT call."""
    def __init__(self, rpm: int | None, tpm: int | None): ...

    async def acquire(self, estimated_tokens: int = 0) -> None:
        # Block until both request-bucket and token-bucket have capacity.
        # Refill rate = limit / 60 per second.
        # Estimate tokens via len(text)//4 heuristic when exact count unavailable.
        ...
```

### 24.3 Retry Logic (Exponential Backoff + Jitter)

Wrap `adapter.invoke` with tenacity:

```python
@retry(
    stop=stop_after_attempt(config.retry.max_attempts),
    wait=wait_exponential_jitter(
        initial=config.retry.base_delay_s,
        max=config.retry.max_delay_s,
    ),
    retry=retry_if_exception_type((TransientError, RateLimitError, TimeoutError)),
    reraise=True,
)
async def _invoke_with_retry(...): ...
```

Backoff delay model:

> d_n = min(d_max, d_0 * 2^(n-1)) + U(0, J)

where n is the attempt index, d_0 the base delay, d_max the cap, and U(0,J) uniform jitter.

**Non-retryable** errors (4xx auth, malformed request, schema validation) MUST fail immediately → `EvalResult.status = ERROR`.

### 24.4 Repetition & Flakiness Semantics

- A test case runs `repetitions` times (case-level override > `default_repetitions`).
- Per-case **flake-aware pass rule** (configurable in `ScoringSpec.params`):
  - `"all"` (default for `risk_level >= HIGH`): pass iff **every** repetition passes.
  - `"any"`: pass iff **at least one** repetition passes.
  - `"majority"`: pass iff > 50% repetitions pass.
- The aggregate stores all repetitions; the rollup applies the rule.

### 24.5 Failure State Recovery

- Each `EvalResult` is committed in its own SQLite transaction.
- On harness crash, a `resume` command re-queries the store for completed `(test_id, repetition_index)` pairs under `run_id` and executes only the remainder.

---

## 25. Scorer Implementation Specifications

All scorers normalize to [0.0, 1.0]. `passed = normalized_score >= ScoringSpec.pass_threshold`.

### 25.1 ExactMatchScorer (`exact_match`)

```
normalize(x) = strip(lower(collapse_whitespace(x))) [unless params.case_sensitive]
native_score = bool(a == e)
normalized_score = 1.0 if match else 0.0
```

### 25.2 JSONSchemaValidatorScorer (`json_schema`)

```
Parse response.final_answer as JSON. If parse fails → 0.0.
Validate against test_case.expected.json_schema (jsonschema lib).
normalized_score = 1.0 if valid else 0.0
details = {"validation_errors": [...]}
```

### 25.3 SemanticSimilarityScorer (`semantic_similarity`)

```
cos = (emb_a · emb_e) / (||emb_a|| * ||emb_e||)
normalized_score = clamp((cos + 1) / 2, 0, 1)
```

Default `pass_threshold = 0.80`. Gate `sentence-transformers` behind optional extra `[semantic]`.

### 25.4 RougeLScorer (`rouge_l`)

Use `rouge_score.RougeScorer(['rougeL'])`. `native_score = rougeL.fmeasure`, `normalized_score = native_score`.

### 25.5 KeywordContainmentScorer (`keyword_containment`)

```
hits = count of answer_contains substrings present (case-insensitive)
violations = count of answer_not_contains substrings present
base = hits / max(1, len(answer_contains))
normalized_score = 0.0 if violations > 0 else base
```

### 25.6 RubricScorer (`rubric`) — LLM-as-Judge

Rubric is a dict `{int: description}` (e.g. `{0: "..", 1: "..", 2: "..", 3: ".."}`).

**Judge prompt template** (`rubric_judge.jinja2`):

```
You are a strict, calibrated evaluator. Score the ANSWER against the RUBRIC.

USER QUESTION:
{{ user_input }}

{% if context %}SOURCE CONTEXT:
{{ context }}{% endif %}

EXPECTED (reference):
{{ expected_answer }}

ANSWER UNDER EVALUATION:
{{ final_answer }}

RUBRIC (assign exactly one integer score):
{% for k, v in rubric.items() %}{{ k }} = {{ v }}
{% endfor %}

Rules:
- Penalize unsupported claims and hallucinations.
- Do not reward verbosity.
- Return ONLY valid JSON: {"score": <int>, "rationale": "<one sentence>"}
```

```
max_rubric = max(rubric keys)
native_score = parsed.score
normalized_score = native_score / max_rubric
```

**Calibration requirement:** Judge MUST use `temperature=0`, fixed seed. Parse via strict JSON; on parse failure retry once, then mark `status=ERROR`.

### 25.7 FaithfulnessScorer (`faithfulness`) — RAG

Decompose answer into atomic claims, verify each against retrieved context.

- **Stage 1 — claim extraction prompt** → returns `["claim1", ...]`
- **Stage 2 — verification prompt** per claim → `{"supported": bool}`

```
Faithfulness = |claims supported by context| / |total claims|
```

`normalized_score = Faithfulness`. Empty-claim edge case → 1.0.

### 25.8 AnswerRelevanceScorer (`answer_relevance`) — RAG

Generate N synthetic questions from the answer (judge), embed each, compare to original question embedding.

```
AnswerRelevance = (1/N) * sum_i cossim(q_orig, q_i_gen)
```

Default N = 3. Normalize via `(sim + 1) / 2`.

### 25.9 ContextPrecisionScorer (`context_precision`) — RAG

For ranked `retrieved_documents`, judge each as relevant (1) or not (0). Compute precision@k weighted by rank:

```
ContextPrecision = sum_k(Precision@k * rel_k) / sum_k(rel_k)
where Precision@k = sum_{i=1}^{k} rel_i / k
```

If denominator is 0 → 0.0.

### 25.10 CitationScorer (`citation_check`) — RAG

```
required = test_case.expected.citation_required
presence = 1.0 if (not required) or len(actual) > 0 else 0.0
correctness = |actual ∩ expected| / max(1, |expected|) if expected else presence
out_of_scope = any(c not in allowed for c in actual) if allowed else False
normalized_score = 0.0 if out_of_scope else mean(presence, correctness)
labels: "missing_citation" if presence==0; "wrong_citation" if out_of_scope
```

### 25.11 ToolUseScorer (`tool_use`)

Composite over four sub-dimensions, equal weight:

```
s_selection     = |called ∩ expected| / max(1, |expected|)
s_no_forbidden  = 0.0 if called & forbidden else 1.0
s_valid_args    = fraction of tool_calls with no .error in args validation
s_recovery      = 1.0 if any failed tool_call followed by successful retry
                  else (1.0 if no failures else 0.0)
normalized_score = mean(s_selection, s_no_forbidden, s_valid_args, s_recovery)
labels: "tool_omission", "tool_misuse", "bad_recovery"
```

### 25.12 SafetyScorer (`safety`) — LLM-as-Judge, binary-critical

Judge prompt returns `{"safe": bool, "violation_type": str|null, "rationale": str}`.

```
normalized_score = 1.0 if safe else 0.0
pass_threshold MUST be 1.0 (safety scorers cannot have threshold < 1.0)
labels: "unsafe_answer", "over_refusal", "under_refusal", "policy_violation"
```

For `risk_level == CRITICAL`, any safety failure forces `RunSummary.recommendation = "FAIL"`.

### 25.13 Composite Scoring (per repetition)

```
composite = sum_j(w_j * s_j) / sum_j(w_j)
passed = ALL scorers with required=True pass (logical AND)
```

A scorer is "required" if its `ScoringSpec.weight > 0` AND not flagged advisory.

### 25.14 Failure-Label Derivation

Each scorer emits candidate labels in `details["labels"]`. The engine unions these across scorers, intersected with `test_case.failure_labels` (if non-empty acts as allow-list) → `EvalResult.detected_failure_labels`.

### 25.15 Regression Metric

```
new_failure    : baseline.passed AND NOT current.passed
fixed_failure  : NOT baseline.passed AND current.passed
score_drop     : current.composite < baseline.composite - epsilon (default 0.05)
regression_detected = len(new_failures) > 0 OR any high/critical score_drop
```

---

## 26. Actionable Implementation Tasks

Execute tasks sequentially. Each task is self-contained, ends with passing unit tests.

### Task 1 — Project Scaffold & Pydantic Schemas

- Create `pyproject.toml` with deps from §20.2; package `agon/`.
- Implement all models in §23 under `agon/schemas/`.
- Add `tests/test_schemas.py`: validate a sample TestCase, assert `extra="forbid"` rejects unknown keys, assert safety threshold validator forces 1.0.
- **DoD:** `pytest tests/test_schemas.py` green; `mypy agon/schemas` clean.

### Task 2 — DatasetLoader

- Implement `agon/loaders/dataset_loader.py` supporting `.yaml`, `.json`, `.jsonl`.
- Aggregate ALL validation errors into `DatasetValidationError`.
- Compute `dataset_version = sha256(json.dumps(sorted_canonical_cases))`.
- **DoD:** Loads the §27 example YAML; deterministic hash test; malformed file raises aggregated error listing every bad case.

### Task 3 — RateLimiter & RetryPolicy

- Implement dual token-bucket `RateLimiter` (§24.2) and tenacity-based retry wrapper (§24.3) in `agon/execution/`.
- Define `TransientError`, `RateLimitError`, `NonRetryableError`.
- **DoD:** Unit test asserts ≤ rpm acquisitions per simulated minute; retry test confirms exactly `max_attempts` on persistent `TransientError` and immediate stop on `NonRetryableError`.

### Task 4 — ModelAdapter Implementations

- Implement `ModelAdapter` protocol + `LiteLLMChatAdapter`, `HTTPEndpointAdapter`, `CallableAdapter` in `agon/adapters/`.
- Build an `AdapterRegistry` mapping `SUTConfig.adapter` string → class.
- HTTP adapter maps response JSON to `SUTResponse` via `SUTConfig.field_map`.
- **DoD:** `CallableAdapter` test wrapping a stub returns a valid `SUTResponse`; `LiteLLMChatAdapter` test mocks `litellm.acompletion`; `health_check` covered.

### Task 5 — Scorer Framework + Non-LLM Scorers

- Implement `Scorer` protocol, `ScorerRegistry`, and §25.1–25.5, 25.10: `exact_match`, `json_schema`, `semantic_similarity`, `rouge_l`, `keyword_containment`, `citation_check`.
- Gate `sentence-transformers` behind optional extra `[semantic]`.
- **DoD:** Parametrized tests verify each normalization formula at boundary values (0.0, 1.0, mid).

### Task 6 — LLM-as-Judge Scorers

- Implement Jinja2 templates and §25.6–25.9, 25.12: `rubric`, `faithfulness`, `answer_relevance`, `context_precision`, `safety`.
- Add `JudgeClient` wrapping LiteLLM with `temperature=0`, fixed seed, strict JSON parsing + one retry on parse failure.
- **DoD:** Tests mock `JudgeClient`; assert rubric normalizes `score/max`; assert safety failure yields `normalized_score=0.0`; assert JSON-parse-failure path sets ERROR.

### Task 7 — ResultsStore (SQLite)

- Implement SQLAlchemy Core schema: tables `runs`, `results`, `reviews`.
- Implement all `ResultsStore` methods (§22.5) with per-result transactions.
- **DoD:** Round-trip test: save run + results, reload, assert equality; `latest_baseline(dataset_version)` returns most recent matching run.

### Task 8 — ExecutionEngine

- Implement §24 pipeline: anyio task group, Semaphore, RateLimiter, retry-wrapped invoke, concurrent scorers, repetition rollup (§24.4), composite scoring (§25.13), label derivation (§25.14), incremental persistence, error isolation.
- Compute `RunSummary` aggregates.
- **DoD:** Integration test with `CallableAdapter` + stub scorers over a 5-case dataset (repetitions=3) produces correct `pass_rate_by_category`, isolates an injected exception as `status=ERROR`, never aborts run.

### Task 9 — RegressionComparator

- Implement §25.15 logic in `agon/regression/`.
- **DoD:** Test with two synthetic runs verifies `new_failures`, `fixed_failures`, `score_drops`, and `regression_detected` boolean.

### Task 10 — ReportGenerator

- Implement Markdown (Jinja2), JSON, and JUnit-XML emitters. Include regression section and recommendation (PASS/FAIL/INVESTIGATE) derived from pass-rate thresholds + safety/critical rules.
- **DoD:** Golden-file test for Markdown output; JUnit XML validates against schema; recommendation logic unit-tested (critical safety fail → FAIL).

### Task 11 — Typer CLI

- Commands: `agon run --config run.toml --dataset path`, `agon compare --current ID --baseline ID`, `agon report --run-id ID`, `agon review`, `agon resume --run-id ID`.
- Exit codes: 0 pass-gate, 1 fail-gate (regression or recommendation=FAIL), 2 abort (health check / config error).
- **DoD:** End-to-end test invokes `run` against `CallableAdapter`, asserts artifacts written to `report_dir` and correct exit code.

### Task 12 — Human Review & Resume

- Implement `add_review` flow (`HumanReview`) and crash-resume (§24.5) re-querying completed `(test_id, repetition_index)`.
- **DoD:** Test simulates partial run, resumes, asserts no duplicate executions and full completion.

### Task 13 — Self-Test Fixtures & Docs

- Ship `examples/datasets/rag_smoke.yaml` (≥20 cases), `examples/run.toml`, and a README quickstart.
- **DoD (MVP complete):** `agon run` over the 20-case dataset using ≥3 scorer types produces Markdown report, pass/fail per case, baseline comparison, and exits with a deterministic gate code.

---

## 27. Example Test Case (YAML Format)

```yaml
test_id: rag_001
name: Answer must be grounded in source document
category: RAG factuality
risk_level: high
difficulty_level: medium

input:
  user_message: "What does the policy say about emergency leave?"
  documents:
    - hr_policy_2026.pdf

expected:
  answer_contains:
    - "supervisor approval"
    - "emergency leave"
  citation_required: true
  allowed_sources:
    - hr_policy_2026.pdf

scoring:
  - type: citation_check
    weight: 1.0
    pass_threshold: 1.0
  - type: rubric
    weight: 1.5
    pass_threshold: 0.67
    params:
      rubric:
        3: "Correct, complete, and supported by citation"
        2: "Mostly correct but missing minor detail"
        1: "Partially correct but weakly supported"
        0: "Incorrect or unsupported"

failure_labels:
  - missing_citation
  - unsupported_claim
  - incomplete_answer

tags:
  - RAG
  - policy
  - citation
```

---

## 28. Example Eval Run Output

```json
{
  "run_id": "eval_2026_06_04_001",
  "system_version": "rag_agent_v0.3",
  "dataset": "rag_regression_suite_v0.1",
  "overall_pass_rate": 0.86,
  "recommendation": "INVESTIGATE",
  "results": [
    {
      "test_id": "rag_001",
      "composite_score": 0.92,
      "passed": true,
      "failure_labels": [],
      "latency_ms": 2400
    },
    {
      "test_id": "rag_002",
      "composite_score": 0.33,
      "passed": false,
      "failure_labels": ["missing_citation", "unsupported_claim"],
      "latency_ms": 3100
    }
  ]
}
```

---

## 29. One-Sentence Definition

An **Evals Harness** is a repeatable testing system that runs AI behavior through known challenges, captures what happened, scores the result, labels failures, compares versions, and produces evidence for improvement or release decisions.

---

*Document assembled from: ChatGPT 5.5 (product definition, user stories, failure taxonomy, build sequence), Ask Sage / Claude Opus 4.8 (implementation spec, schemas, scorer algorithms, architectural invariants), and GenAI.mil / Gemini (supplementary framing).*
