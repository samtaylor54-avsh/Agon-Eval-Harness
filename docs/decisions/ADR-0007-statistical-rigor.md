# ADR-0007: Statistical rigor via closed-form, dependency-free statistics

**Status:** Accepted · **Date:** 2026-06-05 · **Milestone:** Phase 3 M6

## Context

The harness reported point estimates only: bare pass rates, a fixed-epsilon regression rule, and a
Cohen's kappa with no interval. A 90% -> 88% move on 50 samples looked identical to the same move on
500; a borderline judge kappa looked as trustworthy as a confident one. The project is offline-first
with a minimal dependency set.

## Decision

Add uncertainty-aware statistics computed **closed-form in pure Python** (a new `agon/stats`
package), with the result types (`Interval`, `ProportionTest`) living in `agon/schemas`:

- **Pass rates** carry a **Wilson score interval** (stable at small n and at 0%/100%), surfaced in
  the digest and md/json reports, with a small-sample note when n < 30.
- **Regression** gains a **two-proportion z-test** on the overall pass-rate delta plus a
  small-sample flag — as *information*. The existing gate (new failures / high-risk score drops) is
  unchanged: a real regression is never silenced by "not statistically significant."
- **Calibration** gains a **normal-approximation confidence interval on Cohen's kappa**, so a
  borderline judge validation is visibly uncertain. `passed` still keys on the point estimate.

No scipy/numpy: the normal CDF is `math.erf`; z criticals are constants; all formulas are
textbook-tested.

## Consequences

- Results are honest about uncertainty without adding a dependency or breaking the offline path.
- Reviewers get a signal/noise read; the regression gate keeps its exact sensitivity.

## Deferred

- Bayesian / credible intervals, sequential testing, power analysis; multiple-comparison correction
  across per-category tests; per-case (continuous score) significance.
