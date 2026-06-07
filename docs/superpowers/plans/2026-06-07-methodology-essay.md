# Methodology Essay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a publishable, evidence-driven methodology essay — *What We Measure When We Measure an Agentic System* — that argues measurement is an adversarial process and cashes out every claim against a real artifact in this harness.

**Architecture:** A single Markdown essay (`docs/methodology/measuring-agentic-systems.md`), prologue + 7 principle sections + coda + a single "reproduce every claim" footer. Each principle section is drafted to a locked brief that quotes a real, pre-captured offline command output (no invented numbers). README roadmap is updated to check the Phase-3 box and link the essay. A committed Python generator script produces an untracked `.docx` handout in the general-style-guide palette via an ephemeral `uv run --with python-docx` (no permanent dependency added). No changes under `agon/`.

**Tech Stack:** Markdown; the existing `agon` CLI + example scripts (offline, `mockllm`) for evidence; `python-docx` (ephemeral, via `uv run --with`) for the handout.

---

## Evidence ledger (captured 2026-06-07, offline, this branch)

All figures below were produced by running the commands on the offline path. **Quote these exact
numbers.** If a drafting subagent cannot reproduce a figure, it must re-run the command and use the
fresh value, never guess.

**E1 — Adversarial (`uv run python examples/adversarial_quickstart.py`):**
```
owasp_adversarial_suite: 50% of cases safe -> FAIL
OWASP attacks caught: {'prompt_injection_success': 1, 'goal_hijacked': 1, 'memory_poisoned': 1, 'tool_misuse': 1}
```
(8 cases, 2 per OWASP category: 4 attack cases caught, 4 control cases pass -> 50% safe -> FAIL.)

**E2 — Multi-dimensional, mixed report (`uv run python examples/quickstart.py`, report `.md`):**
```
Overall pass rate | 85.0% [64.0%, 94.8%] (17/20)
Recommendation    | INVESTIGATE
Pass rate by category: classification 100.0% | rag_factuality 88.9% | robustness 66.7%
                       | smoke 100.0% | structured_output 50.0% | summarization 100.0%
Pass rate by risk:     high 66.7% | low 100.0% | medium 85.7%
```
(Headline 85% hides structured_output at 50% and high-risk at 66.7% — the single number lies.)

**E3 — Retrieval isolated (`uv run agon retrieve examples/retrieval/corpus.yaml examples/retrieval/qrels.yaml --k 5`):**
```
hr_policy_qrels [bm25]: recall@5=1.000 MRR=0.969 nDCG@5=0.967 hit@5=1.000
```
(Retrieval scored on its own metrics, independent of any generation answer quality.)

**E4 — Asymmetric gate, demo (`uv run python examples/gait_triage/run.py`):**
```
gait_triage_suite: 4/10 passed -> FAIL
  (the CRITICAL under-escalation gait_004 would force FAIL even if every other case passed)
```
**E4b — Asymmetric gate, isolated test (`tests/test_gait_triage.py::test_critical_miss_alone_forces_fail_above_pass_threshold`):**
9/10 pass = 0.9 >= pass_threshold(0.9) would PASS on rate alone; the one CRITICAL under-escalation
carries `unsafe_answer`, and the binary-critical rule forces `recommendation == FAIL`.

**E5 — Calibration (`tests/test_calibrate.py`, `tests/test_stats.py`):**
`cohen_kappa([True,False,True],[True,False,True]) == 1.0`; opposite ratings -> kappa < 0;
`run_calibration(..., min_kappa=0.6)` gates the judge; `kappa_interval(0.85, 0.5, 25)` gives a
Wilson-style CI on kappa. **Note:** a *live* calibration run needs a real judge model + provider key
(it is the one step that legitimately cannot be faked offline) — treat that as itself a methodological
point, not a gap.

**E6 — Statistical, zero-with-interval (`uv run agon run examples/datasets/rag_smoke.yaml --display none`, report `.md`):**
```
Overall pass rate | 0.0% [0.0%, 16.1%] (0/20)
Recommendation    | FAIL
> Small sample (n=20 < 30): treat pass rates and intervals with caution.
```
(A point estimate of 0% still has a Wilson upper bound of 16.1% on n=20.)

**E7 — Reproducible / cost (same rag_smoke report, Cost & usage):**
```
Input tokens 186 | Output tokens 660 | Total tokens 846 | Estimated cost $0.0000 (as of 2026-06-05)
_Offline run (mockllm): synthetic tokens, estimated cost $0.0000._
```
(Exit codes: `agon run` returns 0 PASS / 1 FAIL / 2 abort. Trace export: `uv run agon trace <run_id> --backend console`, needs the `[otel]` extra.)

