# Proposed Table of Contents — *The Agon Eval Harness: A Practitioner's Manual*

> **Status:** Revised non-binding proposal for final review (rev. 2). No manual text has been
> drafted. This document presents the structure, chapter list, per-chapter topics, length estimate,
> resolved production decisions, and a gap analysis — for your approval before any drafting begins.
>
> **Drafting cadence once approved:** Part I only first — **Chapters 1–4 plus the front-matter
> "Note to the T&E reader"** — then stop for your review of teaching voice and depth calibration
> before any further chapters. Nothing past Part I will be drafted until you approve Part I.

---

## Context

**Why this proposal exists.** You asked for a textbook-style training manual that takes a single
reader — a DoD Test & Evaluation professional with strong systems instincts but no CS background —
from zero to proficient operation of the Agon harness, *and* to a transferable understanding of eval
harnesses in general. The four learning goals, in your priority order: (1) operate Agon across common
use cases, (2) understand/operate any standard eval harness, (3) articulate the discipline — what a
harness is for, how it improves a system during development and maintains trustworthiness in
production, and (4) use the harness to localize failures so they can be fixed and kept from silently
regressing.

**What I did to build this proposal.** I inventoried the shipped `agon/` package (16 subpackages,
9 CLI commands, ~47 test files), the examples and templates, the 13 ADRs under `docs/decisions/`,
the methodology essay (`docs/methodology/measuring-agentic-systems.md`), the README, and the
operational guides. That inventory is what lets me tag each topic as recoverable-from-repo or not.

**Two confirmed structural decisions** (from your earlier answers):
- **Interleave register *within* each chapter** — each component chapter carries both the *why*
  (concept/rationale) and the *how* (commands, file paths, hands-on), in that order.
- **Weave general harness theory throughout** — every component generalizes from Agon to the
  portable principle, with a line or two on how other harnesses (Inspect AI natively, plus
  lm-eval-harness / promptfoo / OpenAI Evals) express the same idea. No standalone survey chapter.

---

## Structural Requirements & Authoring Principles (binding on every chapter)

These govern how each topic is written, not just what appears. They begin in Part I.

**Tagging legend:**
- **`[code-resident]`** — the topic's full meaning, *including the why*, is recoverable by reading
  the repository (source, configs, tests, ADRs, README, methodology essay, docstrings).
- **`[rationale-only]`** — the topic touches the code, but the reasoning behind it is *not* in the
  repo. Each is followed by a one-line note on exactly what must be supplied from outside the code.

**Principle 1 — `[code-resident]` does not mean "transcribe."** Where the *why* is recoverable from
an ADR or the methodology essay, the manual must *teach* it to a reader who does not already have the
context — never restate the ADR as if the reader wrote it. The ADRs were authored by someone who
already held the context; the manual builds that context from scratch. **Cohen's κ is the governing
model:** the mechanics are code-resident (the code computes κ and its CI), but the manual must still
teach *what κ is* and *why chance-correction matters*, not merely cite that the code computes it. So
a `[code-resident]` tag means "the facts and rationale exist in the repo," **not** "a paragraph of
citation will do." Treat every tag as a teaching obligation calibrated to a context-building reader.

**Principle 2 — Interpretation is a first-class success criterion.** A primary goal is that you can
look at a completed run and *translate the output into a decision* — not just read the fields, but
know what they are telling you to do next. The load-bearing pieces are the failure-localization
drill (Ch 13), acting on an INVESTIGATE recommendation (Ch 11), and metric interpretation such as
recall@k vs. MRR (Ch 14). "The reader can act on a result" is **not** deferred to Part III: Part I
must already begin building toward it (Ch 1 frames evidence→decision; Ch 4 makes the two-phase
workflow a decision loop, not a description). Every results-bearing topic carries an explicit
"what this is telling you to do" beat.

**A note on the tagging distribution.** This repo is unusually well-documented. The 13 ADRs and the
methodology essay push a large amount of *design rationale* into the `[code-resident]` column that
would normally be `[rationale-only]` — but per Principle 1 that rationale must still be *taught*, not
transcribed. The `[rationale-only]` topics that remain are genuinely absent from the repo:
pedagogical scaffolding for a non-CS reader, selection/decision guidance the repo never states, the
deeper naming/discipline argument, and the DoD T&E framing you want.

---

## Resolved Production Decisions

