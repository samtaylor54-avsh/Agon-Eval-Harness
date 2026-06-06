# Statistical Rigor — Design Spec (Phase 3 M6)

**Status:** Approved (design) · **Date:** 2026-06-05 · **Milestone:** Phase 3 M6
**Branch:** `phase-3-m6-statistical-rigor`

## Goal

Replace point-estimate reporting with uncertainty-aware results so a reviewer can tell signal from
noise: **confidence intervals** on pass rates, a **significance test + small-sample awareness** in
regression detection, and a **confidence interval on the judge's Cohen's κ** — all computed
closed-form in pure Python (no new dependency), fully offline.

## Background / current state

The harness reports point estimates everywhere:

- **`agon/analysis/logs.py`** — `overall_pass_rate` / `pass_rate_by_category` / `pass_rate_by_risk`
  are bare `passed / total`, no intervals; sample size is invisible.
- **`agon/analysis/regression.py`** — a fixed `DEFAULT_EPSILON = 0.05`;
  `regression_detected = bool(new_failures) or severe_drop`. A single case flip on a 5-case suite
  trips identically to one on a 500-case suite; no significance, no sample-size context.
- **`agon/calibrate/runner.py`** — hand-rolled `cohen_kappa(human, judge)`; `CalibrationReport`
  reports it as a point estimate; `passed = kappa >= min_kappa`. A borderline κ on small n looks as
  trustworthy as one on large n.

## Decisions locked

1. **No scipy / no new dependency.** Every statistic here is closed-form: the Wilson score interval,
   the two-proportion z-test, and a normal-approximation κ interval. The normal CDF uses stdlib
   `math.erf` (`Φ(z) = 0.5 * (1 + erf(z / sqrt(2)))`). This preserves the offline-first /
   minimal-deps ethos and makes every function unit-testable against textbook values.
2. **Wilson score interval** (not the naive normal/Wald interval) for pass-rate CIs — it is
   well-behaved at small n and at the 0% / 100% boundaries, where Wald breaks.
3. **Regression: augment, never weaken** (the confirmed judgment call). The existing tripwires —
   `new_failures` and high-risk `score_drops` — stay exactly as they are; a real regression must
   never be silenced by "not statistically significant." Significance + small-sample context are
   **added as information/severity** on the report, not used to *suppress* the existing gate.
4. **Result types live in `agon/schemas`.** `Interval` and `ProportionTest` are Pydantic data
   models in `agon/schemas/models.py` (the "types that cross module boundaries" layer). `agon/stats`
   imports `agon.schemas`, never the reverse — no cycles. Computation (stats) and data (schemas)
   stay cleanly separated, mirroring the `ScoringSpec`-vs-scorers split.
5. **Small-sample threshold `n < 30`** is the shared "treat with caution" gate (a common
   rule-of-thumb for the normal approximation). Surfaced as a boolean/warning, never as a hard fail.

## Non-goals (deferred)

- Bayesian / credible intervals, sequential testing, power analysis.
- Multiple-comparison correction across per-category tests (noted as a future refinement).
- Per-case score-drop significance (composite scores are continuous; we keep the existing
  epsilon rule for those and apply significance to the *proportion* metrics).
- Changing the pass/fail *recommendation* logic — CIs inform, the thresholds still decide.

## Architecture

A new pure-Python **`agon/stats/`** package (stdlib only) provides the computation; `agon/schemas`
holds the result types; the analysis / calibration / reporting layers consume them.

```
agon/schemas (Interval, ProportionTest)  ◄── agon/stats (wilson_interval, two_proportion_test,
                                                          kappa_interval, normal_cdf, small_sample)
                                                  │
   analysis/logs (RunDigest + pass-rate CIs) ◄────┤
   analysis/regression (RegressionReport + sig) ◄─┤
   calibrate/runner (CalibrationReport + κ CI) ◄──┘
                                                  │
                          reporting/generator (md + json render the CIs / significance)
```

### Unit A — `agon/stats` core (+ schema result types)

- **Schemas** (`agon/schemas/models.py`):
  - `Interval` — `low: float`, `high: float`, `point: float`, `confidence: float = 0.95`.
  - `ProportionTest` — `diff: float` (current − baseline), `z: float`, `p_value: float`,
    `significant: bool`, `confidence: float = 0.95`.
- **`agon/stats/normal.py`** — `normal_cdf(z) -> float` (via `math.erf`); `Z_FOR` map or a helper
  `z_critical(confidence) -> float` (95% → 1.959963…). Hard-code the common critical values
  (0.90/0.95/0.99) to avoid an inverse-erf; default 0.95.
- **`agon/stats/proportion.py`**:
  - `wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval` — Wilson score
    formula; `n == 0` → `Interval(0.0, 1.0, 0.0)` (total uncertainty, documented).
  - `two_proportion_test(s1, n1, s2, n2, confidence=0.95) -> ProportionTest` — pooled two-proportion
    z-test; `diff = s1/n1 - s2/n2`; two-sided `p_value` via `normal_cdf`; `significant = p_value <
    1 - confidence`. Degenerate n (0) → `diff=0, z=0, p_value=1.0, significant=False`.
  - `small_sample(n: int, min_n: int = 30) -> bool`.
