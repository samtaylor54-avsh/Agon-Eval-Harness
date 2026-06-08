<!--
  STYLING NOTE (for the eventual .docx build — not part of the body text):
  General style guide (Steel Blue / Charcoal / Amber, Segoe UI 11pt body) governs everything here,
  with ONE deliberate override: the full heading hierarchy (H1–H4) is rendered in Teal-Blue #0F4761.
  No AVSH branding, no AVSH running header/footer — this is a Learning artifact about Agon.
  Markdown cannot carry heading color; apply #0F4761 to all heading styles when this is typeset.
  Output is verbatim from offline runs against the repo during drafting. The appendices are
  reference back-matter for the whole manual; every entry is verified against source.
-->

# The Agon Eval Harness — A Practitioner's Manual
## Part VI — Extending & Mastery · and Back Matter (Appendices A–E)

| | |
|---|---|
| **Document code** | AGON-TM-001 |
| **Part** | VI — Extending & Mastery (Chapters 21–24) + Appendices A–E |
| **Version** | 0.1 — *draft for review* |
| **Date** | 2026-06-08 |
| **Author** | Samuel R. Taylor |
| **Status** | Draft. Final batch — completes the manuscript. Follows Parts I–V. |

---

### About this part

This is the last batch, and it closes the arc the manual has been building since Chapter 1. Part VI is about *ownership*: making the harness yours (Ch 21), making the suite grow itself (Ch 22), running the whole loop end to end in one worked project (Ch 23), and — the payoff of the manual's second goal — using everything you've learned to operate *any* harness, not just this one (Ch 24). Then the back matter: five reference appendices you'll return to long after the chapters are read.

By the end of Chapter 24 you should be able to do the four things this manual set out to teach: operate Agon across its use cases, operate any standard eval harness, articulate the discipline, and localize failures so they're fixed and kept fixed. The appendices are there so you never have to hunt through the prose for a flag, a scorer's parameters, a schema field, or a definition.

As throughout: every command and output shown was run offline against the repository while drafting. Tags mark **`[code-resident]`** versus **`[rationale-only]`**. Results-bearing sections end by telling you what to *do*.

---

# PART VI — EXTENDING & MASTERY

---

## Chapter 21 — Extending Agon: Plugins, Custom Scorers & SUT Adapters

Sooner or later your domain will need something the built-in harness doesn't ship — a scorer for a failure mode no generic rule captures, an adapter for a system shaped unlike any of the four. This chapter is about doing that *without forking the harness*. Agon has exactly three places you're meant to extend, they're a stable public contract, and extending them is a small, bounded task by design.

### The three extension surfaces

*This is `[code-resident]` in ADR-0008 and `docs/extending.md`.*

Agon commits to three — and only three — stable extension points. Keeping the surface small is itself the design: a narrow, documented contract is one future versions can extend rather than break, and one you can learn in a sitting.

| Surface | What you write | The contract |
|---|---|---|
| **Dataset** | Your cases | The YAML `test_cases` schema (`AgonCase` / `ScoringSpec` / `ExpectedBehavior`) — Chapter 6 |
| **Scorer** | Your grading rule | The `AgonScorer` protocol + `@register`, returning a normalized `ScoreOutcome` — Chapter 8 |
| **SUT adapter** | Your system's connection | The `callable` solver: an async `(SUTRequest) -> SUTResponse` — Chapter 7 |

You've already met all three as a *user*; this chapter is about authoring them. The three surfaces are exactly the first three of the four universal parts from Chapter 3 (cases, adapter, scorers) — the decision layer is the harness's job, not yours to extend. Extending Agon means supplying your half of the contract; the harness supplies the rest.

### Writing a custom scorer, and loading it with `--plugin`

*This is `[code-resident]` in `agon/scoring/plugins.py` and ADR-0008.*

A custom scorer is the most common extension, and it's the same small shape from Chapter 8: a class with a `scorer_type`, a `requires_judge` flag, and an async `score` method that returns a `ScoreOutcome`, decorated with `@register`. The only new piece is how the harness *finds* your scorer when it lives in your code rather than the package.

That's what `--plugin` does. You point `agon run` at your module — a dotted name or a path to a `.py` file — and the harness imports it before building the task, so your scorer's `@register` decorator fires and lands it on the registry:

```bash
uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml
```

The mechanism is deliberately simple: importing a module runs its top-level code, and `@register` *is* top-level code, so importing your file registers your scorer as a side effect. The flag is repeatable (load several), and there's a safety net you met in Chapter 8 — if a dataset names a scorer that no plugin registered, the run aborts with exit `2` and lists what *is* registered. You find out at preflight, not mid-run.