| # | Decision | Resolution |
|---|---|---|
| **1. Style / palette** | **General style guide** (`Projects/Claude/general-style-guide.md`: Steel Blue / Charcoal / Amber) for body, tables, and overall layout — **with Teal-Blue `#0F4761` as the dominant heading color across the full heading hierarchy (H1–H4).** This is a *Learning* artifact about Agon: **no AVSH product branding, no AVSH running header/footer.** Teal-Blue in the headings; general style everywhere else. The two guides are not mixed beyond this single deliberate heading-color override. |
| **2. Cadence** | Per-part / per-chapter incremental delivery. **Part I (Ch 1–4 + front-matter T&E note) drafted first for tone and depth approval**, then stop. Subsequent parts only after Part I sign-off. |
| **3. Length** | **Full build — ~190–230 pages, all 24 chapters retained, all four specialized-eval chapters (14–17) kept separate.** Depth chosen deliberately. (No collapsing of Part IV; appendices stay in-document.) |
| **4. Figures** | **Commissioned vector figures**, not only inline Mermaid/ASCII. Minimum required set: (a) **the five-stage pipeline — Ch 3**; (b) **the two-phase workflow loop — Ch 4**; (c) **the OpenTelemetry span tree — Ch 19**; (d) **the failure-localization drill — Ch 13.** Additional figures may be proposed per chapter. Added page count and production time accepted (reflected in the estimate below). |

---

## Source Integrity & Figure Traceability (correction + standing rule)

- **Known statistic drift — do not carry forward.** In your own source corpus, the Shankar/Husain
  course enrollment figure appears inconsistently as both **"2,000+"** and **"4,500+"**. **Neither
  number will be used in the manual** until you reconcile it. If industry-context framing in Ch 1
  would naturally cite it, the manual will phrase around the figure (or leave a clearly marked
  `[TK: enrollment figure pending reconciliation]`) rather than pick one.
- **Standing rule for the whole manual:** any quantitative claim that cannot be traced to a primary
  source will be **flagged, not repeated.** I will surface such figures for your decision rather than
  silently propagate a number whose provenance I can't establish — consistent with the harness's own
  evidence-over-claims principle. (No other untraceable figures were encountered in the repo itself
  during this pass; the repo's claims are tied to runnable commands. The drift risk lives in the
  external source corpus, so the rule matters most in the discipline/industry-context sections.)

---

## 1. Estimated Total Length

| Measure | Estimate | Basis |
|---|---|---|
| **Word count** | **84,000 – 97,000 words** | 24 chapters + front/back matter; foundational chapters ~3,000–4,000 words, component chapters ~3,500–5,000 (concept + code + hands-on + generalization + interpretation beat), appendices ~6,000 combined. |
| **Page count** | **≈ 200 – 235 pages** | Letter, 1" margins, general-style body (Charcoal) with Teal-Blue headings, data tables, code blocks, source notes — plus commissioned figures. Effective density ≈ 370–420 words/page given code/tables/figures. |
| **Figures** | **~12–18 commissioned vector figures** | Includes the four required (Ch 3, 4, 13, 19) plus ~8–14 supporting diagrams; adds roughly **10–18 pages** of figure real estate beyond the prose estimate (already folded into the page range). |
| **Chapters** | 24 (6 parts) + front matter + 5 appendices | See below. |
| **Code/command listings** | ~120–150 runnable snippets | Every operational topic pairs with a copy-runnable command or file excerpt drawn from the repo. |

**Assumptions** (flag if any are wrong): every major component gets a full
concept→code→hands-on→interpretation treatment; worked examples draw from the repo's own
`examples/` plus 2–3 new teaching examples (a minimal 3-case eval, a "failing run that gets fixed,"
and an end-to-end capstone); commissioned figures are produced to the general style guide with
Teal-Blue accents. This is a single-reader manual, so it leans explanatory rather than terse — the
main lever on total length, and one you've chosen deliberately for depth.

---

## 2. Chapter List & Per-Chapter Topics

### FRONT MATTER
- Title page, document code, version/date/author (general style guide; **no AVSH header/branding**).
- How to use this manual (the two registers; the tagging convention; the offline-first promise; the
  interpretation-first promise — every result section tells you what to *do*).
- **Note to the T&E reader** — mapping eval-harness vocabulary to DoD T&E concepts you already own
  (V&V, DT/OT, test cards, regression suites, the test-fix-test loop). **`[rationale-only]`** —
  *the repo contains no T&E framing; this bridge is written from your domain expertise.* **(Drafted
  as part of the Part I batch.)**