**E8 — Continuous / recovery (`uv run agon resume --latest --display none`):**
```
nothing to resume: all cases completed in the prior run
```
(5-category error taxonomy: `timeout` / `resource` / `network` / `scorer` / `sample`, surfaced as
`error_count_by_category` in reports. The prior run is the regression baseline on resume.)

---

## File structure

- **Create:** `docs/methodology/measuring-agentic-systems.md` — the essay (source of truth).
- **Create:** `docs/methodology/build_docx.py` — committed generator: Markdown -> styled `.docx`.
- **Produce (untracked):** `docs/Agon_Methodology_Essay.docx` — handout; **not committed** (the repo
  treats `docs/*.docx` as untracked; the generator script is the reproducible, version-controlled part).
- **Modify:** `README.md` — Phase-3 roadmap line (check the box + link).

---

## Drafting conventions (apply to every prose task)

- **Voice:** confident, precise, first-person plural ("we measure"). Publishable register. The *agon*
  metaphor opens each section but never floats free of evidence.
- **No inline verification tics** in the body (no "(reproduce: ...)" tags). All commands live only in
  the footer (Task 11).
- **ASCII fidelity** when quoting CLI output: `-> `, `[0.0%, 16.1%]`, `$0.0000`, `p=0.048` — no
  `±`/`→`/`—` inside quoted console text. Prose may use UTF-8 punctuation.
- **Numbers are sacred:** every figure in prose must match the Evidence ledger verbatim.
- **Word budget per principle section:** ~400-550 words. Prologue ~350-450; coda ~300-400.
- **Commit after each section** with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. **Targeted `git add` only.**

---

### Task 1: Scaffold the essay skeleton

**Files:**
- Create: `docs/methodology/measuring-agentic-systems.md`

- [ ] **Step 1: Write the skeleton** — title, subtitle, a one-paragraph standfirst stating the thesis, and the nine section headings (empty) plus a "Reproduce every claim" heading at the end.

```markdown
# What We Measure When We Measure an Agentic System

*Trust is earned through opposition — notes on evaluation as an adversarial discipline.*

<!-- Standfirst: 2-3 sentences. A demo proves a system can work once; an evaluation proves it
survives being attacked, measured, and re-measured. This essay argues that measuring an agentic
system is an adversarial process, and shows what that looks like in a working harness. -->

## The Challenge: a demo is not an evaluation

## The Opponent: measurement is adversarial

## The Rules I: measurement is multi-dimensional

## The Rules II: measurement is asymmetric

## The Judges: measurement must be calibrated

## The Record I: measurement is statistical

## The Record II: measurement is reproducible

## The Transformation: measurement is continuous

## Through Agon

## Reproduce Every Claim
```

- [ ] **Step 2: Verify** — `git status` shows the new file; headings render (preview or read back).

- [ ] **Step 3: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): scaffold methodology essay skeleton

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Prologue — "The Challenge"

**Files:** Modify `docs/methodology/measuring-agentic-systems.md` (standfirst + "The Challenge").

**Brief (~350-450 words, conceptual — no hard numbers):**
- Open on the gap: a demo answers "can it work?"; an evaluation answers the harder questions — *does
  it reliably work, under what conditions does it fail, how often and how badly, is it improving or
  regressing?* (mirror the README "Problem This Solves" framing, do not copy it verbatim).
- Introduce *agon*: the Greek contest undertaken in pursuit of excellence — purposeful opposition in
  service of improvement, never conflict for its own sake.
- State the thesis plainly: **to measure an agentic system is to oppose it** — you design contests it
  must survive, and what you measure is the structured record of how hard you tried to break it and
  what withstood the attempt.
- Promise the structure: seven principles, each a stage of the contest, each demonstrated in a real
  harness rather than asserted.

- [ ] **Step 1:** Write the standfirst (replace the HTML comment) and the prologue prose.
- [ ] **Step 2: Verify** — reads as a standalone opening; thesis is explicit; 350-450 words; no
  undefined forward references.
- [ ] **Step 3: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): prologue -- a demo is not an evaluation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: "The Opponent" — measurement is adversarial

**Files:** Modify the essay ("The Opponent" section).

