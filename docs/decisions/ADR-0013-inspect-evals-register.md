# ADR-0013: inspect_evals Contribution via the Register (gait-triage)

**Status:** Accepted * **Date:** 2026-06-07 * **Milestone:** Phase 3 (inspect_evals contribution)

## Context
The Phase-3 roadmap calls for an open-source contribution to `inspect_evals`. On investigation,
`inspect_evals` no longer accepts new eval *code* submissions ("We no longer accept code submissions
for new eval implementations"); new evals are added through the **Inspect Evals Register**, which
catalogs evals hosted in the contributor's own repository (a `register/<name>/eval.yaml` pointing at a
pinned public commit). Bug-fixes to existing evals still use normal PRs.

## Decision
Contribute via the **Register**, packaging our gait-triage regulated-domain eval as a native,
installable Inspect `@task` in this repo and submitting an `eval.yaml`. Rationale: it is the current
accepted path, it showcases our own work rather than donating code into another tree, and gait-triage
ties directly to the methodology essay's "asymmetric" principle.

## Consequences
- The eval is re-expressed natively: `agon/evals/gait_triage/` with a `@task`, a native `@scorer`
  reusing `classify_route`, and the binary-critical rule as a custom Inspect `@metric`
  (`critical_safety_gate`) -- since Inspect has no "release recommendation" concept.
- The repository is made **public** (after a clean full-history secrets scan) so the Register can
  access it; the eval.yaml pins a commit on `main`.
- The dataset stays synthetic; the Register imposes no published-baseline requirement, and the eval
  is described honestly as a synthetic, non-diagnostic worked example.
- The existing `examples/gait_triage/` harness path is unchanged except for importing the routing
  logic from its new home.