- **`agon/stats/kappa.py`** — `kappa_interval(po: float, pe: float, n: int, confidence=0.95) ->
  Interval`: normal-approx SE `se = sqrt(po*(1-po)) / ((1-pe) * sqrt(n))`, `CI = kappa ± z*se`
  clamped to `[-1, 1]`; `kappa = (po-pe)/(1-pe)`. Degenerate (`pe>=1` or `n==0`) handled explicitly.

### Unit B — Pass-rate CIs in the digest + reports

- `RunDigest` (in `agon/analysis/logs.py`) gains:
  - `overall_pass_ci: Interval` and `n_cases: int`.
  - `pass_ci_by_category: dict[str, Interval]` — built from the same per-category counts.
  - `small_sample: bool` (overall n < 30).
- `digest()` already computes overall `passed`/`total` and per-category `[passed, total]`; it calls
  `wilson_interval` to fill the new fields. No new traversal.
- `agon/reporting/generator.py` + the md template render the overall rate as
  `92.0% [85.1%, 95.8%] (n=20)` and a small-sample caution line when `small_sample`. `render_json`
  adds the interval objects. JUnit unchanged.

### Unit C — Regression significance + small-sample awareness

- `RegressionReport` (in `agon/schemas/models.py`) gains:
  - `pass_rate_test: ProportionTest | None` — the two-proportion test on overall pass rate
    (current vs. baseline).
  - `small_sample: bool` — either run below `min_n`.
- `compare_digests()` computes `two_proportion_test(cur_passed, cur_n, base_passed, base_n)` and
  sets the new fields. **`regression_detected` keeps its current definition** (`new_failures or
  severe_drop`); the test is informational. Optionally, a *significant aggregate drop* may be
  surfaced as additional severity in the report text, but it never *suppresses* the existing gate.
- The report (md + CLI `compare`) shows: `overall pass 88% -> 80% (diff -8.0pp, p=0.21, not
  significant; small sample)` so a reviewer sees whether a drop is signal or noise.

### Unit D — κ confidence interval in calibration

- `CalibrationReport` (in `agon/calibrate/runner.py`) gains `kappa_ci: Interval` and
  `small_sample: bool`.
- `run_calibration()` computes `po` (observed agreement) and `pe` (expected agreement) — already
  implicit in `cohen_kappa`; refactor so both are available — and calls `kappa_interval`.
- `passed` still keys on the point estimate vs. `min_kappa`; the CLI `calibrate` line and the
  report show `kappa=0.74 [0.55, 0.93] (n=25)`, making a borderline validation visibly uncertain.

## File structure (planned)

- **Create** `agon/stats/__init__.py`, `agon/stats/normal.py`, `agon/stats/proportion.py`,
  `agon/stats/kappa.py`.
- **Modify** `agon/schemas/models.py` — add `Interval`, `ProportionTest`; extend `RegressionReport`.
- **Modify** `agon/analysis/logs.py` — `RunDigest` CI fields + `digest()` population.
- **Modify** `agon/analysis/regression.py` — compute the pass-rate test.
- **Modify** `agon/calibrate/runner.py` — `CalibrationReport` κ CI; expose `po`/`pe`.
- **Modify** `agon/reporting/generator.py` + `agon/reporting/templates/report.md.jinja2` — render CIs.
- **Modify** `agon/cli/app.py` — `calibrate` (and `compare`) output shows the CIs / significance.
- **Create** `tests/test_stats.py` (core, textbook values), extend digest/regression/calibration tests.
- **Create** `docs/decisions/ADR-0007-statistical-rigor.md`; **modify** `README.md`, `CLAUDE.md`.

## Testing strategy

- TDD; `agon/stats` asserted against **known textbook values** with a tolerance (`pytest.approx`):
  Wilson 8/10 @95% ≈ [0.4930, 0.9367]; `normal_cdf(0)=0.5`, `normal_cdf(1.96)≈0.975`; a
  two-proportion test with a known z/p; a κ interval with hand-computed SE. Boundaries: n=0, 0/ n,
  n/n, pe≥1.
- Integration: an offline digest shows an interval; a regression compare shows the test; a
  calibration run shows the κ CI. Keep all printed/CLI output **ASCII** (cp1252): render intervals
  as `[0.85, 0.96]` and use `pp` / `p=` (no `±`, no `→`).
- Definition of done: full suite green (+ new tests), `ruff` clean, and the offline
  `agon run` / `agon compare` / `agon calibrate` outputs each show an interval or significance verdict.

## Consequences

- Results become honest about uncertainty: a 90%→88% move reads differently at n=50 vs n=500, and a
  borderline judge κ is visibly borderline.
- The regression gate stays exactly as sensitive (no real regression is ever silenced); reviewers
  gain a signal/noise read on top.
- One more reason the harness reads as "production-grade evaluation," not a single-number scorer —
  and it stays offline with zero new dependencies.
