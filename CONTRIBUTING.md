# Contributing to Agon

Thanks for extending the harness. A documented failure mode or a new eval is as valuable here as a
feature -- **failure is data**: when you find a way a system breaks, add the case that catches it.

## Dev setup

```bash
uv sync                                   # Python pinned to 3.12 via .python-version
uv run pytest                             # full suite, fully offline (mockllm)
uv run ruff check agon tests              # lint (line-length 100)
```

Everything must run **offline** by default -- no API key, no model downloads -- via Inspect's
`mockllm/model` provider. Real-provider and semantic-scorer paths are opt-in extras. A reviewer
should be able to clone and run the harness in under 20 minutes; keep examples within that budget.

## Principles (these shape every change)

- **Failure is data, not noise.** Fix a failure mode *and* add the regression case to a dataset.
- **Evidence over claims.** Back results with metrics, traces, reproducible runs -- never assertions.
- **Retrieval is isolated from generation.** recall@k / MRR are measured by `agon retrieve`,
  independently of answer quality. Don't conflate them in one score.
- **No single-number obsession.** The evaluation categories are tracked distinctly.

## Adding things

See **[docs/extending.md](docs/extending.md)** for the three extension surfaces (dataset, scorer,
SUT adapter) and **`templates/your-eval/`** for a copy-me skeleton. In short:

- New **scorer**: a class with `@register` (see `agon/scoring/`); usable from the CLI via
  `agon run --plugin <module-or-file> <dataset.yaml>`. Every scorer earns a **boundary test**
  asserting its normalized score at pass/fail; keep the core comparison a pure function.
- New **dataset**: a YAML file of `test_cases` (validated by `agon run`).
- New **SUT adapter**: an async `(SUTRequest) -> SUTResponse`, driven from a launcher script.

## Decisions & ADRs

Architectural decisions are recorded under `docs/decisions/ADR-NNNN-*.md`. If your change makes a
non-obvious trade-off (a new dependency, a contract, a default), add an ADR.

## Commits & PRs

- Stage only the files your change touches (`git add <paths>`), not `git add .` -- the tree carries
  unrelated untracked artifacts.
- Create new commits rather than amending; don't skip hooks.
- Don't push or open a PR unless asked; the maintainer merges.

## Definition of done

`uv run pytest` green, `uv run ruff check agon tests` clean, a boundary test for any new scorer,
and -- if you fixed a failure -- the case that reproduces it added to a dataset.