**Brief (~400-550 words). Evidence: E1.**
- Claim: you do not measure a system by watching it succeed; you build an opponent and measure what
  survives. Frame as designing the contest, not hoping for a good run.
- Cash out with the OWASP-for-Agents suite: an offline red-team of eight cases, two per failure
  category (prompt injection, goal hijacking, memory poisoning, tool misuse). Quote E1: a scripted
  vulnerable agent is caught on all four attack types
  (`prompt_injection_success`, `goal_hijacked`, `memory_poisoned`, `tool_misuse`), the four control
  cases pass, and the suite reports `50% of cases safe -> FAIL`.
- The deeper move ("failure is data"): a caught attack is not the end — it becomes a permanent case in
  the suite and a regression check, so the same attack can never silently succeed again. The arena
  grows opponents over time.

- [ ] **Step 1: Re-capture evidence** — `uv run python examples/adversarial_quickstart.py`; confirm
  output matches E1 (update figures if the suite changed).
- [ ] **Step 2:** Write the section to brief, quoting the confirmed figures.
- [ ] **Step 3: Verify** — every number matches E1; 400-550 words; section opens on the *agon* stage,
  lands on the evidence.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the opponent -- measurement is adversarial

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: "The Rules I" — measurement is multi-dimensional

**Files:** Modify the essay ("The Rules I" section).

**Brief (~450-550 words). Evidence: E2, E3.**
- Claim: a single pass-rate is a lie. A system has many ways to be right and many to be wrong; collapse
  them into one number and you blind yourself.
- Cash out with E2: a run can report **85.0% [64.0%, 94.8%] (17/20) -> INVESTIGATE**, yet the
  per-category and per-risk breakdown shows `structured_output` at **50.0%** and **high-risk** cases at
  **66.7%**. The headline is reassuring; the breakdown is where the truth is. Name the seven evaluation
  categories the harness tracks distinctly (Functional Correctness, Tool Use, Planning, State
  Management, Robustness, Reliability, Safety) and connect them to this refusal to average everything
  into one figure.
- Cash out separation-of-concerns with E3: retrieval is measured on its **own** axes
  (`recall@5=1.000 MRR=0.969 nDCG@5=0.967 hit@5=1.000`), never folded into answer quality — you cannot
  diagnose a RAG failure if recall and generation share a score.

- [ ] **Step 1: Re-capture** — `uv run python examples/quickstart.py` (read its report `.md`) and
  `uv run agon retrieve examples/retrieval/corpus.yaml examples/retrieval/qrels.yaml --k 5` (needs
  `uv sync --extra retrieval`); confirm E2/E3.
- [ ] **Step 2:** Write the section; quote confirmed figures.
- [ ] **Step 3: Verify** — figures match E2/E3; the seven categories are named; 450-550 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the rules I -- measurement is multi-dimensional

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: "The Rules II" — measurement is asymmetric

**Files:** Modify the essay ("The Rules II" section).

**Brief (~450-550 words). Evidence: E4, E4b.**
- Claim: not all failures cost the same. In a consequential domain, one category of error can be
  disqualifying no matter how good the aggregate looks. Averaging treats a missed escalation like a
  formatting slip; reality does not.
- Cash out with the regulated-domain example (gait-sensor escalation triage, synthetic data): the
  decision is an **escalation recommendation a human acts on, never a diagnosis** (keep this framing —
  non-alarmist, human-in-the-loop). Quote E4b as the sharp version: **9 of 10 cases pass (0.9, at or
  above the 0.9 threshold) and the suite still returns FAIL**, because the single CRITICAL
  under-escalation carries an `unsafe_answer` label and trips a binary-critical gate. Mention the demo
  (E4: `4/10 passed -> FAIL`, with the note that the one CRITICAL miss alone would force FAIL).
- The principle: asymmetric error costs must be **encoded in the scorer and the release gate**, not
  left to a reviewer's judgment after the fact. (DoD-adjacent stakes stay implicit — say "consequential,
  sensor-driven decisions," name no program or domain beyond the eldercare analog.)

- [ ] **Step 1: Re-capture** — `uv run python examples/gait_triage/run.py` (E4) and
  `uv run pytest tests/test_gait_triage.py::test_critical_miss_alone_forces_fail_above_pass_threshold -v`
  (E4b, expect PASS); confirm the 9/10-yet-FAIL behavior.
- [ ] **Step 2:** Write the section; quote confirmed figures; hold the non-diagnostic framing.
- [ ] **Step 3: Verify** — 9/10-yet-FAIL stated correctly; framing is escalation-not-diagnosis; no
  named program/domain; 450-550 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the rules II -- measurement is asymmetric

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: "The Judges" — measurement must be calibrated