---

### PART I — THE DISCIPLINE (why harnesses exist; the theory that transfers) — *drafted first*

**Ch 1 — What an Evaluation Harness Is (and Why It Matters).** Establishes the object of study
before any Agon specifics: a harness is a repeatable apparatus that subjects an AI system to designed
challenges and measures the results *as evidence for a decision*.
- What "evaluation harness" means; harness vs. benchmark vs. leaderboard vs. unit test. **`[rationale-only]`** — *repo never contrasts these; the absolute-readiness-gate vs. comparative-ranking distinction must be supplied.*
- The System Under Test (SUT) concept and why testing borrows the term. **`[rationale-only]`** — *code uses `SUTRequest`/`SUTResponse` but never defines/motivates the term for a newcomer.*
- Why the AI industry is "strong at demos, weak at evaluation." **`[rationale-only]`** — *README alludes to it; the industry history and concrete costs are not in the repo (and see Source-Integrity note re: the enrollment figure).*
- Evidence → decision: the first interpretation beat — a result exists to be *acted on*. **`[rationale-only]`** — *Principle 2 content; not in repo.*
- When to reach for a harness vs. a simpler tool (spot-check, A/B test, unit test). **`[rationale-only]`** — *no scoping/decision guidance exists in the repo.*
- The four guiding commitments as engineering, not slogans. **`[code-resident]`** — *stated in CLAUDE.md/README and enforced in code; taught, not transcribed.*

**Ch 2 — Why "Agon": The Philosophy of Adversarial Measurement.** The naming chapter you required;
argues that the name encodes the method.
- The Greek *agon* — purposeful opposition in service of improvement. **`[code-resident]`** — *README "Why 'Agon'?"; taught from first principles for a reader new to the framing.*
- Why *agon* is the *right* word vs. "challenge," "benchmark," "tournament," "arena." **`[rationale-only]`** — *README explains agon but never argues it against alternatives.*
- "Measurement is adversarial" as a working principle, not a metaphor. **`[code-resident]`** — *methodology essay principle #1; cashed out in the OWASP suite.*
- Trust as *survived challenge*, not demo success. **`[code-resident]`** — *README "Core Philosophy."*
- How the name shapes the architecture (the opponent is a first-class component). **`[rationale-only]`** — *the naming→architecture link is implicit; must be made explicit.*

**Ch 3 — The Universal Anatomy of an Eval Harness.** The portable mental model satisfying Goal #2
structurally. **★ Required figure: the five-stage pipeline.**
- Five-stage pipeline: Eval Suite → Harness/SUT → Evaluation Layer → Results → Continuous Improvement. **`[code-resident]`** — *README diagram + actual module boundaries; figure commissioned.*
- The four moving parts every harness has: cases, a system adapter, scorers, a results/decision layer. **`[code-resident]`** — *maps to `dataset`/`sut`/`scoring`/`reporting`.*
- Schema-first design: why data crosses module boundaries only as validated models. **`[code-resident]`** — *`schemas/models.py`; taught with the "why it protects you" reasoning.*
- How other harnesses express the same anatomy (Inspect `Task`/`Solver`/`Scorer`; lm-eval tasks; promptfoo configs). **`[rationale-only]`** — *only Inspect is in-repo; cross-harness mapping supplied.*
- Why Agon builds *on* Inspect AI rather than reinventing the runner. **`[code-resident]`** — *ADR-0001; taught as a build-vs-buy lesson, not an ADR quote.*

**Ch 4 — The Two-Phase Practitioner Workflow & Failure Localization.** The spine: the *same* harness
used differently before and after deployment, and how it pinpoints failure. **★ Required figure: the
two-phase workflow loop.** This chapter is where Part I's interpretation-first promise becomes
concrete.
- Phase 1 — development: the harness as adversary that finds failures before you ship. **`[rationale-only]`** — *essay describes a lifecycle but never frames two distinct phases with distinct run configs.*
- Phase 2 — production: the same harness as regression gate maintaining trustworthiness. **`[rationale-only]`** — *same gap; the "maintain trust post-deploy" use case is implied, not taught.*
- Failure localization (overview): how per-category, per-risk, per-case scoring tells you *where* it broke. **`[code-resident]`** — *`RunDigest` aggregates; full drill deferred to Ch 13.*
- "Failure is data": turning a discovered failure into a permanent regression case. **`[code-resident]`** — *mandated in CLAUDE.md; mechanism visible.*
- The develop→evaluate→deploy→observe→learn→improve loop as a *decision* loop. **`[code-resident]`** — *methodology essay principle #7; reframed around action.*
- T&E analogy: this is the DT/OT-and-regression cycle you already run, applied to a stochastic SUT. **`[rationale-only]`** — *supplied from your domain.*

