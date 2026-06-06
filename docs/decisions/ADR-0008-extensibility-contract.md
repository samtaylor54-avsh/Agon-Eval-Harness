# ADR-0008: Extensibility contract and the `--plugin` loader

**Status:** Accepted · **Date:** 2026-06-06 · **Milestone:** Phase 3 M7

## Context

The harness had three extension points in code but no documented contract and one real gap: a
user's own scorer was invisible to `agon run` (the CLI resolves scorers through the global
`default_registry`, populated only by side-effect imports in `agon/scoring/__init__.py`). The only
way to use a custom scorer was to fork that file or write a launcher script.

## Decision

1. **The three extension surfaces are the stable public contract:**
   - **Dataset** -- the YAML `test_cases` schema (`AgonCase` / `ScoringSpec` / `ExpectedBehavior`).
   - **Scorer** -- the `AgonScorer` protocol + the `@register` / `default_registry` mechanism,
     returning a normalized `ScoreOutcome`.
   - **SUT adapter** -- the `callable` solver, i.e. an async `(SUTRequest) -> SUTResponse`.
2. **`agon run --plugin <spec>` (repeatable)** imports external scorer modules before the task
   builds, so their `@register` side-effects land on `default_registry`. A spec is a dotted module
   name **or** a path to a `.py` file. A pre-flight check aborts (exit 2) with a helpful message if a
   dataset references an unregistered scorer.
3. **Onboarding is docs + a static template + one worked example**, not a generator: a copy-me
   `templates/your-eval/`, a `docs/extending.md` guide, a `CONTRIBUTING.md`, and a brand-new-domain
   example (`examples/text_to_sql/`) whose custom `sql_result_match` scorer compares result rows.

## Alternatives considered

- **`agon new` scaffolding command** -- rejected (YAGNI; a static folder needs no code/tests and
  can't drift from the runtime).
- **setuptools entry-point plugin discovery** -- deferred. `--plugin` covers the need explicitly;
  entry-point auto-discovery of installed `agon.scorers` packages can be added later without breaking
  the flag.
- **Shipping `sql_result_match` as a built-in** -- rejected. It is domain-specific and lives in the
  example, loaded via `--plugin`, precisely to demonstrate extending from your own code.

## Consequences

- A newcomer can stand up a new eval -- dataset, scorer, and their own system -- from a copy-me
  folder and one guide, and run it from the CLI. The three surfaces are documented and stable, so
  future milestones extend rather than re-invent.
- `--plugin` is a small, well-bounded surface; the example proves the project's thesis in miniature
  (a naive scorer is wrong here; the right custom scorer is a few dozen lines). Still zero new
  dependencies, still fully offline.
