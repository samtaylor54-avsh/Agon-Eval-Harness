<!--
  STYLING NOTE (for the eventual .docx build — not part of the body text):
  General style guide (Steel Blue / Charcoal / Amber, Segoe UI 11pt body) governs everything here,
  with ONE deliberate override: the full heading hierarchy (H1–H4) is rendered in Teal-Blue #0F4761.
  No AVSH branding, no AVSH running header/footer — this is a Learning artifact about Agon.
  Markdown cannot carry heading color; apply #0F4761 to all heading styles when this is typeset.
  Code/command listings are verbatim and were run offline against the repo during drafting.
-->

# The Agon Eval Harness — A Practitioner's Manual
## Part II — Operating Agon: The Core Loop

| | |
|---|---|
| **Document code** | AGON-TM-001 |
| **Part** | II — Operating Agon: The Core Loop (Chapters 5–11) |
| **Version** | 0.1 — *draft for review* |
| **Date** | 2026-06-08 |
| **Author** | Samuel R. Taylor |
| **Status** | Draft. Follows Part I (The Discipline). Carries Part I's conventions forward. |

---

### About this part

Part I was almost entirely *why*. Part II is where you sit down at the keyboard. These seven chapters walk the core operating loop end to end: install the harness and make it run offline (Ch 5), write the cases it runs (Ch 6), connect it to the thing you're testing (Ch 7), grade responses with mechanical scorers (Ch 8) and with an AI judge you've validated (Ch 9), roll many scores into one honest pass/fail (Ch 10), and read the result as a decision (Ch 11).

Every command in this part was run offline against the repository while drafting, and every output shown is real — copied from an actual run, not illustrative. Where a number appears, it is a number the harness produced on a clean checkout. That is the manual holding itself to the harness's own evidence-over-claims rule.

Two conventions from Part I continue here. Each section is tagged **`[code-resident]`** (recoverable from the repo, but taught here rather than transcribed) or **`[rationale-only]`** (genuinely not in the repo, supplied from outside it). And every results-bearing section ends by telling you what the result is *telling you to do* — the interpretation-first promise, now applied to real output.

---

# PART II — OPERATING AGON: THE CORE LOOP

---

## Chapter 5 — Getting Started: Install, Offline-First, Your First Run

The goal of this chapter is narrow and concrete: get from a fresh clone to a passing — or, as you'll see, a *deliberately failing* — report in under twenty minutes, with no API key and no model downloads. That twenty-minute bar is not a nicety; Chapter 1 named it as one of the four commitments, and this chapter is where you feel why it was worth engineering for.

### The environment: `uv`, the Python pin, and `uv sync`

*This is recoverable from `pyproject.toml` and `.python-version`; here it is taught as a setup sequence.*

Agon manages its environment with **`uv`** — a fast Python package-and-environment manager that does the job `pip` plus `virtualenv` plus a lockfile would otherwise do, in one tool. You install `uv` once (see its docs), and from then on every Agon command is prefixed `uv run`, which guarantees it runs inside the project's pinned environment rather than whatever Python happens to be on your path.

Two files control the environment. `.python-version` pins the interpreter to **3.12**. `pyproject.toml` declares the dependencies and the supported range, `requires-python = ">=3.11,<3.13"` — so 3.11 or 3.12, not 3.13. You do not have to manage any of this by hand. One command builds the whole environment:

```bash
uv sync        # create the virtual env and install all base dependencies
```

That installs everything the offline path needs and nothing it doesn't. The heavier, optional capabilities live behind **extras** — named dependency groups you opt into only when you need them:

| Extra | Install | What it adds | On the offline path? |
|---|---|---|---|
| `semantic` | `uv sync --extra semantic` | Embedding-based `semantic_similarity` scorer | No — downloads model weights |
| `providers` | `uv sync --extra providers` | Real LLM providers (OpenAI, Anthropic) | No — opt-in for live runs |
| `retrieval` | `uv sync --extra retrieval` | Isolated retrieval evals (BM25 offline; LanceDB/hybrid) | BM25 yes; vector search no |
| `langgraph` | `uv sync --extra langgraph` | Experimental LangGraph agent bridge | No — experimental |
| `otel` | `uv sync --extra otel` | OpenTelemetry span export (`agon trace`) | Console backend yes |

The design intent of that table is worth naming, because it is the offline-first commitment expressed as packaging: **the default install is the whole offline harness, and every extra is something that would compromise offline reproducibility if it were always on.** You can do real, complete evaluations having run nothing but `uv sync`.

### The offline path: `mockllm`, and why "offline" is not "fake"

*This is observable in the solvers and examples; the trust argument is `[rationale-only]` and supplied here.*

The piece that makes offline operation possible is a stand-in model called **`mockllm/model`** — Inspect AI's deterministic mock provider. When the harness runs against `mockllm`, no network call happens, no model is downloaded, no key is read, and the same inputs produce the same outputs on every machine, every time. The mock *is* the system under test on the default path. Chapter 7 shows how you later swap in your real system; for now, the mock is what lets you learn the whole harness without an account.

Here is the part that matters more than it first appears, and it is the manual's own version of Chapter 1's "evidence over claims": **offline does not mean the measurement is fake.** When the harness runs against the mock, it still meters every token exchanged and still reports a cost — which comes out to `$0.0000`, accurately, because the mock is free, not because cost reporting was switched off. A harness that quietly stopped measuring just because the run was free would be teaching you to trust a dishonest record. This one measures the same way offline and online; only the SUT changes.

And the deeper reason offline-first is a *precondition for trust*, not a convenience for working on a plane: a result anyone can reproduce, on any machine, with no credentials, is a result that can be *independently verified*. Verification is what converts "trust me, it passed" into "run it yourself and see." Every API key or model download you would otherwise need is an obstacle between your claim and someone else's ability to check it. Removing those obstacles is not about convenience. It is about accountability — the same reason a T&E result is worth more when an independent team can rerun the test rig and get your number.

### Your first run — and reading the exit code as a decision

*The command and exit-code semantics are `[code-resident]` in `cli/app.py`; the interpretation is taught.*

Run the twenty-case smoke suite against the offline mock:

```bash
uv run agon run examples/datasets/rag_smoke.yaml --display none
```

Here is the real result on a clean checkout:

```
rag_smoke_suite: pass 0.0% (0/20)  -> FAIL
  wrote reports\<run_id>.report.md
  wrote reports\<run_id>.report.json
  wrote reports\<run_id>.report.junit.xml
```

Zero of twenty. **This is not a broken install** — and understanding why is your first real lesson in operating the harness. The smoke suite asks for grounded answers with citations, but the bare `mockllm` model returns a fixed, canned completion that satisfies none of those cases. So every case fails, the recommendation is FAIL, and the process exits with code `1`.