---

### PART II — OPERATING AGON: THE CORE LOOP

**Ch 5 — Getting Started: Install, Offline-First, Your First Run.** From clone to a passing report in
under 20 minutes (the repo's hard reproducibility bar).
- `uv` environment, `.python-version` pin, `uv sync`, the extras map (providers/semantic/retrieval/otel/langgraph). **`[code-resident]`** — *`pyproject.toml`.*
- The offline path via Inspect's `mockllm/model` — no keys, no downloads, deterministic. **`[code-resident]`** — *observable in solvers + examples.*
- Why offline-first is a *prerequisite for trust*, not just convenience. **`[rationale-only]`** — *essay values reproducibility; the governance argument (reproducible→independent→accountable) must be supplied.*
- First run: `uv run agon run examples/datasets/rag_smoke.yaml --display none`; reading exit code 0/1/2 *as a decision*. **`[code-resident]`** — *CLI + exit-code semantics; interpretation beat.*
- `agon doctor` — versions, masked secret status, provider readiness. **`[code-resident]`** — *`cli/app.py`, ADR-0010.*

**Ch 6 — Anatomy of an Eval: Datasets, Cases & the Schema.** The case is the atom of evaluation.
- The `AgonCase`/`AgonDataset` schema: `input`, `expected`, `scoring`, `risk_level`, `category`, `failure_labels`, `tags`. **`[code-resident]`** — *`schemas/models.py`, example YAML.*
- Writing `dataset.yaml` by hand; SHA256 dataset versioning. **`[code-resident]`** — *`dataset/loader.py`.*
- `category` vs `risk_level`: orthogonal axes and how they interact at the gate. **`[rationale-only]`** — *both fields exist but their relationship/interaction is never explained.*
- How a case becomes an Inspect `Sample`. **`[code-resident]`** — *`dataset/loader.py` bridge.*
- Designing good cases: coverage, the seven categories, boundary/adversarial cases (T&E test-card thinking). **`[rationale-only]`** — *case-design methodology is not in the repo.*

**Ch 7 — The System Under Test (SUT).** How Agon talks to *anything* you want to evaluate.
- The normalized contract: `SUTRequest` / `SUTResponse` / `TokenUsage` / `ToolCall`. **`[code-resident]`** — *`sut/contract.py`.*
- Adapters: `mockllm`, `litellm`, `http`, `callable` — when to use each. **`[code-resident]`** — *`sut/solvers.py`; selection rationale partly in ADRs, taught as a decision.*
- Why scorers read from `SUTResponse` and never from the adapter (decoupling). **`[code-resident]`** — *contract design self-evident in code.*
- Hands-on: wrap your own system as a `callable` adapter (`run.py` pattern). **`[code-resident]`** — *`examples/*/run.py`, `templates/your-eval/`.*

**Ch 8 — Scoring I: Deterministic Scorers.** The "matchers" — fast, free, offline, exact.
- Concept: matcher vs. judge, and why you prefer a matcher when you can use one. **`[rationale-only]`** — *the distinction and the "prefer deterministic" heuristic are not stated in the repo.*
- The scorer registry and `@register`; `ScoreOutcome` [0–1] normalization. **`[code-resident]`** — *`scoring/base.py`.*
- `exact_match`, `keyword_containment`, `json_schema`, `citation_check`, `rouge_l`, `semantic_similarity`. **`[code-resident]`** — *`scoring/non_llm.py`.*
- Choosing a deterministic scorer — a decision table by ground-truth shape and match tolerance. **`[rationale-only]`** — *repo lists scorers but offers no selection guidance.*
- Hands-on: add a scorer to a dataset and run it; write the boundary test that pins it. **`[code-resident]`** — *test patterns + `templates/your-eval/test_scorer.py`.*

**Ch 9 — Scoring II: LLM-as-Judge & Calibration.** Using a model to grade a model — and proving the
judge trustworthy first.
- Concept: when a judge is necessary (open-ended outputs) and its risks. **`[rationale-only]`** — *motivation for judges is not spelled out.*
- Judge-backed scorers: `rubric`, `safety`, `faithfulness`, `context_precision`, `answer_relevance`. **`[code-resident]`** — *`scoring/llm.py`.*
- The `JudgeClient`: deterministic generation (temp 0, fixed seed), JSON parse + retry. **`[code-resident]`** — *`scoring/judge.py`.*
- "A judge is an evaluated component, not ground truth." **`[code-resident]`** — *judge.py docstring + README requirement.*
- Calibration: Cohen's κ vs. raw accuracy; `agon calibrate`, `--min-kappa`, the gate. **`[code-resident]`** — *`calibrate/runner.py`, `stats/kappa.py`; mandated in ADR-0001.*
- **What Cohen's κ *is* and why chance-correction matters** (the Principle-1 exemplar, taught for a non-CS reader). **`[rationale-only]`** — *code computes κ but does not teach the concept.*

**Ch 10 — Scoring III: Composite Scoring, Categories & Risk.** How many scorers per case roll up into
one pass/fail without hiding anything.
- Weighted composite; `advisory` scorers that report but don't gate. **`[code-resident]`** — *`scoring/composite.py`, `ScoringSpec`.*
- Pass logic: every required scorer must meet its threshold. **`[code-resident]`** — *composite.py.*
- The seven evaluation categories tracked separately; "no single-number obsession." **`[code-resident]`** — *README + essay + per-category aggregation.*
- Why *these* seven categories, and whether they're exhaustive/extensible. **`[rationale-only]`** — *taxonomy listed but its derivation/completeness never argued.*
- Safety labels always surface, even when other labels are filtered. **`[code-resident]`** — *composite.py behavior.*
- Flake handling: `epochs` and the all/any/majority reducer. **`[code-resident]`** — *composite.py + RunConfig.*

**Ch 11 — Reading Results: Reports, Recommendations & Exit Codes.** Turning a run into a decision —
a load-bearing interpretation chapter.
- The three report formats — Markdown (human), JSON (machine), JUnit-XML (CI) — and where they're written. **`[code-resident]`** — *`reporting/generator.py`, templates.*
- The recommendation engine: PASS / INVESTIGATE / FAIL and the threshold + safety logic. **`[code-resident]`** — *`reporting/generator.py` `recommend()`.*
- Exit codes 0/1/2 as a release gate. **`[code-resident]`** — *`cli/app.py`.*
- `agon report` to regenerate without re-running. **`[code-resident]`** — *CLI.*
- **How to *act* on an INVESTIGATE — a day-in-the-life of triage.** **`[rationale-only]`** — *the interpretive/triage narrative is not in the repo (Principle 2 load-bearing piece).*

---

### PART III — MEASURING HONESTLY

**Ch 12 — Statistical Honesty: Confidence, Significance & Small Samples.** A pass rate is a point
estimate with error bars — taught for a numerate non-statistician.
- Wilson confidence intervals for pass rates; why Wilson over normal-approx at small n. **`[code-resident]`** — *`stats/proportion.py`, ADR-0007; taught, not cited.*
- The two-proportion z-test for "is this regression real or noise?" **`[code-resident]`** — *`stats/proportion.py`.*
- Small-sample warnings (n<30) and what they should change in your conclusions. **`[code-resident]`** — *`small_sample` flag.*
- What a confidence interval *means* (and what it doesn't). **`[rationale-only]`** — *code computes CIs; interpretation for a newcomer must be supplied.*
- The deliberate limits: no Bayesian/sequential/power analysis, and why that's an acceptable trade. **`[code-resident]`** — *ADR-0007 states the trade.*

**Ch 13 — Failure Localization & Regression Tracking.** Goal #4 in depth, and the second load-bearing
interpretation chapter. **★ Required figure: the failure-localization drill.**
- `RunDigest`: per-case records, pass-rate by category, by risk, top failure labels. **`[code-resident]`** — *`analysis/logs.py`.*
- The error taxonomy (timeout/resource/network/scorer/sample). **`[code-resident]`** — *`analysis/errors.py`, ADR-0009.*
- `agon compare` and `--baseline`: new failures, fixed, score drops, severity by risk. **`[code-resident]`** — *`analysis/regression.py`, CLI.*
- **The localization drill: category drop → case → failure label → trace → fix.** **`[rationale-only]`** — *the step-by-step diagnostic procedure is not written down; supplied as method + figure.*
- Closing the loop: promote the localized failure into a permanent case. **`[code-resident]`** — *mandated in CLAUDE.md; mechanism visible.*

---

### PART IV — SPECIALIZED EVALUATIONS *(all four chapters retained separately)*

**Ch 14 — Retrieval Evaluation in Isolation.** The repo's flagship separation-of-concerns principle.
- Why retrieval must be measured apart from generation. **`[code-resident]`** — *README principle, ADR-0002, enforced in composite.py exclusion.*
- IR metrics: recall@k, precision@k, MRR, nDCG, hit@k — computed natively. **`[code-resident]`** — *`retrieval/metrics.py`.*
- `agon retrieve corpus.yaml qrels.yaml`; retrievers: BM25 (offline default), LanceDB, hybrid RRF. **`[code-resident]`** — *`retrieval/`, ADR-0002.*
- How the code *enforces* isolation (retrieval scorers excluded from the gen composite). **`[code-resident]`** — *composite.py lines.*
- **Reading recall@k vs. MRR — what each tells you about a retriever, and what to do about it.** **`[rationale-only]`** — *metric interpretation/selection guidance is not in the repo (Principle 2 load-bearing piece).*

**Ch 15 — Agent Evaluation.** Evaluating tool-using, multi-step systems.
- Agent scorers: `tool_use`, `planning`, `step_efficiency`. **`[code-resident]`** — *`scoring/agent.py`.*
- Native ReAct SUT offline (`react_sut`) vs. experimental LangGraph bridge. **`[code-resident]`** — *`sut/agent.py`, `sut/langgraph.py`, ADR-0004.*
- Why native-for-CI + bridge-experimental (version churn vs. real-agent fidelity). **`[code-resident]`** — *ADR-0004.*
- Hands-on: `examples/agent_quickstart.py`. **`[code-resident]`** — *example.*
- Mapping agent failures to the seven categories (Tool Use / Planning / State). **`[rationale-only]`** — *the mapping heuristic is not written down.*

**Ch 16 — Adversarial Evaluation (OWASP for Agents).** The opponent, made concrete.
- OWASP Top 10 for Agentic Apps: prompt injection, goal hijacking, memory poisoning, tool misuse. **`[code-resident]`** — *README + `examples/adversarial_quickstart.py`, owasp_smoke.yaml.*
- `injection_resistance` scorer and canary-marker detection. **`[code-resident]`** — *`scoring/adversarial.py`.*
- Offline scripted attacks (`[sim:naive]`/`[sim:hardened]`) — a *detection harness*, not proof of real vulnerability. **`[code-resident]`** — *ADR-0005 states the scope honestly.*
- What's deferred (real-provider red-teaming) and why. **`[code-resident]`** — *ADR-0005.*
- Designing your own attack cases. **`[rationale-only]`** — *attack-authoring methodology is not in the repo.*

**Ch 17 — Regulated-Domain & Asymmetric-Cost Evaluation.** When one kind of error is far worse than
the other — closest to your DoD/T&E world.
- Asymmetric error costs; why aggregate accuracy hides safety-critical misses. **`[rationale-only]`** — *gait-triage demonstrates it; the broader "why ML eval underweights asymmetry" argument must be supplied.*
- The gait-triage worked example: asymmetric-ordinal scorer, binary-critical safety gate. **`[code-resident]`** — *`examples/gait_triage/`, `evals/gait_triage/`, ADR-0012, example README.*
- Human-in-the-loop as a design requirement; `agon review` append-only overrides. **`[code-resident]`** — *`review/store.py`, ADR-0012.*
- The "adjacent-not-exact analog" approach to building a regulated-domain eval. **`[code-resident]`** — *ADR-0012 (aligns with your stored DoD-adjacent framing).*
- Contributing an eval to `inspect_evals` via the Register. **`[code-resident]`** — *ADR-0013.*

---

### PART V — PRODUCTION & SCALE

**Ch 18 — Running Against Real Providers: Cost, Resilience & Secrets.** Leaving the offline sandbox
safely.
- Providers extra, `.env`, model strings; `--model`, `--adapter litellm`. **`[code-resident]`** — *`docs/running-real-evals.md`, config.*
- Resilience knobs exposed from Inspect (`--max-retries`, timeouts, `--fail-on-error`) — expose, don't reinvent. **`[code-resident]`** — *ADR-0006, CLI.*
- Cost tracking as a *dated advisory estimate*, not billing truth. **`[code-resident]`** — *`cost/`, ADR-0006.*
- Secret masking, redaction, preflight, `agon doctor`. **`[code-resident]`** — *`secrets.py`, ADR-0010.*
- Known limitation: raw Inspect `.eval` log isn't redacted. **`[code-resident]`** — *ADR-0010.*

**Ch 19 — Observability & Tracing.** Exporting runs for dashboards and longitudinal monitoring.
**★ Required figure: the OpenTelemetry span tree.**
- Why post-hoc export from the EvalLog instead of live hooks. **`[code-resident]`** — *ADR-0003.*
- The OpenTelemetry GenAI span tree (eval → invoke_agent → chat/execute_tool → agon.score). **`[code-resident]`** — *`observability/exporter.py`, `semconv.py`; figure commissioned.*
- `agon trace --backend console|langsmith|otlp`. **`[code-resident]`** — *CLI, ADR-0003/0011.*
- LangSmith dashboard recipes (pass-rate over time, errors by category, cost per run). **`[code-resident]`** — *`docs/langsmith-dashboards.md`, ADR-0011.*
- Connecting tracing to the production-monitoring half of the two-phase workflow. **`[rationale-only]`** — *the operational story of monitoring a deployed system over time is not narrated in the repo.*

**Ch 20 — Resume, Recovery & Error Taxonomy.** Surviving partial failures on long runs.
- `agon resume <run_id>` / `--latest`: re-run only failed/incomplete cases, merge reports. **`[code-resident]`** — *`task/resume.py`, ADR-0009.*
- How cases are reconstructed from log metadata. **`[code-resident]`** — *resume.py.*
- Known limits (epochs>1, ReAct path). **`[code-resident]`** — *ADR-0009.*

---

### PART VI — EXTENDING & MASTERY

**Ch 21 — Extending Agon: Plugins, Custom Scorers & SUT Adapters.** Making the harness yours.
- The three stable extension surfaces (dataset / scorer / SUT adapter). **`[code-resident]`** — *ADR-0008, `docs/extending.md`.*
- Writing a custom scorer (`AgonScorer` protocol + `@register`); loading via `--plugin`. **`[code-resident]`** — *`scoring/plugins.py`, ADR-0008.*
- The copy-me skeleton (`templates/your-eval/`) and the `text_to_sql` worked example. **`[code-resident]`** — *template + example.*
- When your domain's failure mode fits no built-in scorer — the build-test-register path. **`[rationale-only]`** — *mechanics are in-repo; the *decision* of when to build new vs. adapt is not.*
- The test obligation: every scorer ships with boundary tests. **`[code-resident]`** — *CLAUDE.md + test patterns.*

**Ch 22 — The Continuous Improvement Loop.** How the suite grows itself over time.
- Production traces → harvested new eval cases (`evals/production/` intent). **`[code-resident]`** — *README/CLAUDE.md state the intent (note: directory is planned, not yet populated — described honestly as roadmap).*
- The regression ratchet: every fixed failure becomes a permanent guard. **`[code-resident]`** — *principle + mechanism.*
- Governance: an eval suite as a living accountability artifact. **`[rationale-only]`** — *the governance framing must be supplied.*

**Ch 23 — Putting It Together: A Capstone Project.** One narrative thread from empty repo to a gated,
calibrated, traced eval — the day-in-the-life reference docs can't give.
- Build a small SUT, write 3 cases, run, watch it FAIL, localize, fix, watch it PASS. **`[rationale-only]`** — *no end-to-end "failing run that gets fixed" walkthrough exists; must be authored.*
- Add a judge, calibrate it, gate on κ. **`[code-resident]`** — *composable from existing pieces.*
- Wire it into CI with exit codes; add a baseline and detect a planted regression. **`[rationale-only]`** — *CI integration narrative is not in the repo.*
- Export to a dashboard; close the loop with a harvested production case. **`[code-resident]`** — *composable.*

**Ch 24 — Beyond Agon: Operating Any Harness.** Cashes out Goal #2 explicitly, once the reader has a
concrete anchor.
- The transferable checklist: cases, adapter, scorers, decision layer, reproducibility. **`[rationale-only]`** — *synthesis across harnesses; not in repo.*
- Reading an unfamiliar harness (Inspect AI internals, lm-eval-harness, promptfoo, OpenAI Evals). **`[rationale-only]`** — *only Inspect is in-repo; comparative literacy must be supplied.*
- What to demand of *any* harness you're asked to trust (the T&E acceptance lens). **`[rationale-only]`** — *your domain contribution.*

---

### BACK MATTER (Appendices)
- **App. A — CLI Reference.** Every command, flag, exit code. **`[code-resident]`** — *`cli/app.py`.*
- **App. B — Scorer Reference.** All built-in scorers, inputs, params, formulas. **`[code-resident]`** — *`scoring/*`.*
- **App. C — Config & Schema Reference.** `RunConfig`, `SUTConfig`, dataset YAML fields. **`[code-resident]`** — *`schemas/models.py`, `config/`.*
- **App. D — ADR Index.** One-line summary of each of the 13 ADRs, as a rationale map. **`[code-resident]`** — *`docs/decisions/`.*
- **App. E — Glossary.** SUT, scorer, judge, κ, Wilson interval, MRR, nDCG, RRF, OWASP, span, reducer, flake. **`[rationale-only]`** — *plain-language definitions for a non-CS reader; not in repo.*

---

## 3. Gap Analysis — Topics the Repo Does Not Cover (must be supplied before/while drafting)

Consolidated `[rationale-only]` themes — real content the manual needs that **cannot be
reconstructed from the repo**:

1. **Foundational concepts for a non-CS reader.** What an SUT is, matcher vs. judge, what Cohen's κ
   and a Wilson interval *mean*, what a confidence interval does and doesn't claim. (Principle 1: the
   code uses these correctly but never teaches them — Cohen's κ is the exemplar.)
2. **Selection / decision guidance.** Which scorer for which ground-truth shape; when to use a judge;
   when a sample size is sufficient; when to go to a real provider; when to write vs. adapt a scorer.
3. **The two-phase workflow framing.** Develop-with-the-harness vs. maintain-trust-in-production as
   distinct modes with distinct configs and questions.
4. **Failure-localization as a procedure.** The step-by-step drill (category drop → case → label →
   trace → fix → regression case). Mechanisms exist in code; the *method* is unwritten.
5. **Interpretation-to-action throughout** (Principle 2). Acting on INVESTIGATE (Ch 11), the drill
   (Ch 13), metric interpretation (Ch 14) — the load-bearing pieces, started in Part I.
6. **The deeper naming/discipline argument.** Why *agon* over alternatives; why eval engineering is
   its own discipline; why offline-first is a precondition for *trust*.
7. **The DoD T&E bridge.** Mapping every concept to V&V, DT/OT, test cards, acceptance gating.
8. **Worked examples the repo lacks.** A minimal 3-case eval; a "failing run that gets fixed"; an
   end-to-end CI-integrated capstone.
9. **Cross-harness literacy.** Inspect internals beyond what Agon touches, plus lm-eval / promptfoo /
   OpenAI Evals comparisons for Goal #2.
10. **Taxonomy justification.** Why exactly these seven categories; whether exhaustive; how
    domain-specific failure modes that fit none of them are handled.

**Minor scope flags** (accuracy, not gaps): `evals/production/` is a stated *intent*, not yet
populated; the OWASP suite implements a subset (4 attacks + 4 controls), not the full Top 10; the
LangGraph bridge is experimental. The manual describes these honestly as current-state vs. roadmap.

**Source-integrity flag** (carried from the section above): the Shankar/Husain enrollment figure
(2,000+ vs. 4,500+) is **held** pending your reconciliation; no untraceable quantitative claim will
be propagated.

---

## 4. What Happens Next (on approval)

1. You approve this revised plan (or request edits).
2. I draft **Part I only** — front-matter "Note to the T&E reader" + Chapters 1–4 — formatted to the
   general style guide with Teal-Blue `#0F4761` headings, including the two required Part I figures
   (Ch 3 five-stage pipeline; Ch 4 two-phase loop) as commissioned vector art.
3. We stop. You review teaching voice, depth calibration, and the interpretation-first treatment.
4. Only after your Part I sign-off do I proceed to subsequent parts, delivered per-part for review.

---

## 5. Verification

Not applicable to this proposal (no code/text drafted). When drafting begins, every operational topic
is verified by actually running its command offline against the repo (the `<20-minute`
reproducibility bar), and every `[code-resident]` claim is checked against the cited file path so the
manual never reports behavior by assertion — consistent with the harness's own evidence-over-claims
principle and the source-integrity rule above.