**Files:** Modify the essay ("The Judges" section).

**Brief (~400-500 words). Evidence: E5.**
- Claim: when an LLM grades another model's output, the judge is itself a system under evaluation — not
  ground truth. Trusting an unvalidated judge just moves the unmeasured risk one layer up.
- Cash out with E5: the harness validates a judge against held-out human labels before trusting it —
  Cohen's kappa with a confidence interval (`kappa_interval`), gated by `--min-kappa` (e.g. 0.6).
  Perfect agreement scores kappa 1.0; systematically opposite ratings score negative; the gate refuses
  to certify a judge that only agrees with humans at chance.
- The honest note (turn it into a strength): live calibration is the **one** step that cannot run on
  the offline mock path — it needs a real judge model and human labels. That is the point: you cannot
  fake the validation of the thing doing your grading.

- [ ] **Step 1: Re-capture** — `uv run pytest tests/test_calibrate.py tests/test_stats.py -k "kappa" -v`
  (expect PASS); confirm the kappa behaviors in E5.
- [ ] **Step 2:** Write the section; describe the mechanism accurately (kappa, CI, min-kappa gate).
- [ ] **Step 3: Verify** — no invented live kappa number is presented as an offline result; the
  "can't fake the judge" point is made; 400-500 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the judges -- measurement must be calibrated

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: "The Record I" — measurement is statistical

**Files:** Modify the essay ("The Record I" section).

**Brief (~400-500 words). Evidence: E6.**
- Claim: a pass rate is an estimate, not a fact. Report it without an interval and you invite false
  confidence (or false alarm).
- Cash out with E6: a run of **0/20** reports **0.0% [0.0%, 16.1%]** — a point estimate of zero whose
  Wilson upper bound still reaches **16.1%** on twenty cases, with an explicit small-sample warning
  (`n=20 < 30`). Generalize: the harness puts Wilson intervals on pass rates, uses a two-proportion
  significance test to decide whether a regression is real rather than noise, and flags small samples
  so a 1-of-2 swing is not mistaken for a trend.
- The principle: statistics is how you tell a real change from a lucky (or unlucky) draw — the
  difference between measuring and guessing.

- [ ] **Step 1: Re-capture** — `uv run agon run examples/datasets/rag_smoke.yaml --display none`; read
  the report `.md`; confirm `0.0% [0.0%, 16.1%]` and the small-sample note.
- [ ] **Step 2:** Write the section; quote confirmed figures.
- [ ] **Step 3: Verify** — interval and small-sample note match E6; 400-500 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the record I -- measurement is statistical

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: "The Record II" — measurement is reproducible

**Files:** Modify the essay ("The Record II" section).

**Brief (~400-500 words). Evidence: E7.**
- Claim: a result no one else can reproduce is an anecdote, not evidence. The bar is that a reviewer
  clones the repo and runs the harness in under 20 minutes.
- Cash out with E7: the default path is fully offline (`mockllm` — no API key, no model downloads), so
  the same run yields the same report; the offline run prices out at **$0.0000** while still reporting
  real token usage (`186` in / `660` out / `846` total — not a fake "zero tokens"); `agon run` returns
  a deterministic CI exit code (`0` PASS / `1` FAIL / `2` abort) so a regression breaks the build; and
  any run can be exported as OpenTelemetry GenAI spans (`agon trace ... --backend console`) for an
  auditable trace.
- The principle: reproducibility plus tracing turns "trust me" into "run it yourself."

- [ ] **Step 1: Re-capture** — read the rag_smoke report `.md` Cost & usage block; confirm E7 figures.
  (Optionally `uv sync --extra otel && uv run agon trace <run_id> --backend console` to confirm the
  trace path emits spans.)
- [ ] **Step 2:** Write the section; quote confirmed figures; state exit codes correctly.
- [ ] **Step 3: Verify** — cost/token figures match E7; exit-code semantics correct; 400-500 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the record II -- measurement is reproducible

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: "The Transformation" — measurement is continuous

**Files:** Modify the essay ("The Transformation" section).

**Brief (~400-500 words). Evidence: E8.**
- Claim: a one-time evaluation is a snapshot; trust requires a loop. The contest never ends — every
  failure feeds back as a new test, and the suite grows stronger than the system it measures.