That is the right behavior, and it is the interpretation beat at its simplest. The exit code is the harness's most compressed output, and it maps to an action:

- **`0` — PASS.** The recommendation was PASS and no regression fired. *Decision: proceed.*
- **`1` — FAIL gate.** The recommendation was FAIL **or INVESTIGATE**, or a regression was detected. *Decision: stop and look — something is below the bar or has moved.*
- **`2` — abort.** The run never produced a verdict: a bad config, an unreadable dataset, an unknown scorer, a failed health check. *Decision: fix the rig; do not conclude anything about the SUT yet.*

Hold onto the subtlety in code `1`, because Chapter 11 returns to it: the *recommendation* is three-valued (PASS / INVESTIGATE / FAIL) but the *gate* is binary. Anything short of a clean PASS exits `1`. The harness will not let an "INVESTIGATE" quietly pass a release gate just because it sounds softer than "FAIL."

To see what a *realistic* run looks like — a system that mostly works — run the quickstart, which wires in a smarter in-process stand-in SUT:

```bash
uv run python examples/quickstart.py
```

```
rag_smoke_suite: pass 85% -> INVESTIGATE
```

Eighty-five percent, INVESTIGATE — a mixed result with real failures to localize. That is the run Chapter 11 reads field by field. The contrast between `0/20 FAIL` and `85% INVESTIGATE` is the contrast between "the SUT isn't wired up" and "the SUT works but isn't yet good enough to ship."

### `agon doctor` — the preflight check

*This is `[code-resident]` in `cli/app.py` (the `doctor` command) and ADR-0010.*

Before a run — especially before your first one, or before a real-provider run — `agon doctor` tells you what state the harness is in:

```bash
uv run agon doctor
```

```
agon doctor
  agon:    0.1.0
  inspect: 0.3.235
  default path: offline (mockllm; no API key required)

secret env vars:
  ANTHROPIC_API_KEY: (not set)
  OPENAI_API_KEY: (not set)
  LANGSMITH_API_KEY: lsv2_...7119
  ...
```

Three things to read here. The **versions** of `agon` and the `inspect` engine underneath it — useful when a result needs to be reproduced later against the same tooling. The reassurance that the **default path is offline** and needs no key. And a **masked secret status**: every relevant key is listed as either `(not set)` or, when present, shown only as a masked fragment (`lsv2_...7119`) — never the full value. That masking is deliberate and consistent: Chapter 18 shows the same redaction discipline applied to reports and logs, so a key can never leak into an artifact you share. For now, `doctor` is the command you run when something doesn't behave and you want to rule out the environment before suspecting the harness.

---

## Chapter 6 — Anatomy of an Eval: Datasets, Cases & the Schema

The **case** is the atom of evaluation — one designed challenge with an expected outcome and a rule for grading it. A **dataset** is a validated collection of cases. Everything the harness does is, at bottom, running cases and grading them, so this is the chapter where you learn to write the thing the whole harness consumes. We'll build a case up field by field, then step back to the harder question the repo can't answer for you: what makes a case *good*.

### The case schema, field by field

*This is `[code-resident]` in `agon/schemas/models.py` and the example YAML; taught as a writer's reference.*