The design choice worth noting (ADR-0008): the harness deliberately did *not* build an `agon new` scaffolding command or auto-discovering plugin system. A `--plugin` flag plus a copy-me template covers the need with zero machinery that could drift from the runtime. When a small explicit surface does the job, the harness prefers it over a clever big one — the same restraint as the build-vs-buy and expose-don't-reinvent lessons before it.

### The worked example: scoring SQL by results, not strings

*This is `[code-resident]` in `examples/text_to_sql/`.*

The text-to-SQL example is the project's thesis in miniature, and it's the best teacher for *why* you'd write a custom scorer. The task: evaluate a system that turns natural-language questions into SQL. The naïve approach would be `exact_match` against a reference query — and it would be *wrong*, because two different SQL strings can return identical results. `SELECT name FROM employees WHERE dept IN ('engineering')` and `SELECT name FROM employees WHERE dept = 'engineering'` are the same answer; a string match would fail the second one falsely.

So the example ships a custom `sql_result_match` scorer that does the right thing: it executes both the candidate and the reference query against a fresh in-memory SQLite database and compares the *result rows*. It's a few dozen lines, runs fully offline (SQLite is in the standard library), and emits meaningful labels — `sql_error` when the candidate query won't run, `wrong_rows` when it runs but returns the wrong data. Here's the real result:

```
text_to_sql_suite: 4/6 passed -> FAIL
```

Four of six — and the interesting part is *which* four. The equivalent-but-differently-written query **passes** (where `exact_match` would have failed it), the genuinely wrong query fails as `wrong_rows`, and the malformed one fails as `sql_error`. That's the whole lesson: **a scorer encodes what "correct" means in your domain, and getting that definition right is the actual work of evaluation.** The harness can't know that SQL correctness is about rows, not strings — but it makes encoding that knowledge a few-dozen-line plugin instead of a fork.

### When to build a new scorer — and when not to

*The decision of when to build versus adapt is not in the repo — supplied here. `[rationale-only]`*

The mechanics are easy; the judgment is knowing when you need them. A decision guide:

- **First, try to compose built-ins.** Many domain needs are a *combination* of existing scorers on one case (a `keyword_containment` plus a `citation_check`), or a built-in with the right `params`. Composition beats authorship — there's nothing new to test.
- **Build a custom scorer when "correct" has a domain definition no built-in captures** — like SQL's row-equivalence, or the gait example's asymmetric-ordinal routing (Chapter 17). The tell is that you keep wanting to say "it's right if…" in terms a generic matcher or even a judge can't express.
- **Prefer a deterministic custom scorer over a judge when you can.** The SQL scorer could have asked a judge "are these queries equivalent?" — but executing the rows is deterministic, free, offline, and needs no calibration (Chapter 9's preference, applied to your own scorers).

The pattern, once you've decided: **build → test → register.** Write the scorer, write its boundary tests, register it with `@register`, and load it with `--plugin`. Which brings us to the obligation.

### The test obligation, and the copy-me skeleton

*This is `[code-resident]` — `templates/your-eval/` and CLAUDE.md.*

A scorer is a measuring instrument, and Chapter 8 stated the rule: **every scorer ships with boundary tests.** This isn't optional discipline you might skip under deadline — it's how the harness keeps its own measurements honest. An untested scorer is an uncalibrated instrument producing confident wrong numbers, which is worse than no scorer at all.

The harness makes this the path of least resistance by shipping a copy-me skeleton at `templates/your-eval/`. It contains exactly the files a new eval needs, already wired together:

```
templates/your-eval/
├── dataset.yaml        # your cases
├── scorer.py           # your custom scorer (with @register)
├── sut_adapter.py      # your callable SUT
├── run.py              # the launcher that ties them together
├── test_scorer.py      # boundary tests — the obligation, pre-stubbed
└── README.md           # how to run it
```

You copy the folder, fill in the four parts (your cases, your scorer, your system, your tests), and run. The presence of `test_scorer.py` *in the template* is the point: the test file isn't an afterthought you might add — it's there from the first copy, so writing the boundary tests is the obvious next step, not a virtuous extra. Chapter 23 walks this exact path end to end.

---

## Chapter 22 — The Continuous Improvement Loop

Chapter 4 promised that the harness *compounds* — that the suite grows stronger than the system it measures. This short chapter is about the machinery of that growth: how a suite gets harder over time, what part of that machinery exists today, what part is roadmap, and why a growing eval suite is ultimately a governance artifact, not just a test asset.

### The regression ratchet — working today

*This is `[code-resident]` — the principle and mechanism, taught in Chapters 4 and 13.*

The part that works right now, and is the heart of continuous improvement, is the **regression ratchet**. You met it as a habit in Chapter 13: when you localize a real failure and fix it, you add the case that catches it — and from then on, `agon compare` flags that case the instant it ever flips back. The ratchet only turns one way. Every failure the system has ever had leaves behind a permanent guard, so the suite accumulates hardness exactly where the system has historically been weak.

This is "failure is data" as an *operating loop* rather than a slogan: discover a failure (in development or production), localize it (the Chapter 13 drill), fix it, and convert it into a standing regression case. The suite that results is not the suite you designed up front — it's that suite plus one guard for every real failure you've ever encountered, which is a strictly better suite than any you could have written in advance, because reality found failure modes you wouldn't have thought to probe.

### Production-trace harvesting — the roadmap, described honestly

*This is `[code-resident]` as *intent* in the README/CLAUDE.md; the directory is not yet populated, so it's described as roadmap. `[rationale-only]` framing.*

There's a second, more ambitious mechanism the project intends but has **not yet built**, and honesty about that boundary matters as much here as anywhere. The vision (stated in the README and CLAUDE.md) is that *production traces continuously harvest new eval cases*: a system running in the field encounters failure modes no synthetic suite anticipated, those real traces get converted into new cases, and the suite grows from how the system actually fails in production — the richest possible source of cases.

The honest current state: **this is intent, not shipped code.** The target repository layout reserves an `evals/production/` directory for harvested cases, but that directory does not exist yet — there is no automated harvesting pipeline today. I'm flagging this plainly because the whole manual operates by the harness's own evidence-over-claims rule, and that rule applies to the manual's account of the harness: the regression ratchet is real and you can use it now; the production-harvest loop is a designed-but-unbuilt roadmap item. What you *can* do today is the manual version — when a production incident reveals a failure, you write the case by hand and add it to the suite, which is the same loop closed with human effort instead of an automated pipeline.

### Governance: the suite as a living accountability artifact

*This framing is not in the repo — supplied here. `[rationale-only]`*

Step back and the growing suite becomes something larger than a test asset. An eval suite that accumulates a permanent guard for every failure a system has ever had is a **living accountability record**. It answers, at any moment, the question a regulator, an auditor, or an acceptance authority actually asks: *what failure modes do you know about, and what proves you've addressed them?* Each regression case is a documented, re-runnable answer — here is a failure we found, here is the case that catches it, here is its current green status proving the fix still holds.

This is why the discipline matters beyond engineering hygiene. A demo proves a system worked once. A *suite* — especially one that has compounded over a system's life — is a standing, evidence-backed account of the system's known weaknesses and the proof that each is guarded. For a T&E reader, this is the difference between a point-in-time test report and a maintained verification baseline: the suite is the artifact you can put in front of an accountability authority and say "this is what we know, this is what we've proven, and it re-runs on demand." A harness that grows this way isn't just getting better at catching bugs. It's building the documented basis for trust — which, as Chapter 2 argued, is the entire point.

---

## Chapter 23 — Putting It Together: A Capstone Project

Reference documentation tells you what each piece does. It can't show you the *rhythm* of using them together — the day-in-the-life of taking a system from nothing to a gated, calibrated, monitored eval. This chapter is that walkthrough: one narrative thread through everything the manual has taught. Where a step runs offline exactly as shown, the output is real; where a step needs a real provider, it's marked.

### Act 1 — Build a small eval and watch it fail

*The walkthrough is authored (`[rationale-only]`); every command is a verified form, and the failing run is real.*

Start where Chapter 21 left off: copy `templates/your-eval/`, and build the smallest real thing — a system under test, a few cases, a scorer that knows your domain. The text-to-SQL example *is* this capstone's Act 1, already built, so we'll use it as the concrete spine. It has a callable SUT (a function that returns SQL), a handful of cases, and the `sql_result_match` custom scorer from Chapter 21. Run it:

```bash
uv run python examples/text_to_sql/run.py
```

```
text_to_sql_suite: 4/6 passed -> FAIL
```

There it is — a real, mixed, *failing* run, exactly the situation you'll face in real work. The harness exited non-zero; the gate says this doesn't ship. Act 1 is done: you have a working eval and an honest FAIL.

### Act 2 — Localize, fix, and watch it pass

*Authored walkthrough applying the Chapter 13 drill. `[rationale-only]`*

Now run the Chapter 13 drill. Open the report and read the failed cases: the failures carry labels — `sql_error` on the malformed query, `wrong_rows` on the genuinely incorrect one. The labels are your hypothesis of cause before you read a single query. Drop into the trace, confirm: one case generated SQL that doesn't run, one generated SQL that runs but answers the wrong question.

Fix the SUT so it generates valid, correct SQL for those cases. Re-run. The previously-failing cases now pass, the suite goes green, and — this is the Chapter 13 close-the-loop step — those exact cases are now permanent regression guards. If a future change reintroduces the `sql_error`, `agon compare` against this run will catch it. You didn't just fix two cases; you ratcheted the suite.

### Act 3 — Add a judge and calibrate it

*Composable from Chapters 9–10; the calibration step needs a real provider, marked. `[code-resident]` mechanics.*

Suppose one of your cases needs open-ended grading no deterministic scorer can do — "is this explanation faithful to the schema?" Add a judge-backed scorer (Chapter 9). But — the discipline the manual keeps returning to — *do not trust the judge until you've calibrated it.* Assemble a small set of human-labeled cases and run:

```bash
uv run agon calibrate my_labeled_set.yaml --judge-model openai/gpt-4o --min-kappa 0.6
```

This step **needs a real judge model** (Chapter 9: the mock can't produce real judgments, and you can't calibrate against a standard you can't simulate). If the judge clears κ ≥ 0.6, it's certified and you may gate on it; if it doesn't, you fix the rubric, pick a better judge, or fall back to a deterministic scorer. Only a calibrated judge joins your suite.

### Act 4 — Wire it into CI and catch a planted regression

*Authored walkthrough; the exit-code and baseline mechanics are `[code-resident]`. `[rationale-only]` for the CI narrative.*

The suite is only a gate if something acts on it automatically. In your CI pipeline, run the eval and let the exit code break the build:

```bash
uv run agon run examples/text_to_sql/dataset.yaml --plugin examples/text_to_sql/sql_scorer.py --display none
# exit 0 → CI proceeds;  exit 1 → CI fails the build
```

Now prove the regression gate works by planting a regression: deliberately break the SUT on one case, run against your last-good run as baseline (`--baseline <good_run_id>`), and watch `regression detected: True` with the broken case in `new failures` and exit `1`. You've now seen the Phase 2 gate from Chapter 4 do its job — catch a system that *used to* pass and now doesn't, automatically, before it ships. (This is the same machinery that produced the real `-85.0pp` regression in Chapter 13.)

### Act 5 — Monitor over time, and close the loop

*Composable from Chapters 19 and 22. `[code-resident]` mechanics.*

Finally, make it a standing watch. Export your runs as traces and chart pass-rate-over-time on a dashboard (Chapter 19):

```bash
uv run agon trace <run_id> --backend console     # offline check; or --backend langsmith
```

Now you're in Phase 2: the dashboard watches the fielded system, and when its pass rate sags because the model drifted, you see it. And when a real production incident reveals a failure mode you never tested, you write that case by hand, add it to the suite (Chapter 22's manual harvest), and the loop closes — the suite is now harder than it was, in exactly the place reality found weak.

That's the whole arc in one project: build, fail, localize, fix, calibrate, gate, monitor, and grow. Every chapter of this manual is one move in that sequence. Run it once end to end on a system you care about and the pieces stop being separate commands and become a practice.

---

## Chapter 24 — Beyond Agon: Operating Any Harness

This is the chapter that cashes out the manual's second goal: that learning Agon makes you fluent in eval harnesses *as a category*, not just this one. You now have a concrete anchor — one harness you understand in depth — and that's exactly what you need to read any other. The skill transfers because, as Chapter 3 argued, the anatomy is universal even when the vocabulary isn't.

### The transferable checklist

*Synthesis across harnesses; not in the repo. `[rationale-only]`*

Strip away everything Agon-specific and five things remain that *every* harness must have. When you meet a new one, find these five, and you understand it:

1. **Cases** — where do the designed challenges live, and what's their format? (Agon: YAML `test_cases`.)
2. **A system adapter** — how does it connect to the thing under test? (Agon: the SUT adapters.)
3. **Scorers** — how does it turn a response into a measurement? (Agon: the scorer registry.)
4. **A decision layer** — how does it turn measurements into a verdict you can act on? (Agon: reports, recommendation, exit codes.)
5. **Reproducibility** — can someone else rerun it and get the same answer? (Agon: offline-first, mock SUT, content-addressed datasets.)

The first four are the universal anatomy from Chapter 3; the fifth is the property from Chapter 1 that separates a harness from an anecdote. A tool missing any of the first four isn't a harness — it's a fragment. A tool missing the fifth produces results you can't trust.

### Reading an unfamiliar harness

*Comparative literacy; only Inspect is in the repo. `[rationale-only]`*

Lay the checklist over the harnesses you're most likely to meet — the same four from Chapter 3's anatomy table, now as an orientation procedure:

| Harness | Cases | Adapter | Scorers | Decision layer |
|---|---|---|---|---|
| **Inspect AI** (Agon's engine) | `Dataset` of `Sample`s | `Solver` + model provider | `Scorer` | `EvalLog` + viewer |
| **lm-eval-harness** | a registered `task` | model wrapper | `metric` functions | aggregated metric output |
| **promptfoo** | `tests` in YAML | `providers` | `assert`s | results table / web view |
| **OpenAI Evals** | a JSONL dataset | completion function | graders / `Eval` classes | run report |

To read any of them: find the cases, find the adapter, find the scorers, find where the verdict comes out. The names will be unfamiliar and the ergonomics will differ, but the questions are the same ones you now answer fluently for Agon. Inspect you already half-know, because Agon is built on it — when you want to go deeper than Agon exposes (custom solvers, the tool sandbox, multi-turn protocols), Inspect's own abstractions are right underneath, and Chapter 3's build-on-not-reinvent decision means they're available, not hidden.

### What to demand of any harness you're asked to trust

*The T&E acceptance lens; your domain contribution. `[rationale-only]`*

Here is where your T&E discipline and this manual converge into a single lens. When someone hands you a harness and a green result and asks you to trust it, you now have the questions to ask — the acceptance criteria for an evaluation apparatus:

- **Is the result reproducible?** Can I rerun it myself and get the same number, without your credentials? If not, it's an anecdote, not evidence.
- **Are the scorers trustworthy?** For any AI-judge scorer — is it *calibrated* against human labels, with a measured agreement, or is it an oracle you're asked to take on faith? (Chapter 9.)
- **Does it report uncertainty?** Is the pass rate a bare number, or does it carry an interval and a small-sample warning? A number without error bars is false precision. (Chapter 12.)
- **Does the aggregate hide anything?** Can I see the breakdown by category and risk, or is everything collapsed into one reassuring percentage? (Chapters 10, 13.)
- **Does it encode the asymmetries that matter?** For a consequential decision — does a safety-critical miss force a fail, or can it be averaged away under a good headline? (Chapter 17.)
- **Is it honest about its own limits?** Does it tell you what it doesn't cover, or does it imply it covers everything? (The "known limitations" discipline throughout.)

These are not Agon questions. They're the questions that separate a measurement you can stake a decision on from benchmark theater dressed in a green dashboard — and they're the acceptance lens a T&E professional already brings to any test apparatus. The deepest thing this manual has to teach is that an AI evaluation harness is a test apparatus like any other, and it earns trust the same way: by being reproducible, calibrated, honest about uncertainty, refusing to hide the failures that matter, and explicit about where it stops. Through *agon* — purposeful opposition, honestly measured — a system becomes more than it was. The harness is how you run the contest. This manual was how to operate it. The discipline is now yours.

---

# BACK MATTER

---

## Appendix A — CLI Reference

*`[code-resident]` — `agon/cli/app.py`. Every command, its arguments, and its exit behavior. Run any command with `--help` for the live signature.*

**Global:** all commands are invoked as `uv run agon <command>`. A `.env` file is loaded at entry so secrets and provider keys are visible to preflight and `doctor`.

**Exit codes (gating commands):** `0` = PASS gate (recommendation PASS and no regression) · `1` = FAIL gate (recommendation FAIL or INVESTIGATE, or a regression detected) · `2` = abort (bad config/dataset, unknown scorer, failed health check, missing provider key).

| Command | Arguments | Key options | Exit |
|---|---|---|---|
| `run` | `<dataset>` | `--config/-c`, `--system-version`, `--model`, `--adapter`, `--epochs`, `--baseline`, `--display plain\|rich\|none`, `--plugin/-p` (repeatable), `--log-dir`, `--report-dir`, + resilience flags | 0/1/2 |
| `resume` | `[run_id]` | `--latest`, `--config/-c`, `--display`, `--plugin/-p`, `--log-dir`, `--report-dir`, + resilience flags | 0/1/2 |
| `compare` | `<current> <baseline>` | `--log-dir` | 0/1 |
| `report` | `<run_id>` | `--baseline`, `--log-dir`, `--report-dir` | (informational) |
| `doctor` | — | `--model`, `--config/-c` | 0 |
| `trace` | `<run_id>` | `--backend console\|langsmith\|otlp`, `--endpoint` (otlp), `--log-dir` · needs `[otel]` | 0/2 |
| `retrieve` | `<corpus> <qrels>` | `--k`, `--retriever bm25\|lancedb\|hybrid`, `--log-dir`, `--report-dir` · needs `[retrieval]` | 0/2 |
| `review` | — | `--run-id`, `--test-id`, `--reviewer` (required); `--notes`, `--override-passed/--override-failed`, `--ambiguous`, `--reviews-dir` | 0 |
| `calibrate` | `<labeled>` | `--judge-model`, `--min-kappa` · needs a real judge model | 0/1/2 |

**Resilience flags** (shared by `run` and `resume`): `--max-retries` (default 5), `--request-timeout`, `--attempt-timeout`, `--retry-on-error`, `--sample-time-limit`, `--fail-on-error` (`true`/`false` or an error-rate `0..1`).

---

## Appendix B — Scorer Reference

*`[code-resident]` — `agon/scoring/*` and the retrieval/example scorers. Reference a scorer in a case's `scoring:` block by its `type`. All return a normalized `[0,1]` score; the case passes iff every required (non-`advisory`) scorer meets its `pass_threshold`.*

**Deterministic scorers** (offline, judge-free — `agon/scoring/non_llm.py`):

| `type` | Grades against | Key params | Failure labels |
|---|---|---|---|
| `exact_match` | `expected.expected_answer` | `case_sensitive` (default false) | — |
| `keyword_containment` | `expected.answer_contains` / `answer_not_contains` | — | `incomplete_answer`, `instruction_following_failure` |
| `json_schema` | `expected.json_schema` | — | `format_failure` |
| `citation_check` | `expected.expected_citations` / `allowed_sources` / `citation_required` | — | `missing_citation`, `wrong_citation` |
| `rouge_l` | `expected.expected_answer` (ROUGE-L F) | — | — |
| `semantic_similarity` | `expected.expected_answer` (embedding cosine) | `model` · needs `[semantic]` | — |

**Judge-backed scorers** (`requires_judge=True` — `agon/scoring/llm.py`). *Retrieval scorers are excluded from the generation composite (Ch 10/14) but still gate.*

| `type` | The judge decides | Notes / labels |
|---|---|---|
| `rubric` | Score against a rubric (integer, normalized) | `params.rubric` (required) |
| `safety` | Is the answer safe? | `pass_threshold` forced to `1.0`; labels `unsafe_answer`, `over_refusal`, `under_refusal`, `policy_violation` |
| `faithfulness` | Are the answer's claims supported by context? | *retrieval*; label `unsupported_claim` |
| `context_precision` | Are retrieved docs relevant (rank-weighted)? | *retrieval*; label `retrieval_miss` |
| `answer_relevance` | How directly does the answer address the question? | *retrieval* |

**Agent scorers** (read the tool-call trajectory — `agon/scoring/agent.py`):

| `type` | Measures | Failure labels |
|---|---|---|
| `tool_use` | Selection · no-forbidden · valid-args · recovery | `tool_omission`, `tool_misuse`, `bad_recovery` |
| `planning` | Did it gather (call tools) before answering? | `poor_reasoning_path` |
| `step_efficiency` | Fraction of non-redundant tool calls | `redundant_tool_call` |

**Adversarial** (`agon/scoring/adversarial.py`): `injection_resistance` — passes iff the answer leaks none of the canary markers in `expected.answer_not_contains`; emits the label in `params.failure_label`. Offline, judge-free.

**Retrieval metrics** (via `agon retrieve`, not case scorers — `agon/retrieval/metrics.py`): `recall@k`, `precision@k`, `hit@k`, `MRR`, `nDCG@k`. Computed natively from ranked doc IDs vs gold qrels.

**Example / plugin scorers** (loaded via `--plugin`, not in the core registry): `sql_result_match` (compares SQL result rows; labels `sql_error`, `wrong_rows`) · `gait_triage_route` (asymmetric-ordinal routing; under-escalation → `unsafe_answer`).

---

## Appendix C — Config & Schema Reference

*`[code-resident]` — `agon/schemas/models.py` and `agon/config/`.*

**Dataset case (`AgonCase`)** — the fields you write in a dataset's `test_cases`:

| Field | Type / default | Notes |
|---|---|---|
| `test_id` | str (required) | `^[a-z0-9_\-]+$`, unique |
| `name` | str (required) | human label |
| `category` | str (required) | free-form; rolls up to the seven categories |
| `input` | `CaseInput` (required) | `user_message` (required), `documents`, `session_id`, `config_overrides` |
| `scoring` | list[`ScoringSpec`] (≥1) | the scorers to apply |
| `expected` | `ExpectedBehavior` | `expected_answer`, `answer_contains`, `answer_not_contains`, `expected_citations`, `citation_required`, `allowed_sources`, `expected_tool_calls`, `forbidden_tools`, `json_schema` |
| `risk_level` | `low\|medium\|high\|critical` (medium) | drives the binary-critical gate |
| `difficulty_level` | `easy\|medium\|hard\|adversarial` | |
| `failure_labels` | list[str] | allow-list (safety labels always surface) |
| `tags` | list[str] | |
| `repetitions` | int? | per-case epoch override |
| `sample_time_limit` | int? | per-case wall-clock cap (s) |

**`ScoringSpec`:** `type` (registered scorer key) · `weight` (default 1.0) · `pass_threshold` (default 0.5; forced 1.0 for `safety`) · `advisory` (default false — reported, doesn't gate) · `params` (dict).

**`AgonDataset`:** `name` · `dataset_version` (SHA-256, computed by the loader) · `test_cases`.

**Run config (`RunConfig`)** — TOML/YAML/JSON, passed with `--config`:

| Field | Default | Notes |
|---|---|---|
| `system_version` | `"unversioned"` | recorded in reports/traces |
| `sut` (`SUTConfig`) | `adapter="mockllm"` | `model`, `temperature=0.0`, `seed=42`, `endpoint_url`, `headers`, `field_map`, `extra` |
| `judge` (`JudgeConfig`) | `model="mockllm/model"` | `temperature=0.0`, `seed=42`, `max_tokens=1024` |
| `epochs` | 1 | repetitions per case |
| `flake_rule` | `"all"` | `all` / `any` / `majority` |
| `max_connections` | 8 | concurrency |
| `resilience` (`ResilienceConfig`) | `max_retries=5` | `request_timeout`, `attempt_timeout`, `retry_on_error`, `sample_time_limit`, `fail_on_error` |
| `pass_threshold` | 0.90 | ≥ → PASS |
| `investigate_threshold` | 0.80 | between → INVESTIGATE; below → FAIL (`investigate ≤ pass` enforced) |
| `baseline_run` | — | regression baseline run_id |
| `log_dir` / `report_dir` | `logs` / `reports` | |

---

## Appendix D — ADR Index

*`[code-resident]` — `docs/decisions/`. The thirteen Architecture Decision Records, as a one-line rationale map. Read the full ADR when you need the *why* behind a behavior.*

| ADR | Decision in one line |
|---|---|
| 0001 | Build on **Inspect AI**, not a hand-rolled runner — adopt the engine, build only the harness-specific parts. |
| 0002 | **LanceDB** default vector store (embedded), pgvector optional; **BM25** offline default retriever; IR metrics implemented natively; hybrid = portable RRF. |
| 0003 | Export observability **post-hoc from the EvalLog**, not via live hooks — deterministic, testable, works on any stored run. |
| 0004 | **Native ReAct** agent is the offline/CI SUT; the **LangGraph bridge** is experimental — same scorers grade either. |
| 0005 | The OWASP adversarial suite is **offline, deterministic, scripted** — it proves the detection harness, not real-model vulnerability. |
| 0006 | Real-provider hardening by **exposing Inspect's resilience knobs** (not reinventing them) + a dated, **advisory** cost layer. |
| 0007 | Statistical rigor via **closed-form, dependency-free** stats — Wilson intervals, two-proportion test, kappa CI; significance informs, never silences the gate. |
| 0008 | Three stable **extension surfaces** (dataset / scorer / SUT adapter) + a `--plugin` loader; a copy-me template, not a generator. |
| 0009 | **Harness-native resume** (re-run only incomplete cases) + a five-category **error taxonomy**. |
| 0010 | **Secrets hardening** — hybrid redaction, preflight, `doctor`; the raw `.eval` log remains un-redacted (known limit). |
| 0011 | **Enrich trace spans** with evaluation outcomes from the digest, so dashboards chart pass-rate/errors/cost directly. |
| 0012 | A worked **regulated-domain** eval (gait-triage) — asymmetric-ordinal scoring, binary-critical gate, the adjacent-not-exact analog. |
| 0013 | Contribute to `inspect_evals` via the **Register** (host-your-own-repo + `eval.yaml`), since code submissions are no longer accepted. |

---

## Appendix E — Glossary

*`[rationale-only]` — plain-language definitions for a reader new to the field. Cross-references point to the chapter that teaches each term.*

| Term | Definition |
|---|---|
| **Advisory scorer** | A scorer that is reported but does not gate pass/fail. (Ch 10) |
| **Canary / marker** | A synthetic string an attack tries to elicit; its appearance in output means the attack landed. (Ch 16) |
| **Cohen's kappa (κ)** | Agreement between two raters, *corrected for chance* — the metric that validates a judge. 1.0 perfect, ~0 no better than chance, <0 systematically inverted. (Ch 9) |
| **Composite score** | The weighted average of a case's scorers. *Reported* as a summary; the *pass* decision is the AND across required scorers, not a threshold on this average. (Ch 10) |
| **Dataset version** | A SHA-256 fingerprint of a dataset's cases — content-addressed provenance for "the same test." (Ch 6) |
| **Epoch** | One repetition of a case; multiple epochs measure reliability under stochasticity. (Ch 10) |
| **Exit code** | The harness's gate output: `0` PASS, `1` FAIL/INVESTIGATE/regression, `2` abort. (Ch 1, 11) |
| **Flake rule** | How epoch repetitions combine: `all` (every rep passes), `any`, or `majority`. (Ch 10) |
| **Gate** | The automated pass/block decision (an exit code) that authorizes or stops a release. Binary, even though the recommendation is three-valued. (Ch 11) |
| **Judge (LLM-as-judge)** | A model used to grade another model's open-ended output — itself an evaluated component, calibrated before trust. (Ch 9) |
| **Matcher** | A deterministic scorer (vs. a judge) — exact, free, offline; preferred whenever it can capture "correct." (Ch 8) |
| **MRR** | Mean Reciprocal Rank — how high the *first* relevant document sits, averaged over queries; a *ranking* metric. (Ch 14) |
| **nDCG@k** | Normalized Discounted Cumulative Gain — graded ranking quality, rewarding relevant docs placed higher. (Ch 14) |
| **OWASP (for agents)** | The Top-10 catalog of agentic-app attacks (prompt injection, goal hijacking, memory poisoning, tool misuse). (Ch 16) |
| **Recall@k** | Of all relevant documents, the fraction retrieved in the top k; a *completeness* metric. (Ch 14) |
| **Recommendation** | The three-valued verdict: PASS / INVESTIGATE / FAIL. (Ch 11) |
| **Reducer** | The function that collapses multiple epochs into one verdict (per the flake rule). (Ch 10) |
| **RRF** | Reciprocal Rank Fusion — the portable method that fuses two retrievers into a hybrid. (Ch 14) |
| **Span** | One timed, attributed operation in a trace; spans nest into a tree. (Ch 19) |
| **SUT** | System Under Test — the bounded thing being evaluated, reached through a normalized contract. (Ch 1, 7) |
| **Scorer** | A rule that turns a response into a normalized `[0,1]` measurement. (Ch 8) |
| **Wilson interval** | A confidence interval for a pass rate that stays honest at small n and at 0%/100% (unlike the naïve normal interval). (Ch 12) |

---

## End of the manuscript — what to review

This final batch completes the draft manuscript: Part VI (extending, the continuous-improvement loop, the capstone, and operating any harness — Ch 21–24) and the five reference appendices (CLI, scorers, config/schema, ADR index, glossary). All four required figures are in place across Parts I–V. Every command and output shown was run offline against the repo during drafting; the appendices are verified against source.

Calibration points I'd value a verdict on:

- **Ch 22's roadmap honesty.** I described the production-trace-harvesting loop as *intent, not shipped* (the `evals/production/` directory genuinely doesn't exist yet) and kept the regression-ratchet as the real, working mechanism. That's the plan's "describe current-state vs roadmap honestly" rule — confirm I drew the line where you want it, neither overclaiming the vision nor underselling what works today.
- **The capstone (Ch 23).** It's an authored narrative anchored on the real text-to-SQL example, with the judge-calibration step honestly marked as needing a real provider. Does it read as a usable end-to-end walkthrough, or would you rather it be a fully-runnable single script the reader can execute verbatim? (I can build that as a new example if you want the capstone to be executable, not just narrated.)
- **Ch 24's "what to demand of any harness" lens.** This is the manual's closing argument and the fullest fusion of the eval discipline with your T&E acceptance instincts. Is it the right note to end on?
- **Appendix depth.** The appendices are reference-dense (tables over prose). Is the level right — enough to be a standing desk reference — or do you want any of them expanded (e.g., per-scorer formulas in App B) or trimmed?

**The whole manuscript is now drafted (front matter + 24 chapters + 5 appendices + 4 figures).** The standing item from every prior batch still holds and is now the gating question for the whole work: none of it has had your verdict on the Part I conventions (voice, depth, tagging, table density, T&E-bridge weight, figure style). A read of Part I — or a pass over any one later chapter you'd treat as representative — is what unlocks either a confident "proceed to .docx production" or a single round of revisions that I'd apply consistently across all six parts before typesetting.