- Cash out with E8 and the recovery features: production traces are intended to harvest new eval cases;
  a five-category error taxonomy (`timeout` / `resource` / `network` / `scorer` / `sample`) separates a
  *system* failure from a *harness* failure so a flaky network run is not misread as a regression;
  `agon resume` re-runs only the failed/incomplete cases against the prior run as baseline (quote E8:
  `nothing to resume: all cases completed in the prior run` when a run finished clean).
- Close on the loop: Design -> Evaluate -> Deploy -> Observe -> Learn -> Improve, feeding back into the
  Eval Suite — the arena that compounds.

- [ ] **Step 1: Re-capture** — `uv run agon resume --latest --display none`; confirm E8 message.
- [ ] **Step 2:** Write the section; quote confirmed figures; name the five error categories exactly.
- [ ] **Step 3: Verify** — taxonomy names exact; resume message matches E8; 400-500 words.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): the transformation -- measurement is continuous

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Coda — "Through Agon"

**Files:** Modify the essay ("Through Agon" section).

**Brief (~300-400 words, conceptual):**
- Tie the seven principles back to the thesis: what we measure when we measure an agentic system is the
  structured record of how hard we tried to break it and what survived — adversarially, across many
  dimensions, with asymmetric stakes, a validated judge, honest statistics, reproducible runs, and a
  feedback loop.
- Raise the stakes for the close: as agents move into consequential, regulated, sensor-driven
  decisioning, demo-grade evaluation stops being merely weak and becomes irresponsible. (DoD-adjacent
  framing stays **implicit** — no program names.)
- End on the *agon* note already in the repo's voice: excellence is not the absence of opposition but
  victory through it; through agon, a system becomes more than it was.

- [ ] **Step 1:** Write the coda to brief.
- [ ] **Step 2: Verify** — recalls all seven principles without re-arguing them; stakes raised; no
  named program/domain; 300-400 words.
- [ ] **Step 3: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): coda -- through agon

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: "Reproduce Every Claim" footer

**Files:** Modify the essay ("Reproduce Every Claim" section).

**Brief:** A single compact table mapping each principle to the exact command that reproduces its
evidence. One short intro line: every figure in this essay was produced offline; here is how to
reproduce each. Then the table:

```markdown
| Principle | Claim reproduced | Command |
|---|---|---|
| Adversarial | 4/4 attacks caught, 50% safe -> FAIL | `uv run python examples/adversarial_quickstart.py` |
| Multi-dimensional | 85% headline hides structured_output 50% | `uv run python examples/quickstart.py` |
| Multi-dimensional | retrieval recall@5/MRR/nDCG, isolated | `uv sync --extra retrieval && uv run agon retrieve examples/retrieval/corpus.yaml examples/retrieval/qrels.yaml --k 5` |
| Asymmetric | 9/10 pass yet FAIL on a CRITICAL miss | `uv run pytest tests/test_gait_triage.py -k critical_miss_alone -v` (or `uv run python examples/gait_triage/run.py`) |
| Calibrated | judge validated by Cohen's kappa + min-kappa gate | `uv run pytest tests/test_calibrate.py tests/test_stats.py -k kappa -v` |
| Statistical | 0/20 -> 0.0% [0.0%, 16.1%] + small-sample note | `uv run agon run examples/datasets/rag_smoke.yaml --display none` |
| Reproducible | offline $0.0000, real tokens, CI exit code | `uv run agon run examples/datasets/rag_smoke.yaml --display none` |
| Reproducible | OpenTelemetry trace export | `uv sync --extra otel && uv run agon trace <run_id> --backend console` |
| Continuous | resume only failed/incomplete cases | `uv run agon resume --latest --display none` |
```

- [ ] **Step 1:** Write the intro line + table.
- [ ] **Step 2: Verify** — every command in the table actually ran during drafting; commands are ASCII;
  each row maps to a figure used in the body.
- [ ] **Step 3: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): reproduce-every-claim footer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Full-essay coherence pass

**Files:** Modify `docs/methodology/measuring-agentic-systems.md` (whole-document edit).

- [ ] **Step 1: Read the whole essay end to end.** Check: (a) total length ~3,000-5,000 words
  (`wc -w docs/methodology/measuring-agentic-systems.md`); (b) the *agon* spine is present at section
  openings but never overrides the argument; (c) transitions between principles read as one cumulative
  build, not nine disconnected notes; (d) no inline verification tics in the body; (e) every number in
  the body matches the Evidence ledger and appears in the footer; (f) no undefined forward references;
  (g) standalone-readable without the repo open.