A case is a structured record. The harness will not run a malformed one — it validates every case against a schema (Chapter 3's schema-first principle, now concrete) and rejects anything that doesn't fit, naming the offending field. Here are the fields you'll actually write:

| Field | Required | What it holds |
|---|---|---|
| `test_id` | yes | A unique id, lowercase/digits/`_`/`-` (e.g. `rag_001`) |
| `name` | yes | A human-readable label |
| `category` | yes | The evaluation category (free-form string; see below) |
| `input` | yes | The challenge: `user_message`, optional `documents`, `session_id` |
| `scoring` | yes (≥1) | The list of scorers to apply, each a `ScoringSpec` |
| `expected` | no | The reference the scorers check against (answer, citations, schema…) |
| `risk_level` | no | `low` / `medium` / `high` / `critical` (default `medium`) |
| `difficulty_level` | no | `easy` / `medium` / `hard` / `adversarial` |
| `failure_labels` | no | An allow-list of labels this case may emit (Ch 10) |
| `tags` | no | Free-form labels for filtering |
| `repetitions` | no | Per-case epoch override (Ch 10 flake handling) |
| `sample_time_limit` | no | Per-case wall-clock cap, in seconds |

Here is a real case from the smoke suite, annotated:

```yaml
- test_id: rag_001
  name: emergency leave grounded answer
  category: rag_factuality
  risk_level: high                       # raises the stakes; drives the gate (Ch 10/11)
  input:
    user_message: "What does the policy say about emergency leave?"
    documents: [hr_policy_2026.pdf]      # context handed to the SUT
  expected:
    answer_contains: ["supervisor approval", "emergency leave"]
    citation_required: true
    allowed_sources: [hr_policy_2026.pdf]
  scoring:                               # two scorers, both must pass (Ch 10)
    - {type: citation_check, weight: 1.0, pass_threshold: 1.0}
    - {type: keyword_containment, weight: 1.0, pass_threshold: 1.0}
  failure_labels: [missing_citation, incomplete_answer]
  tags: [rag, policy, citation]
```

Top to bottom, it reads as a test card: here is the prompt, here is the context, here is what a correct answer must contain and cite, here is how we grade it, and here are the failure modes we expect to see if it goes wrong. The `scoring` block is the only part that takes real practice, and Chapters 8–10 are devoted to it. Everything else is description.

### Writing the dataset, and the content-addressed version

*This is `[code-resident]` in `agon/dataset/loader.py`.*

A dataset is a YAML file with a `name` and a `test_cases` list — the cases above, collected. You can write it by hand, and for small suites you should. When the loader reads it, it does two things worth knowing.

First, it **validates** every case and rejects the whole dataset if any case is malformed — so a typo in one case is caught at load time, not three stages into a run. Second, it computes a **`dataset_version`**: a SHA-256 hash of the canonicalized cases. You'll see it in every report as a short fingerprint:

```
| Dataset version | `ceb3f6f5f73e` |
```

That fingerprint is content-addressed, which means it is derived from the *content* of the cases, not a number you bump by hand. Change any case — even one character — and the fingerprint changes; leave the cases alone and it stays identical across machines and across time. The payoff is traceability: when you compare two runs (Chapter 13), the fingerprint tells you instantly whether they tested *the same cases*. A score that improved because the system got better and a score that "improved" because someone quietly edited the cases are different events, and the dataset version is what keeps you from confusing them. It is provenance for the test itself.

### `category` versus `risk_level`: two orthogonal axes

*Both fields exist in the schema, but their relationship and interaction are never explained in the repo — supplied here. `[rationale-only]`*

Two fields on a case look similar and are constantly confused, so pin the distinction now because it drives how you read every result. **`category` is what kind of thing the case tests. `risk_level` is how much a failure costs.** They are independent — orthogonal — axes.

`category` answers *what capability is under test* — `rag_factuality`, `structured_output`, `robustness`, and so on. It is the axis you slice by when localizing a failure: a pass-rate drop concentrated in one category tells you *where* the system broke (Chapter 13). Categories are how the harness refuses the single-number hiding place.

`risk_level` answers *what's at stake if this case fails* — `low`, `medium`, `high`, or `critical`. It does not describe the capability; it describes the consequence. And it has teeth: at the gate (Chapter 11), a safety failure on a `critical`-risk case forces an outright FAIL regardless of the overall pass rate. A `high`-risk case failing is, in the report, kept visibly separate from a `low`-risk case failing, even when the counts are equal, because they are not equivalent events.

The interaction is the important part. The two axes combine at decision time: `category` tells you *where* to look when something fails, and `risk_level` tells you *how hard to care* that it failed there. A formatting slip (`structured_output`, `low`) and an unsafe answer (`safety`, `critical`) can sit at the same composite score and demand completely different responses. Keeping the axes separate is what lets the harness — and you — tell them apart. This is the closest thing in Agon to a T&E reader's instinct that a Category I deficiency and a cosmetic finding are not the same finding, even if both are "fails."

### How a case becomes an Inspect `Sample`

*This is `[code-resident]` in the loader's bridge to Inspect.*

One mechanical fact closes the loop with Chapter 3. The harness does not run cases itself — it hands them to the Inspect engine. So at load time, each `AgonCase` is translated into an Inspect **`Sample`**, the unit the engine actually executes, with your case's content carried along as metadata so the scorers can read it back later. You almost never have to think about this, but it is the seam where "Agon's typed case" becomes "the engine's runnable unit," and it is why the cross-harness map in Chapter 3 put `AgonCase` and Inspect's `Sample` in the same row. They are the same idea on two sides of a boundary.

### Designing good cases

*Case-design methodology is not in the repo — supplied from T&E practice. `[rationale-only]`*

The schema tells you how to write a *valid* case. It cannot tell you how to write a *good* one, and that judgment is where evaluation engineering actually lives. Four habits, all of which a T&E reader already owns under other names:

**Cover the space, not the happy path.** A suite of cases the system obviously handles measures nothing (Chapter 2's "a suite that never catches anything is evidence the suite is weak"). Spend your cases where failure is plausible: boundaries, ambiguity, adversarial inputs, the conditions you'd probe in operational test, not the ones the builder demoed.

**Use the categories as a coverage checklist.** The seven evaluation categories (Functional Correctness, Tool Use, Planning, State Management, Robustness, Reliability, Safety) are a prompt: have I written cases that exercise each one that applies to my system? A suite heavy on functional correctness and empty on robustness has a blind spot exactly where fielded systems tend to fail.

**Set `risk_level` honestly, by consequence.** Reserve `critical` for cases where a failure is genuinely disqualifying — the ones that should sink a release on their own. Inflate it everywhere and the gate becomes noise; never use it and the gate can't protect you. This is the same discipline as severity classification on a deficiency report.

**Write the failure in when you write the case.** Populate `failure_labels` with the failure modes you expect this case to catch. That is what later lets the harness tell you not just *that* a case failed but *what kind* of failure it was — and it is the seed of the "failure is data" loop, because the case you write today to catch a known failure mode is the regression guard that catches it again tomorrow.

---

## Chapter 7 — The System Under Test (SUT)

Chapter 1 defined the SUT as the bounded thing you've drawn a box around and declared responsible for the result. This chapter is about the wall of that box: the single, fixed contract through which Agon talks to *whatever* you're evaluating, so that the rest of the harness never has to know or care what's on the far side.

### The normalized contract

*This is `[code-resident]` in `agon/sut/contract.py`.*

No matter what your system is — a hosted model, a prompt, a full tool-using agent, an external RAG service, a function on your laptop — Agon speaks to it through two small shapes. A **`SUTRequest`** goes in; a **`SUTResponse`** comes back.

```
SUTRequest:  user_message · documents · session_id · config_overrides
SUTResponse: final_answer · citations · tool_calls · retrieved_documents
             · token_usage · latency_ms · trace_id · error
```

The request is just the challenge from the case. The response is richer, because it has to carry everything any scorer might want to grade: the answer text (`final_answer`), the sources cited (`citations`), any tools the system called (`tool_calls`), the documents it retrieved (`retrieved_documents`), and metering (`token_usage`, `latency_ms`). Two supporting shapes fill it out — `TokenUsage` (input/output/total token counts) and `ToolCall` (a tool name, its arguments, its result, any error).

This contract *is* the box wall from Chapter 1. Everything expressed as `SUTRequest`/`SUTResponse` is the boundary; everything behind `final_answer` is the system under test. Drawing the box well — deciding what your SUT includes — is the design judgment; the contract is just where that judgment becomes code.

### The four adapters, and when to use each

*This is `[code-resident]` in `agon/sut/solvers.py`; the selection guidance is taught as a decision.*

An **adapter** is the piece that connects the universal contract to one specific kind of system. Agon ships four:

| Adapter | What it talks to | Reach for it when |
|---|---|---|
| `mockllm` | Inspect's deterministic mock | Learning, CI, any offline run — the default |
| `litellm` | A real hosted provider (OpenAI, Anthropic, …) | Evaluating an actual model via its API (Ch 18) |
| `http` | An external service over HTTP POST | Your system runs as a service (a RAG/agent endpoint) |
| `callable` | An in-process async function | Your system is Python you can call directly |

The selection logic is mostly mechanical: pick the adapter that matches *where your system lives*. In process? `callable`. Behind an HTTP endpoint? `http`. A raw hosted model you want to test directly? `litellm`. Nothing real yet, or running in CI? `mockllm`. One convenience worth knowing: if you pass `--model` on the command line without naming an adapter, the harness infers you mean a real provider and switches the adapter from `mockllm` to `litellm` for you.

### Why scorers read the response, never the adapter

*This is `[code-resident]` and self-evident in the contract design; the reasoning is taught.*

Here is the decoupling that makes the whole arrangement pay off, and it's worth stating because it's the kind of design you'll want to recognize in other harnesses. **Scorers read from `SUTResponse`. They never know which adapter produced it.** Every adapter's only job is to produce a normalized `SUTResponse`; from there, a scorer that checks citations works identically whether the citations came from a mock, a live model, an HTTP service, or a local function.

The payoff is that the two halves of the harness vary independently. You can swap your SUT from a mock to a real provider without touching a single scorer, and you can add a new scorer without touching a single adapter. That is the schema-first principle from Chapter 3 doing exactly what it promised: a clean contract at the boundary means each side can change without breaking the other. When you later evaluate an unfamiliar harness, "does the scoring layer depend on how the system was called?" is a sharp diagnostic question — a harness where it does will fight you every time you change systems.

### Hands-on: wrap your own system as a `callable`

*This is `[code-resident]` — the `examples/*/run.py` pattern and `templates/your-eval/`.*

The fastest way to evaluate your own code is the `callable` adapter. You write one async function that takes a `SUTRequest` and returns a `SUTResponse`, and you tell the run to use the `callable` adapter. Here is the shape, drawn from the offline text-to-SQL example:

```python
from agon.schemas import RunConfig, SUTConfig
from agon.sut import SUTRequest, SUTResponse

async def my_sut(req: SUTRequest) -> SUTResponse:
    # req.user_message is the prompt; req.documents is the context.
    # Call whatever your system is, however it works:
    answer = my_system(req.user_message, req.documents)
    return SUTResponse(final_answer=answer)

config = RunConfig(system_version="my_v1", sut=SUTConfig(adapter="callable"))
# the run is then driven with my_sut wired in as the callable SUT
```

That is the entire integration surface. Your system can be anything — a model call, a chain, a heap of business logic — and as long as it can be reached from one async function that fills in a `SUTResponse`, Agon can evaluate it. The `templates/your-eval/` skeleton in the repo is a copy-me starting point with this wiring already in place; Chapter 21 returns to it when we extend the harness in earnest. For now, the lesson is that "make Agon talk to my system" is a small, bounded task by design — you implement one function against one contract, and everything else in the harness just works.

A generalization to close on: this adapter pattern is universal. Inspect calls the equivalent a `Solver`; promptfoo calls it a `provider`; every harness has *some* seam where "the thing under test" plugs in. Recognizing that seam is how you orient yourself in any harness you're handed.

---

## Chapter 8 — Scoring I: Deterministic Scorers

Now the heart of the harness: turning a response into a measurement. This chapter covers the **deterministic scorers** — the mechanical, exact, offline, free ones — and the principle that should govern your whole approach to scoring: prefer the simplest rule that captures what "correct" means.

### Matcher versus judge — and why to prefer a matcher

*The distinction and the "prefer deterministic" heuristic are not stated in the repo — supplied here. `[rationale-only]`*

Scorers come in two families. A **matcher** is a deterministic rule: it checks the response against a fixed criterion — does it contain this string, does it match this schema, does it cite this source — and returns the same answer every time. A **judge** is another AI model asked to grade the response (Chapter 9). Both have their place, but there is a clear default: **prefer a matcher whenever a matcher can capture what you mean by correct.**

The reasoning is practical, not ideological. A matcher is free, instant, fully offline, and — crucially — *itself trustworthy without further validation*. A judge is none of those: it costs tokens, adds latency, requires a provider, and is itself a system of unknown reliability that you must validate before you trust it (the entire subject of Chapter 9). So every criterion you can express as a matcher is a criterion you get to grade for free, deterministically, and without inheriting a second system's uncertainty. Reach for a judge only when the thing you're grading is genuinely open-ended enough that no mechanical rule can capture it. The order of Chapters 8 and 9 is the order of your preference.

### The registry, the decorator, and the normalized outcome

*This is `[code-resident]` in `agon/scoring/base.py`.*

Mechanically, a scorer is a small object with a `scorer_type` name and an async `score` method, registered so the harness can find it by name. Registration is one decorator:

```python
from agon.scoring.base import ScoreOutcome, register

@register
class MyScorer:
    scorer_type = "my_scorer"      # the name you reference in a case's scoring block
    requires_judge = False         # True if it needs an AI judge

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        ...
```

Two things to notice. The `@register` decorator adds the scorer to `default_registry`, which is how a case's `scoring: [{type: my_scorer}]` finds the implementation. (If a case names a scorer that isn't registered, the run aborts with exit `2` and lists what *is* registered — a config error, caught before any work is done.) And every scorer returns the same shape, a **`ScoreOutcome`**, whose central field is a `normalized_score` between `0.0` and `1.0`.

That normalization is the quiet design decision that makes everything downstream possible. A keyword match, a schema validation, a ROUGE overlap, and a judge's rubric rating produce wildly different native numbers — but every one of them is normalized to the same `[0, 1]` scale before it leaves the scorer. Because they share a scale, they can be combined, thresholded, and compared without special-casing. The `ScoreOutcome` also carries `labels` (the failure-mode tags, Chapter 10) and a `rationale`, but the normalized score is the load-bearing field.

### The six deterministic scorers

*This is `[code-resident]` in `agon/scoring/non_llm.py`.*

| Scorer | Grades | Passes when |
|---|---|---|
| `exact_match` | `final_answer` vs `expected_answer` | Strings match (whitespace-collapsed; case-insensitive by default) |
| `keyword_containment` | Required/forbidden substrings | All required strings present, no forbidden ones |
| `json_schema` | `final_answer` as JSON vs a schema | Parses as JSON and validates against the case's `json_schema` |
| `citation_check` | `citations` vs expected/allowed sources | Required citations present, correct, and in-scope |
| `rouge_l` | Overlap with a reference answer | ROUGE-L F-measure clears the threshold |
| `semantic_similarity` | Embedding cosine vs reference | Meaning is close enough (needs the `[semantic]` extra) |

A few behaviors worth knowing because they show how a scorer encodes judgment. `keyword_containment` returns a *partial* score — the fraction of required keywords present — and attaches an `incomplete_answer` label when it's below 1.0, or an `instruction_following_failure` label if a *forbidden* string appears. `citation_check` is genuinely compound: it rewards citations being *present* (when required), being *correct* (matching expected sources), and being *in-scope* (drawn only from allowed sources), and it zeroes the score outright and labels `wrong_citation` if the system cites something out of scope. These scorers are not just true/false gates; they carry diagnostic detail about *how* a response fell short. That detail is what feeds failure localization later.

Note also the split by offline-readiness: five of the six run on the bare `uv sync` install. Only `semantic_similarity` sits behind an extra, because it downloads embedding weights — exactly the offline-first packaging discipline from Chapter 5.

### Choosing a deterministic scorer

*The repo lists the scorers but offers no selection guidance — supplied here. `[rationale-only]`*

The repo gives you six tools and no map. Here is the map, keyed to the shape of your ground truth:

| If a correct answer is… | Use | Because |
|---|---|---|
| Exactly one known string | `exact_match` | The criterion is literal equality |
| Defined by must-have / must-not-have phrases | `keyword_containment` | Open phrasing, fixed required content |
| A structured object (JSON) | `json_schema` | You care about shape and types, not prose |
| Grounded in cited sources | `citation_check` | Provenance is part of correctness |
| Close to a reference, wording flexible | `rouge_l` | Lexical overlap is a fair proxy |
| Close in *meaning*, wording very flexible | `semantic_similarity` | Surface overlap would miss paraphrase |

The decision is mostly: *how is "correct" defined for this case?* If correctness is literal, match literally. If it's structural, validate the structure. If it's about meaning rather than words, reach for overlap or embeddings — and notice that as you move down the table you trade determinism and speed for tolerance of variation, which is exactly the tension Chapter 1 said a harness exists to manage. Stop as high in the table as your case allows.

### Hands-on and the test obligation

*This is `[code-resident]` — test patterns and `templates/your-eval/test_scorer.py`.*

Using a scorer is just naming it in a case's `scoring` block with a `pass_threshold`:

```yaml
scoring:
  - {type: keyword_containment, weight: 1.0, pass_threshold: 1.0}
```

Run the dataset and the scorer runs. But there is a standing obligation, mandated by the project's own rules and taught here as a habit: **every scorer ships with boundary tests.** A scorer is a measuring instrument, and an uncalibrated instrument is worse than none because it produces confident wrong numbers. So when you write or modify a scorer, you write tests that pin its behavior at the edges — the empty answer, the exact-threshold case, the forbidden-string case — so that a future change can't silently shift what "pass" means. This is the same instinct as Chapter 1's "evidence over claims," turned on the scorers themselves: a scorer's correctness is asserted by tests, not by trust. Chapter 21 walks the full build-test-register path for a custom scorer; the obligation starts now.

Generalizing: deterministic scorers are universal harness furniture. Inspect calls them `Scorer`s, promptfoo calls them `assert`s, lm-eval calls them `metric`s. The names differ; the idea — a mechanical rule that turns a response into a `[0,1]` measurement — is the same one everywhere.

---

## Chapter 9 — Scoring II: LLM-as-Judge & Calibration

Some things you want to grade cannot be captured by any mechanical rule. Whether an open-ended answer is *faithful* to its sources, whether a response is *safe*, whether an explanation is *good* — these resist exact matching. For them, the harness uses another model as the grader: an **LLM-as-judge**. This chapter covers the judges Agon ships, the discipline that keeps them honest, and the single most important idea in the manual that the repo implements but never teaches: **Cohen's kappa, and why a judge must be calibrated before it is trusted.**

### When a judge is necessary — and its risks

*The motivation for judges is not spelled out in the repo — supplied here. `[rationale-only]`*

Reach for a judge only when the thing you're grading is genuinely open-ended — when there are many correct answers and no mechanical rule separates them from the incorrect ones. "Is this summary faithful to the source?" has no keyword that settles it; a human would have to read both and decide. That is judge territory.

But understand what you're taking on. A judge is itself an AI system, with all the unreliability that implies: it can be inconsistent, it can be biased, it can be confidently wrong, and — most dangerously — it can be wrong in ways that *look* like authoritative grading. Using an unvalidated judge does not remove uncertainty from your evaluation; it relocates the uncertainty one level up, where it is harder to see. You have not grounded your result in a standard. You have substituted one unknown system for another and called the second one "the grader." The rest of this chapter is about not letting that happen.

### The judge-backed scorers and the `JudgeClient`

*This is `[code-resident]` in `agon/scoring/llm.py` and `agon/scoring/judge.py`.*

Agon ships five judge-backed scorers:

| Scorer | Asks the judge |
|---|---|
| `rubric` | Score this answer against a rubric (returns an integer, normalized) |
| `safety` | Is this answer safe and policy-compliant? |
| `faithfulness` | Are the answer's atomic claims supported by the context? |
| `context_precision` | Are the retrieved documents actually relevant to the question? |
| `answer_relevance` | How directly does the answer address the question? |

Every one of them routes its model calls through a single gateway, the **`JudgeClient`**, and the design of that gateway is where the discipline lives. The `JudgeClient` runs the judge at **`temperature=0` with a fixed seed**, so the grader is as deterministic as the provider allows — you do not want your grades to wobble run to run for no reason. It demands **strict JSON output** and parses it, **retrying exactly once** on a parse failure, and if the judge still returns garbage it raises a `JudgeParseError` rather than silently scoring zero. That last choice matters: a judge that emits unparseable output is a *broken instrument*, and the harness surfaces that as an error to investigate, not as a quiet failing grade that would corrupt your numbers. (Three of these scorers — `faithfulness`, `context_precision`, `answer_relevance` — measure retrieval quality and are deliberately kept out of the generation score; Chapter 10 explains the exclusion and Chapter 14 covers retrieval evaluation properly.)

### A judge is an evaluated component, not a ground truth

*This is `[code-resident]` — stated in the judge docstring and the README requirement — and is the through-line of the chapter.*

Here is the principle that governs everything: **the judge is itself a component under evaluation.** It is not an oracle whose verdicts you accept because it's a model. It is an instrument, and like any instrument its readings are worthless until you've checked them against a known standard. The harness enforces this — it will not let you treat a judge as trustworthy until you have *measured* its agreement with human judgment and it has cleared a bar. That measurement is calibration.

### What Cohen's kappa is, and why chance-correction matters

*The code computes kappa but never teaches the concept — supplied here, for a non-CS reader. This is the manual's Principle-1 exemplar. `[rationale-only]`*

To calibrate a judge you compare its verdicts against a set of cases a human has already labeled, and you need a *number* that says how well they agree. The obvious number is **raw accuracy**: the fraction of cases where the judge and the human gave the same verdict. Build it up and you'll see why it's not enough.

Suppose you have 100 labeled cases and the judge agrees with the human on 90 of them. Ninety percent agreement — sounds excellent. But now suppose 90 of those 100 cases were "pass" anyway. A judge that did no work at all — that simply said "pass" every single time — would also score 90% agreement, purely because "pass" is common. The accuracy number can't tell a real grader apart from a broken one that got lucky on the base rate. That is the flaw: **raw agreement doesn't account for the agreement you'd expect from chance alone.**

**Cohen's kappa** fixes exactly this. It is a measure of agreement that *subtracts out* the agreement you'd expect by chance. The construction, in three steps the code follows directly:

1. **Observed agreement (`po`)** — the fraction of cases where judge and human actually agree. (This is just raw accuracy.)
2. **Chance agreement (`pe`)** — the fraction they'd be *expected* to agree on if each were just guessing at their own base rate. If both call "pass" 90% of the time, they'd agree by luck a lot.
3. **Kappa** — how much of the *available room above chance* the judge actually captured:

   κ = (po − pe) / (1 − pe)

Read that formula as a ratio. The denominator `1 − pe` is all the agreement that *wasn't* going to happen by chance — the room a real grader has to prove itself. The numerator `po − pe` is how much of that room the judge actually earned. So:

- **κ = 1.0** — perfect agreement beyond chance. The judge tracks the human exactly.
- **κ ≈ 0** — the judge agrees only as often as random chance would predict. *No real signal*, even if raw accuracy looks high. This is the 90%-accuracy-but-useless judge, unmasked.
- **κ < 0** — the judge *systematically disagrees* — it tends to invert the human's verdict. A negative kappa is not just a bad grader; it's an actively misleading one, and the sign tells you so. A judge that reliably flips every human label produces a strongly negative kappa.

That is why the harness measures kappa and not accuracy. Accuracy can be inflated to meaninglessness by an unbalanced base rate; kappa cannot. This is the exemplar the whole manual is built around: the *code* computes kappa correctly, but a reader who has never met the concept needs to be *taught* why chance-correction is the difference between a trustworthy grader and a lucky one. The mechanics being in the repo is not the same as the understanding being in your head.

One more honesty the harness insists on: kappa is reported with a **confidence interval**, not as a bare point. A kappa of 0.85 measured on 25 cases might really lie anywhere in a wide band, because 25 cases is a small sample. Reporting the interval keeps you from over-trusting a good-looking number that a few cases could have swung — the same statistical honesty Chapter 12 develops in full.

### Calibrating a judge: `agon calibrate` and the gate

*This is `[code-resident]` in `agon/calibrate/runner.py` and `agon/cli/app.py`.*

The calibration workflow is one command run against a YAML file of human-labeled cases:

```bash
uv run agon calibrate examples/calibration/labeled.yaml \
    --judge-model openai/gpt-4o --min-kappa 0.6
```

The harness runs the judge over every labeled case, compares its verdicts to the human labels, computes kappa with its interval, and prints a verdict in this form (numbers illustrative — unlike every other output in this part, this one can't be reproduced offline, for the reason the next section explains):

```
calibration [safety] n=25 accuracy=0.88 kappa=0.71 [0.42, 0.98] (min 0.6) -> PASS
```

The `--min-kappa` flag is the **gate**: a judge whose kappa clears the floor passes (exit `0`) and may be trusted downstream; a judge that falls short fails (exit `1`) and is not certified — and any evaluation that rested on it is not certified either. The default floor is **0.6**, which corresponds to "substantial" agreement on the Landis–Koch scale the field commonly uses. The decision this output forces: *if it says FAIL, do not use this judge* — fix the rubric, pick a better judge model, or fall back to a deterministic scorer, but do not ship grades from an instrument that failed its calibration.

### The honest boundary: calibration cannot run offline

*This is `[code-resident]` — the mock judge raises `JudgeParseError`, and the CLI says so.*

There is one place the offline-first promise genuinely stops, and the harness is honest about it. **Calibration cannot run on the mock.** Try it with the offline `mockllm` judge and you get a deliberate abort:

```
[abort] judge 'mockllm/model' returned unparseable output - calibration needs a
real judge model (e.g. --judge-model openai/gpt-4o).
```

This is not a defect; it is the nature of the problem. The mock returns canned output, not real judgments, so there is nothing meaningful to calibrate. More fundamentally, calibration measures whether the judge tracks *human* judgment — and you cannot simulate the human standard you are calibrating against. The thing doing the grading has to be graded by reality. An honest harness names that boundary and stops; a dishonest one would fill it with invented numbers. Calibration needs two things the offline path can't supply: a real judge model and real human labels.

For a T&E reader, this whole chapter is one familiar idea in new clothing: **you do not trust an instrument until it has been calibrated against a known standard.** The judge is an instrument. Kappa is the calibration. `--min-kappa` is the acceptance limit. And just as in the lab, the calibration is only as good as the reference standard — here, the human labels — which is why that one step cannot be faked offline.

---

## Chapter 10 — Scoring III: Composite Scoring, Categories & Risk

A single case often carries several scorers. This chapter is about the roll-up: how many scorer outputs become one pass/fail for the case, and one set of category and risk breakdowns for the run — without letting the aggregation hide anything. This is "no single-number obsession" (Chapter 1) turned into arithmetic.

### The composite score, and the pass rule that is *not* the composite

*This is `[code-resident]` in `agon/scoring/composite.py`.*

When a case has multiple scorers, the harness computes a **composite score** — a weighted average of the scorers' normalized scores, using the `weight` on each `ScoringSpec`. That gives you one number summarizing how the case did overall.

But here is the subtlety that trips people up, and it's important: **the composite score is not what decides whether the case passes.** A case passes if and only if **every required scorer independently meets its own `pass_threshold`.** The pass rule is an AND across scorers, not a threshold on the average. The reason is exactly the anti-aggregation argument from Chapter 1: if passing were "the weighted average clears a bar," a strong score on an easy scorer could drag a failing scorer up over the line, and the failure would vanish into the average. The AND rule forbids that. A case with a perfect keyword score and a failed citation check does not pass on a 0.5 average — it fails, because the citation scorer didn't meet its threshold. The composite is reported as a summary; the *gate* is the conjunction.

Two modifiers refine this. A scorer marked **`advisory`** is reported but does not gate — it informs without being able to fail the case, for metrics you want visible but not decisive. And `pass_threshold` defaults to `0.5`, except for `safety` scorers, where the schema *forces* it to `1.0`: safety is binary-critical, so a safety scorer cannot pass on anything less than a perfect score. You cannot even write a case that lets a partial safety result through; the schema rejects it.

### Failure labels, and why safety labels always surface

*This is `[code-resident]` in `composite.py`.*

Each scorer can attach **failure labels** — `missing_citation`, `format_failure`, `unsafe_answer`, and so on — naming *what kind* of failure occurred. The composite collects these into the case's `detected_failure_labels`, which is what later powers failure localization (Chapter 13): you don't just learn that cases failed, you learn what kinds of failures dominate.

There's a filtering rule with one deliberate exception. A case can declare a `failure_labels` allow-list, and by default only labels on that list are kept — a way to keep a case's reporting focused on the failure modes it was written to catch. **But safety labels always surface, regardless of the allow-list.** The four safety labels (`unsafe_answer`, `over_refusal`, `under_refusal`, `policy_violation`) can never be filtered out by a case's allow-list. The reasoning is non-negotiable: a safety failure is exactly the kind of thing that must never be suppressed by a reporting convention, even an innocent one. The harness refuses to let a case's own configuration hide a safety problem.

### The seven categories, tracked separately

*This is `[code-resident]` — the README, the essay, and the per-category aggregation — with the open question supplied. `[rationale-only]` for the justification.*

At the run level, the harness reports pass rates broken out by the **seven evaluation categories** — Functional Correctness, Tool Use, Planning, State Management, Robustness, Reliability, Safety — and never collapses them into one headline. You saw this in the quickstart report: an 85% overall that, broken out, revealed `structured_output` at 50% and `robustness` at 66.7% hiding beneath categories scoring 100%. The aggregate is a hiding place; the per-category breakdown is the light. This is the most direct expression of "no single-number obsession" — the categories exist precisely so the one number can't be the whole story.

Two honest caveats the repo doesn't state. First, the seven categories are a deliberate taxonomy, not a proof: the repo lists them and tracks them, but never argues that they're *exhaustive* or *minimal*. They are a well-chosen working set covering the ways agentic systems are known to fail, and you should treat them as a coverage checklist rather than a closed ontology. Second, `category` on a case is a free-form string — nothing forces it to be one of the seven. The seven are the conceptual frame; your cases can carry finer-grained category strings (`rag_factuality`, `structured_output`) that *roll up* to them. When your domain has a failure mode that fits none of the seven, that's a signal to add a category and, often, a custom scorer (Chapter 21) — the taxonomy is meant to extend.

### Flake handling: epochs and the reducer

*This is `[code-resident]` in `composite.py` and `RunConfig`.*

Because the SUT is stochastic (the T&E reader's adjustment from Part I), the same case can pass once and fail the next time. To measure *reliability* rather than luck, the harness can run each case multiple times — **`epochs`** — and combine the repetitions with a **flake rule**:

| `flake_rule` | A case passes if… | Use for |
|---|---|---|
| `all` (default) | *every* repetition passes | High-stakes cases — reliability means always |
| `any` | *at least one* repetition passes | Measuring best-case capability |
| `majority` | *more than half* pass | A tolerance-for-occasional-miss middle ground |

The default is `all`, and that default encodes a value: for a case that matters, "reliable" means it passes every time, not most times. A case that passes on three of five epochs is not a reliable pass — it's a flaky one, and under the default rule the harness reports it as a failure, which is the honest reading. You loosen to `any` or `majority` only when the case's purpose genuinely tolerates occasional misses. This is where "Reliability" stops being a category name and becomes a measured property.

### A forward pointer: retrieval is excluded on purpose

*This is `[code-resident]` in `composite.py`; full treatment in Chapter 14.*

One last rule belongs here even though its full payoff is later. The three retrieval scorers (`faithfulness`, `context_precision`, `answer_relevance`) are **deliberately excluded from the generation composite.** They're still computed, still reported, and still gate pass/fail — but they do not contribute to the single generation-quality number. This is the "separate concerns the system blurs" commitment from Chapter 1, enforced in code: retrieval quality and answer quality are different failure modes with different fixes, so a strong retriever is not allowed to inflate a weak generator's score, or vice versa. Chapter 14 measures retrieval properly; here, just note that the composite already knows to keep the two apart.

---

## Chapter 11 — Reading Results: Reports, Recommendations & Exit Codes

A run is only as useful as the decision you can make from it. This chapter is where everything in Part II converges: the run is done, the scores are in, and now you have to translate the output into an action. It is the load-bearing interpretation chapter of the core loop, so it ends not with a field reference but with a triage walkthrough — what you actually *do* when the harness says INVESTIGATE.

### Three report formats, three audiences

*This is `[code-resident]` in `agon/reporting/generator.py`.*

Every run writes three reports into `reports/`, each for a different consumer:

| File | Format | Audience |
|---|---|---|
| `<run_id>.report.md` | Markdown | A human reading the result |
| `<run_id>.report.json` | JSON | A program or dashboard ingesting the result |
| `<run_id>.report.junit.xml` | JUnit-XML | A CI system that already speaks the test-result dialect |

Same data, three shapes. The JUnit-XML one is a nice piece of pragmatism: CI systems already know how to display JUnit results — pass/fail counts, which "tests" failed — so emitting that format means an Agon run shows up in your existing CI dashboard with no custom integration. The harness meets the tooling where it already is.

### Reading the Markdown report

*This is the real output of the offline quickstart run, copied verbatim.*

Here is an actual report — the `85% INVESTIGATE` run from Chapter 5, lightly condensed (the cost/usage section is omitted and the by-risk lines are wrapped onto one; everything else is as the harness wrote it):

```markdown
# Agon Eval Report — rag_smoke_suite

| Field | Value |
|---|---|
| Run ID | `4oXbsywF8eUvuLm8m3SwZm` |
| System version | quickstart_v1 |
| Model | mockllm/model |
| Dataset version | `ceb3f6f5f73e` |
| Overall pass rate | **85.0%** [64.0%, 94.8%] (17/20) |
| Errors | 0 |
| Recommendation | **INVESTIGATE** |

> Small sample (n=20 < 30): treat pass rates and intervals with caution.

## Pass rate by category
- classification: 100.0%
- rag_factuality: 88.9%
- robustness: 66.7%
- structured_output: 50.0%
- summarization: 100.0%

## Pass rate by risk
- high: 66.7%   low: 100.0%   medium: 85.7%

## Top failure modes
- format_failure: 1
- missing_citation: 1

## Failed cases
| Test | Category | Risk | Composite | Failure labels |
|---|---|---|---|---|
| robust_016 | robustness | high | 0.00 |  |
| format_017 | structured_output | medium | 0.00 | format_failure |
| rag_020 | rag_factuality | high | 0.00 | missing_citation |
```

Walk it the way you'd actually read it. The headline — **85.0% [64.0%, 94.8%] (17/20)** — is a pass rate *with error bars*: the bracketed range is the Wilson confidence interval (Chapter 12), and its width tells you how much to trust the point estimate. The **small-sample note** warns you that at n=20 a single case swings the rate five points. Then the breakdowns do the localizing for you: the 85% headline dissolves into `structured_output` at 50% and `robustness` at 66.7%, with the strong categories revealed as the ones carrying the average. The **top failure modes** name the dominant problems by kind, and the **failed cases** table drops you to the individual cases — with their category, risk, and labels — ready for the drill in Chapter 13. Every section is an instrument for narrowing "something's wrong" toward "*this* is wrong."

### The recommendation engine

*This is `[code-resident]` in `generator.py` (`recommend()`).*

The harness condenses all of that into one of three recommendations, by a rule you should know exactly, because it's the logic behind the gate:

1. **Any safety failure on a `critical`-risk case → FAIL**, unconditionally. This override comes *first* and ignores the overall pass rate entirely. A single critical-safety miss sinks the run even if everything else is perfect — the asymmetric-cost principle, enforced.
2. Otherwise, **if a regression was detected** (against a baseline, Chapter 13): INVESTIGATE if the pass rate is still respectable (≥ the investigate threshold), else FAIL.
3. Otherwise, by pass rate: **≥ 0.90 → PASS**, **≥ 0.80 → INVESTIGATE**, **below → FAIL**. (Those two thresholds are configurable; 0.90 and 0.80 are the defaults.)

So INVESTIGATE is the honest middle: good enough not to be a clear failure, not good enough to wave through. The quickstart run landed there — 85% sits between 0.80 and 0.90, with no critical-safety miss and no regression.

### Exit codes: the recommendation is three-valued, the gate is binary

*This is `[code-resident]` in `cli/app.py`.*

Now the nuance flagged back in Chapter 5, stated precisely because it's the crux of using Agon in CI. The recommendation has three values, but the **exit code has two outcomes that matter for a gate**:

- Exit **`0`** only when the recommendation is **PASS and no regression** fired.
- Exit **`1`** for **FAIL, INVESTIGATE, or a detected regression** — anything short of a clean pass.
- Exit **`2`** for an abort (the run never reached a verdict).

The design decision worth absorbing: **INVESTIGATE exits 1, not 0.** It does not pass the gate. This is deliberate and it is the right call — "INVESTIGATE" means a human needs to look, and a release gate that let "needs a human" through automatically would defeat its own purpose. In CI, an Agon run breaks the build on anything that isn't a clean PASS, which forces the INVESTIGATE to a person instead of letting it slip by under schedule pressure. For a T&E reader: the recommendation is the *finding*, the exit code is the *gate decision*, and the gate is conservative on purpose — it fails closed.

### Regenerating without re-running

*This is `[code-resident]` — the `agon report` command.*

Because the run's results live in an immutable log, you can regenerate the reports for a past run without paying to run it again:

```bash
uv run agon report <run_id>
```

Useful when you want the report in a fresh location, or want to re-render it against a baseline you didn't have at run time. The underlying run is never re-executed — it's read from its stored log — which keeps the report cheap and the original result immutable.

### How to *act* on an INVESTIGATE — a day in the life of triage

*The interpretive/triage narrative is not in the repo — supplied here. This is the Principle-2 load-bearing piece of Part II. `[rationale-only]`*

A field reference tells you what INVESTIGATE *is*. It doesn't tell you what to *do* when you see it, and that's the skill that separates running the harness from operating it. Here is the actual sequence, using the quickstart run above.

**Step 1 — Read the gate, not the headline.** The run exited `1` and recommends INVESTIGATE. So the first decision is already made for you: *this does not ship as-is.* You are not deciding whether to act; you're deciding where to look. Resist the pull of "85% is pretty good" — the harness already told you 85% isn't the bar.

**Step 2 — Find where the failure concentrates.** Skip the overall number and go straight to the breakdowns. `structured_output: 50.0%` and `robustness: 66.7%` are dragging an otherwise-strong run. That's your search narrowed from twenty cases to a handful, before you've opened a single trace.

**Step 3 — Weigh by risk.** Cross the category view with the risk view: `high: 66.7%`. Two of the three failures — `robust_016` and `rag_020` — are `high`-risk. A `medium`-risk `format_failure` and a `high`-risk `missing_citation` are not equal claims on your attention. Triage the high-risk failures first; they're the ones closest to a gate-sinking problem.

**Step 4 — Read the failure labels.** The failed-cases table hands you the *kind* of each failure: `rag_020` is a `missing_citation`, `format_017` is a `format_failure`. You now have a hypothesis about cause before you've looked at the response — a citation that didn't get emitted, an output that didn't parse as JSON.

**Step 5 — Drop to the case and its trace.** Take `rag_020`. Open its trace (`uv run inspect view --log-dir logs`) and read what the system actually produced — the exact response, the exact scoring decision. Now you can confirm the hypothesis: did it answer well but omit the citation, or did it miss the substance entirely? The label pointed you here; the trace tells you the truth.

**Step 6 — Decide, and close the loop.** Either the failure is real (fix the system) or the *case* is wrong (fix the case — a too-strict threshold, a bad expectation). If it's a real failure, fix it — and then, per the "failure is data" rule, make sure a case exists that will catch this exact failure if it ever returns. That last move is what turns this triage from a one-time cleanup into a permanent guard, and it's the bridge into Chapter 13, where failure localization and regression tracking get the full treatment.

That sequence — gate, category, risk, label, trace, decide-and-guard — is the interpretation-first promise delivered end to end. The harness didn't just hand you a number. At every step it handed you the next question, and the last step handed you back a stronger suite. That is what it means to read a result as a decision.

---

## End of Part II — what to review

Part II covered the full operating loop: install and first run (Ch 5), the case schema (Ch 6), the SUT contract and adapters (Ch 7), deterministic scorers (Ch 8), judges and calibration (Ch 9), composite scoring with categories and risk (Ch 10), and reading results as decisions (Ch 11). Every command and every output shown was run offline against the repo during drafting.

Specific calibration points I'd value a verdict on, since these set the pattern for the operational chapters in Parts III–VI:

- **Code/command density.** Part II carries real YAML, Python, and verbatim CLI output where Part I carried mostly prose and tables. Right balance for the hands-on chapters, or do you want more annotation per listing / fewer listings?
- **The two big "subtle but load-bearing" beats** — the pass rule being an AND across scorers rather than a composite threshold (Ch 10), and INVESTIGATE exiting 1 (Ch 11). These are the kind of thing the repo embodies but never flags. Is that the right level of emphasis, or too much weight on edge cases?
- **The Cohen's-kappa teaching (Ch 9).** This is the manual's designated Principle-1 exemplar — the deepest "teach it, don't cite it" passage so far. Is the build-up (raw accuracy → its flaw → chance-correction → the formula as a ratio → negative kappa) the right depth for the no-CS reader, or should it go deeper / lighter?
- **Triage walkthrough (Ch 11).** The six-step "day in the life of an INVESTIGATE" is the Principle-2 payoff for Part II. Does it read as genuinely actionable, or still too abstract?

**Figure opportunities for this part** (none commissioned yet — flagging for your call before I draw them in the Part I visual language): a scorer-to-composite-to-pass/fail flow for Ch 10, and a recommendation-and-exit-code decision tree for Ch 11. Both would earn their space; I held off pending your sign-off on the Part I figure style.

On your sign-off, I proceed to Part III (Measuring Honestly — statistical honesty and failure localization, Ch 12–13), where the Wilson interval and the localization drill get the full treatment, including the third required figure.
