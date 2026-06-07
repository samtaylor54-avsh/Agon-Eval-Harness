# ADR-0012: Regulated-Domain Harness (Gait-Sensor Escalation Triage)

**Status:** Accepted · **Date:** 2026-06-07 · **Milestone:** Phase 3 M11

## Context

The roadmap calls for a "regulated-domain eval harness (consequential-decision analog; synthetic data
only)." The harness already has the primitives (safety labels, `risk_level`, the binary-critical
gate, custom plugin scorers, cost/traceability). What was missing was a worked example showing them
composed on a high-stakes decision where the two error directions are not equal.

## Decision

Ship a worked, offline example suite: **gait-sensor escalation triage**. A system routes a synthetic
gait-signal summary to `routine` / `notify_caregiver` / `urgent_review` / `defer`.

1. **Adjacent-not-exact analog.** Gait-sensor escalation shares the structure of high-stakes,
   sensor-driven, defer-to-human decisioning (asymmetric error cost, decision under uncertainty,
   human-in-the-loop, auditability) while using only synthetic, non-sensitive data. The transferable
   artifact is the evaluation methodology, not the domain.
2. **Asymmetric-ordinal scoring** (`gait_triage_route`, an example-local `--plugin` scorer, not added
   to the core registry). Under-escalation emits `unsafe_answer` (an existing safety label), so an
   under-escalation on a `risk_level: critical` case forces a release FAIL via the binary-critical
   rule. Over-escalation, over-deferral, missed-defer, and unparseable routes are non-safety faults:
   they fail the case and appear in the taxonomy but never force the gate.
3. **No core changes.** The scorer reuses `case.expected.expected_answer` for the gold route and the
   existing `SAFETY_LABELS` set; nothing in the package is modified.
4. **Non-diagnostic framing.** The output is an escalation recommendation a human acts on, not a
   diagnosis or prediction; case prose is descriptive and non-alarmist (signals relative to the
   resident's own baseline).

## Consequences

- A reviewer can run one offline command and see the harness make a consequential decision, score it
  with the right asymmetry, and block a release on a single dangerous miss.
- The pattern generalizes: swap the dataset and the tier semantics for another consequential domain.

## Known limitations

- **Synthetic, illustrative data** — not a validated clinical or operational instrument.
- **Canned SUT** — demonstrates the scoring/gating, not a real model's routing quality.
- **Example-local scorer** — if asymmetric-ordinal escalation scoring proves broadly useful it could
  later be promoted into `agon.scoring.default_registry` with boundary tests; out of scope here.
