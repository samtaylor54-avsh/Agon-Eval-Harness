# Methodology Essay: *What We Measure When We Measure an Agentic System* — Design Spec (Phase 3)

**Status:** Approved (design) · **Date:** 2026-06-07 · **Milestone:** Phase 3 (methodology essay)
**Branch:** TBD (to be created at plan time, e.g. `phase-3-methodology-essay`)

## Goal & framing

A **publishable methodology essay** that doubles as the intellectual core of Sam's company
submission. It makes one argument — **measurement is an adversarial process** — and cashes out
every claim against a real artifact in this harness. It is the Phase-3 "thesis" item the README
roadmap names: *"Published methodology essay on what we measure when we measure an agentic system."*

The essay is prose, not code. No changes under `agon/`. The deliverable is a Markdown source of
truth in `docs/`, a README link that checks the Phase-3 box, and a formatted `.docx` handout.

### Audience (hybrid)

Written for an **external reader** — the broader AI-engineering community — but lands as the
**submission's centerpiece**. A hiring manager or technical evaluator should read it as proof that
the author knows the evaluation discipline cold; a general AI-eng reader should be able to read it
as a standalone, citable essay without ever opening the repo.

### Thesis

**Measurement as adversarial process** (the *agon* frame): trust is earned through opposition, not
demonstration. An evaluation is a contest you deliberately design to make the system fail; what you
measure is the structured record of how hard you tried to break it and what survived. This ties the
Greek *agon* (purposeful opposition in service of improvement) to Test & Evaluation discipline.

### Grounding rule: evidence over claims, applied to the essay itself

Every section closes on a **concrete, real artifact** from this harness — a scorer's behavior, a
run's pass-rate/CI, the M11 asymmetric gate forcing FAIL, a calibration kappa, a regression call.
No claim floats free of evidence. The numbers cited must be **pulled from actual runs at draft
time**, not invented (see "Evidence-gathering protocol" below).

## Title

- **Primary:** *What We Measure When We Measure an Agentic System*
- **Subtitle:** *Trust is earned through opposition — notes on evaluation as an adversarial discipline*

## Voice & register

- Confident, precise, technically grounded. Publishable register.
- The *agon* metaphor is the **spine** and surfaces at section openings, but never floats free of
  evidence — each section lands on a real artifact.
- First-person plural ("we measure"), matching the title and the repo's voice.
- No defensive verification tics in the body (no inline "you can verify this!" tags). Verification
  lives in **one** quiet footer (see below). Clean prose throughout; the argument stands on its own
  merits before the footer ever appears.

## Structure — prologue + 7 principles + coda

Cumulative argument arc: **demo -> adversarial -> multi-dimensional -> asymmetric -> calibrated ->
statistical -> reproducible -> continuous.** Each principle is an arena stage that closes on a real
harness artifact. Target length **~3,000-5,000 words** (medium long-form, single-sitting read),
roughly ~400-500 words per principle section.