- [ ] **Step 2: Fix any issues inline** (tighten, smooth transitions, trim to budget).
- [ ] **Step 3: Verify** — `wc -w` in range; a fresh read confirms the criteria above.
- [ ] **Step 4: Commit**

```bash
git add docs/methodology/measuring-agentic-systems.md
git commit -m "docs(essay): full coherence pass -- transitions, length, voice

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Wire the essay into the README roadmap

**Files:** Modify `README.md` (Phase-3 roadmap, the methodology-essay line).

- [ ] **Step 1: Read** the current line:

```markdown
- [ ] Published methodology essay on what we measure when we measure an agentic system
```

- [ ] **Step 2: Replace** with a checked, linked line:

```markdown
- [x] **Published methodology essay** — *What We Measure When We Measure an Agentic System*: evaluation as an adversarial discipline, every claim cashed out against the harness ([docs/methodology/measuring-agentic-systems.md](docs/methodology/measuring-agentic-systems.md))
```

- [ ] **Step 3: Verify** — link path is correct; only the one roadmap line changed (`git diff README.md`).
- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): check + link the methodology essay (Phase 3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: `.docx` handout generator

**Files:**
- Create: `docs/methodology/build_docx.py`
- Produce (untracked): `docs/Agon_Methodology_Essay.docx`

**Palette/typography (general style guide):** Body Calibri 11pt, Charcoal `#2D3436`, line spacing 1.15.
H1 18pt bold Steel Blue `#2C3E6B`; H2 14pt bold Charcoal `#2D3436`; H3 12pt bold Charcoal. Tables:
header row Steel Blue `#2C3E6B` background + white bold text, body rows alternate `#FFFFFF` / Warm Grey
`#F5F5F0`. Code/mono: Consolas, background Warm Grey `#F5F5F0`.

- [ ] **Step 1: Write the generator** `docs/methodology/build_docx.py` — a self-contained script that
  reads the essay Markdown and emits the styled `.docx` via `python-docx`. It must: set Normal style to
  Calibri 11pt / charcoal / 1.15 spacing; map `#`/`##`/`###` to the H1/H2/H3 styles above (colored via
  `RGBColor`); render Markdown tables as Word tables with the Steel Blue header + alternating row
  shading (set cell shading via `w:shd` on `tcPr`); render fenced code blocks in Consolas on the warm-
  grey background; handle bold (`**`) and italic (`*`) inline runs. Title block uses the H1 color for
  the title and an italic Medium Grey `#7B8794` subtitle. Output path `docs/Agon_Methodology_Essay.docx`.

- [ ] **Step 2: Generate** (ephemeral dependency — no permanent dep added):

```bash
uv run --with python-docx python docs/methodology/build_docx.py
```
Expected: prints the output path; `docs/Agon_Methodology_Essay.docx` exists and opens with Steel Blue
headings, charcoal body, and a Steel-Blue-header table for the footer.

- [ ] **Step 3: Verify** — open the `.docx`; headings/body/tables/code match the palette; the essay
  content is complete and correctly ordered.

- [ ] **Step 4: Commit the generator only** (the `.docx` stays untracked, like the repo's other docx):

```bash
git add docs/methodology/build_docx.py
git commit -m "docs(essay): committed generator for the styled .docx handout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review (run before handing off to execution)

**Spec coverage:** prologue (T2), 7 principles adversarial/multi-dimensional/asymmetric/calibrated/
statistical/reproducible/continuous (T3-T9), coda (T10), single footer (T11), evidence-driven grounding
(Evidence ledger + per-task re-capture), title+subtitle (T1), markdown source (T1-T12), README link
(T13), `.docx` in general-style-guide palette (T14), DoD-adjacent-implicit (T5, T10), no-`agon`-changes
(none touched), non-diagnostic AVSH framing (T5). All spec sections map to a task.

**Placeholder scan:** evidence figures are captured verbatim in the ledger; commands are exact; palette
hex values are concrete; the only deliberate runtime value is `<run_id>` in the trace command (a real
id substituted at run time). No "TBD"/"handle appropriately".

**Consistency:** section names match between T1 skeleton, per-section tasks, the footer table, and the
README link text; file paths identical across tasks
(`docs/methodology/measuring-agentic-systems.md`, `docs/methodology/build_docx.py`,
`docs/Agon_Methodology_Essay.docx`); the 9/10-yet-FAIL figure is consistent (E4b) wherever cited.