| # | Section (arena stage) | The claim | Evidence cashed out |
|---|---|---|---|
| 0 | **The Challenge** (prologue) | A demo answers "can it work?"; an eval answers "does it *reliably* work, when does it fail, how often/badly, is it regressing?" Demo-grade eval is the problem. *Agon* = purposeful opposition in service of improvement. | README problem framing; favor/reject table; thesis stated |
| 1 | **The Opponent** — measurement is *adversarial* | You don't measure by demonstration; you design a contest to make the system fail. Failure is data: every failure becomes a permanent test case + regression check. | OWASP-for-Agents suite: `examples/adversarial_quickstart.py` — attacks caught / controls pass; safe-rate below threshold -> FAIL; OWASP category labels |
| 2 | **The Rules I** — measurement is *multi-dimensional* | A single pass-rate is a lie. Seven categories tracked distinctly; retrieval isolated from generation (recall@k separate from answer quality). | 7 evaluation categories; composite scorer; isolated `agon retrieve` (recall@k / MRR / nDCG / hit@k) |
| 3 | **The Rules II** — measurement is *asymmetric* | Not all failures are equal; some are categorically disqualifying regardless of aggregate score. Consequential, sensor-driven decisions demand asymmetric error costs. | M11 gait-triage: a CRITICAL under-escalation forces release FAIL even at 90% pass (9/10 = 0.9 >= threshold, yet FAIL via the binary-critical gate); non-diagnostic framing |
| 4 | **The Judges** — measurement must be *calibrated* | An LLM-as-judge is itself an evaluated component, not ground truth — validate against held-out human labels before trusting it. | `agon calibrate`; Cohen's kappa + CI; `--min-kappa` gate |
| 5 | **The Record I** — measurement is *statistical* | Point estimates lie. Report confidence intervals on pass rates, a significance test for regression, small-sample awareness. | Wilson CI on pass rate; two-proportion regression test; small-sample flag |
| 6 | **The Record II** — measurement is *reproducible* | Evidence over claims means a reviewer can clone and run in <20 min, offline-first, with a deterministic CI gate and traceable runs. | mockllm offline path; `agon run` exit-code gate; OpenTelemetry export (`agon trace`); cost/token reporting |
| 7 | **The Transformation** — measurement is *continuous* | Failure feeds back: production harvests new cases, regression locks them in, runs stay operable under error. | 5-category error taxonomy; `agon resume`; regression baseline; the Design->Evaluate->Deploy->Observe->Learn->Improve loop |
| 8 | **Through Agon** (coda) | What we measure = the structured record of how hard we tried to break it and what survived. Stakes rise as agents move into consequential, regulated decisioning. | Ties back to thesis; DoD-adjacent framing kept **implicit and non-specific** |

## The "Reproduce every claim" footer

A single, compact table at the **very end** of the essay mapping each numbered claim/section to the
exact `uv run ...` command that reproduces its evidence. Appears **once**, after the argument has
landed — a confidence signal (the standard artifact/reproducibility section of credible empirical
work), never an inline nag. This is the only place verification commands appear in the essay.

## Deliverables

1. **`docs/methodology/measuring-agentic-systems.md`** — Markdown source of truth.
2. **README roadmap** — check the Phase-3 box (`[ ] Published methodology essay ...` -> `[x] ...`)
   and link to the essay.
3. **`.docx` handout** in `docs/` — formatted with the **general style guide** palette
   (Steel Blue / Charcoal / Amber), *not* AVSH branding (this is not an AVSH artifact). Generated
   from the Markdown.

## Evidence-gathering protocol (so the numbers are real)

This essay's credibility rests on real numbers. At **draft time** (plan/implementation phase, not
now), before writing each evidence sentence:

- Run the relevant offline command and **read the actual report/output** for the figure cited
  (pass rate, CI bounds, caught/total, kappa, recommendation, exit code).
- Prefer figures the reader can reproduce on the offline path (`mockllm`, the example `run.py`
  scripts, `agon run --display none`). Cite the command that produced each figure.
- If a number can drift between runs (e.g. anything stochastic), state it as the deterministic
  offline value and confirm the footer command reproduces it.
- Do **not** invent or round-guess numbers. Every cited figure must trace to a command in the footer.

## Non-goals (YAGNI)

- No new `agon/` code, scorers, or dependencies.
- No formal essay+appendix two-layer split — evidence is inline prose + the single footer.
- No academic citation apparatus / bibliography (it's an engineering essay, not a paper).
- No live-provider runs required to reproduce any cited figure (offline-first).
- The DoD-adjacent angle stays implicit; the essay does not name specific programs or domains.

## Success criteria

- Reads as a standalone, publishable essay without the repo open.
- Every principle section closes on a real, reproducible artifact; every footer command works on the
  offline path.
- ~3,000-5,000 words; single-sitting read; the *agon* spine is present but never overrides the
  argument or the evidence.
- README Phase-3 box checked and linked; `.docx` handout produced in the general-style-guide palette.
- A technical evaluator finishes it convinced the author knows the evaluation discipline in depth.

## Conventions (carried from prior milestones)

- Markdown / `.docx` may be UTF-8; any CLI/example output quoted in the essay stays ASCII-faithful to
  what the cp1252 Windows console actually prints (`-> `, `[0.49, 0.94]`, `p=0.048`).
- Targeted `git add` only (never `git add .` / `-A`); the working tree carries pre-existing untracked
  `.docx`/`reports2/`/banner-PNG noise.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Push / open PR only when Sam asks; Sam merges.
