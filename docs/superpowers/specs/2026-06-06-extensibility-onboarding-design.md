# Extensibility & Onboarding — Design Spec (Phase 3 M7)

**Status:** Approved (design) · **Date:** 2026-06-06 · **Milestone:** Phase 3 M7
**Branch:** `phase-3-m7-extensibility-onboarding`

## Goal

Turn the harness from "a thing the authors run" into an **all-purpose kit a newcomer can extend in an
afternoon**. Document and make first-class the three extension surfaces that already exist in the
code — **datasets** (YAML, no code), **scorers** (`@register` Python class), and **SUT adapters**
(`SUTRequest`->`SUTResponse` callable) — ship a **copy-me template** and a **worked example in a
brand-new domain (text-to-SQL)**, add the long-promised **`CONTRIBUTING.md`**, and close the one real
gap that blocks the scorer story: the CLI cannot see a user's scorer. Everything stays **offline-first
with zero new dependencies** (the example uses stdlib `sqlite3`).

## Background / current state

The extension points exist but are undocumented and partially un-wired:

- **Scorers** register via the `@register` class decorator onto `agon.scoring.default_registry`
  (`agon/scoring/base.py`). They are only *on* the registry if their module was imported — the
  side-effect import line at the bottom of `agon/scoring/__init__.py` is what loads the built-ins.
- **`agon run` always resolves scorers through `default_registry`.** The chain is
  `cli.run -> task.run_eval -> task/builder.py -> agon_scorer(judge=...) ->
  inspect_scorer.agon_scorer(registry=default_registry)` which calls `registry.get(spec.type)` and
  raises `KeyError("unknown scorer_type ...; registered: [...]")` on a miss. **There is no CLI flag
  to import an external module**, so a user's own scorer is invisible to `agon run` unless they fork
  `agon/scoring/__init__.py`. The only working path today is a Python launcher script
  (`examples/quickstart.py`-style) that imports the scorer module *before* calling `run_eval`.
- **Datasets** are plain YAML (`name` + `test_cases[]`); `agon/dataset/` validates and loads them.
  This surface needs only documentation.
- **SUT adapters** plug in via the `callable` solver (`agon/sut/solvers.py::callable_solver`), an
  `async (SUTRequest) -> SUTResponse` function. The CLI cannot wire a Python callable (noted in
  `quickstart.py`: "the `callable` adapter, which the CLI can't wire"), so this surface is inherently
  launcher-script-driven — and that is fine, it just needs to be documented.
- **`CONTRIBUTING.md` does not exist.** README §Contributing says "A `CONTRIBUTING.md` will accompany
  the Phase 1 release." The roadmap still lists onboarding as pending.

## Decisions locked

1. **`agon run --plugin` accepts BOTH a dotted module and a `.py` file path.** Repeatable
   (`-p`/`--plugin`). Each value is imported before the task builds, so any `@register` side-effects
   land on `default_registry`. Dotted names go through `importlib.import_module`; values that exist as
   a filesystem path (or end in `.py`) go through `importlib.util.spec_from_file_location`. The CWD is
   added to `sys.path` so a bare local module name resolves. This makes the copy-me template and the
   text-to-SQL example runnable straight from the CLI.
2. **Static copy-me template, not a generator.** A `templates/your-eval/` directory copied by hand —
   no `agon new` command (YAGNI; a generator is code with its own failure modes for no real gain over
   "copy this folder"). The template is docs-shaped and validated by one offline test so it never rots.
3. **Text-to-SQL is the new-domain worked example.** It is the example that most clearly *motivates a
   custom scorer*: `exact_match` wrongly fails semantically-equivalent SQL, whereas a scorer that
   executes both queries and compares result rows gets it right. Fully offline via stdlib `sqlite3`
   (in-memory DB), no new dependency.
3a. **The example's scorer ships only inside the example** (`examples/text_to_sql/sql_scorer.py`),
   loaded via `--plugin` — it is **not** added to `agon/scoring/__init__.py`'s built-in imports. This
   is deliberate: it proves the real extensibility story (extend from *your own* code without forking
   agon core), and keeps a domain-specific scorer out of the shipped default registry.
4. **The three extension points are the stable public contract** (recorded in ADR-0008): the dataset
   YAML schema, the `AgonScorer` protocol + `@register`/`default_registry`, and the `callable` SUT
   (`SUTRequest`/`SUTResponse`). Documenting them as stable is itself a deliverable.
5. **Offline-first, ASCII CLI output, no new deps/extras.** The example DB is stdlib `sqlite3`
   in-memory; all printed strings stay cp1252-safe (`-> `, `[...]`, no Unicode arrows/dashes).

## Non-goals (deferred)

- An `agon new <name>` scaffolding command (a static template covers the need).
- setuptools/importlib **entry-point** plugin discovery (auto-finding installed `agon.scorers`
  packages). The `--plugin` flag is the supported mechanism; entry-points can be a later refinement
  and ADR-0008 notes this.
- A second new-domain example beyond text-to-SQL.
- Loading external **datasets adapters** or **SUT adapters** via `--plugin` — the flag is scoped to
  importing modules so their scorer registrations fire; SUT adapters remain launcher-driven by design
  (the CLI cannot wire a Python callable regardless).
- Any change to scoring/aggregation logic — this milestone adds extension *surface* and *docs*, not
  new metrics.

## Architecture

One small core feature (the `--plugin` loader) plus four documentation/example artifacts. The loader
is the only thing that touches importable code paths; everything else is additive files.

```
agon/cli/app.py  --plugin/-p (repeatable)
      |
      v
agon/scoring/plugins.py::load_plugins(specs) -- importlib --> @register side-effects
      |                                                              |
      v                                                              v
(records names of newly-registered scorers)              agon.scoring.default_registry
      |                                                              |
      v                                                              v
typer.echo("loaded plugin scorers: sql_result_match")   inspect_scorer.registry.get(spec.type)  (now resolves)

templates/your-eval/      examples/text_to_sql/        docs/extending.md     CONTRIBUTING.md   ADR-0008
  dataset.yaml              schema.sql                   (3 sections)          (dev + principles) (contract)
  scorer.py (+test)         dataset.yaml                                       README link
  sut_adapter.py            sql_scorer.py
  run.py                    run.py
  README.md                 (tests)
```

### Unit A — `agon run --plugin` loader (the only core code change)

- **New module `agon/scoring/plugins.py`:**
  - `load_plugins(specs: Iterable[str]) -> list[str]` — for each spec, snapshot
    `set(default_registry.keys())`, import the spec, then return the sorted list of scorer_types that
    appeared (so the CLI can echo what got loaded). Import resolution:
    - If the spec exists as a file path **or** ends in `.py`: load via
      `importlib.util.spec_from_file_location(<derived module name>, <abspath>)` +
      `module_from_spec` + `spec.loader.exec_module`. A unique synthetic module name avoids collisions
      (`agon_plugin_<stem>`).
    - Else: ensure CWD is on `sys.path`, then `importlib.import_module(spec)`.
  - On failure, raise `PluginLoadError(spec, original)` (a small local exception) carrying the spec
    and the underlying error, for a clean CLI message.
- **`agon/cli/app.py`** — `run` gains `plugin: list[str] = typer.Option([], "--plugin", "-p", help=...)`.
  Before `load_dataset` / `run_eval`, call `load_plugins(plugin)`; on `PluginLoadError`, `typer.echo`
  the message and `raise typer.Exit(2)` (matching the existing abort convention). On success with a
  non-empty result, echo `loaded plugin scorers: a, b` (ASCII). Also **sharpen the unknown-scorer
  error**: `inspect_scorer`/`registry.get` already lists registered types; append a hint
  `(did you forget --plugin <module>?)` to the `KeyError` message text raised in
  `agon/scoring/base.py::ScorerRegistry.get`.
- **Tests** (`tests/test_plugins.py`): (1) load a temp `.py` file that `@register`s a dummy scorer ->
  it is on `default_registry` and `load_plugins` returns its name; (2) load a dotted module on
  `sys.path` -> same; (3) bad path/module -> `PluginLoadError`; (4) a dataset referencing an
  unknown scorer_type produces an error message mentioning `--plugin`. Each test cleans up the
  registry entry it added (and any `sys.modules` injection) so suite order stays deterministic.

### Unit B — copy-me template (`templates/your-eval/`)

- `dataset.yaml` — 2-3 skeleton cases, every field commented with what to put there; uses one
  built-in scorer (`keyword_containment`) so it runs with **no** custom code, plus a commented-out
  line showing how to reference a custom scorer + `--plugin`.
- `scorer.py` — a minimal `@register class MyScorer` with `scorer_type = "my_scorer"`,
  `requires_judge = False`, an `async def score(self, case, response, spec, *, judge=None)` returning
  a `ScoreOutcome`, and `# TODO:` markers at the decision points (what to compare, how to normalize,
  which failure labels).
- `test_scorer.py` — one boundary test for the stub scorer (pass case + fail case), modelling the
  "every scorer gets a boundary test" rule.
- `sut_adapter.py` — an `async def my_sut(req: SUTRequest) -> SUTResponse` stub plus a short comment
  block showing the launcher wiring (`build_solver`/`callable_solver` + `run_eval`).
- `run.py` — a runnable launcher: import scorer + adapter, `load_dataset`, `run_eval` with the
  callable SUT, `generate_reports`. Mirrors `examples/quickstart.py`.
- `README.md` — an ordered checklist: "1. edit dataset.yaml; 2. (optional) write scorer.py; 3. run it
  two ways (`agon run --plugin scorer.py dataset.yaml`, or `python run.py` for a custom SUT)".
- **Test** (`tests/test_template.py`): run the template's `run.py` (or its dataset through `run_eval`)
  offline and assert it produces a digest — guarantees the template never bit-rots.

### Unit C — worked example (`examples/text_to_sql/`)

- `schema.sql` — a tiny, self-contained schema + seed `INSERT`s (e.g. `employees(id, name, dept,
  salary)`), small enough to read at a glance. Loaded into an **in-memory** `sqlite3` connection.
- `dataset.yaml` — ~6-8 NL->SQL cases. Each: `input.user_message` = the natural-language question;
  `expected.expected_answer` = the reference SQL; `scoring: [{type: sql_result_match, weight: 1.0,
  pass_threshold: 1.0, params: {schema: schema.sql}}]`; `failure_labels: [sql_error, wrong_rows]`.
  Includes at least one case where a *different but equivalent* query is the SUT's answer (passes on
  result rows, would fail `exact_match`) and one genuinely wrong query (fails).
- `sql_scorer.py` — `@register class SqlResultMatchScorer` (`scorer_type = "sql_result_match"`):
  - Reads the candidate SQL from `response.final_answer` and the reference SQL from
    `case.expected.expected_answer`. The schema file is named by `spec.params.get("schema",
    "schema.sql")` and resolved **relative to the scorer module's own directory**
    (`Path(__file__).parent`) when the value is not absolute — the scorer receives only
    `case/response/spec`, never the dataset path, so it cannot resolve relative to the dataset. The
    schema SQL is read once and cached at module level.
  - Builds a fresh in-memory DB from the schema, executes both queries, compares **result row-sets**:
    order-insensitive (sorted rows) **unless** the reference SQL contains `order by` (case-insensitive
    word match), in which case order is significant. `normalized_score = 1.0` on match else `0.0`.
  - Error handling: a candidate that raises `sqlite3.Error` -> `normalized_score=0.0`,
    `labels=["sql_error"]`, rationale carries the DB message; a clean-but-wrong result ->
    `labels=["wrong_rows"]`. A malformed *reference* query is a dataset bug -> raises (fail loud).
  - Pure function core (`compare_sql(candidate, reference, schema_sql) -> (bool, label, detail)`) so
    the row-comparison logic is unit-testable without the scorer/Inspect wrapper.
- `run.py` — a stub NL->SQL SUT: `RESPONSES: dict[test_id, sql_string]` (a couple intentionally wrong
  to produce a mixed report), `async def stub_sut`, then `run_eval` + `generate_reports`. Prints the
  reports dir. Mirrors the existing quickstarts.
- **Tests** (`tests/test_text_to_sql.py`): assert `compare_sql` on (a) identical query -> pass,
  (b) equivalent-but-different query (e.g. `WHERE dept='eng'` vs a join giving same rows) -> pass,
  (c) wrong query -> fail + `wrong_rows`, (d) malformed candidate -> fail + `sql_error`; and an
  integration test that the example dataset run yields the expected pass/fail split.
- The CLI path is exercised in docs: `agon run --plugin examples/text_to_sql/sql_scorer.py
  examples/text_to_sql/dataset.yaml` (with the default mock SUT) demonstrates `--plugin` end-to-end.

### Unit D — extension guide (`docs/extending.md`)

Three parallel sections, each: **the contract -> a minimal example -> how to run it -> the test you
owe**.
- **Add a dataset** — the YAML schema (fields, scoring specs, failure labels), validation via
  `agon run`, pointer to `examples/datasets/`.
- **Add a scorer** — the `AgonScorer` protocol, `ScoreOutcome` fields, `@register`, and the two ways
  to use it: `agon run --plugin <module-or-file> <dataset.yaml>` (CLI) and the launcher pattern.
  Worked against `sql_result_match`. States the boundary-test requirement.
- **Add a SUT adapter** — the `SUTRequest`/`SUTResponse` contract, the `callable` solver, why this is
  launcher-driven, worked against the template's `sut_adapter.py` + `run.py`.
Links back to the template and the text-to-SQL example; linked from README and CONTRIBUTING.

### Unit E — `CONTRIBUTING.md` + README/CLAUDE wiring

- `CONTRIBUTING.md`: dev setup (`uv sync`, `uv run pytest`, `uv run ruff check agon tests`, Python
  3.12, offline-first); the project principles (failure-is-data -> add the regression case;
  evidence-over-claims; retrieval isolated from generation; no single-number); "how to extend" (links
  to `docs/extending.md` + template); the ADR process (when to add `docs/decisions/ADR-NNNN-*.md`);
  commit conventions (targeted `git add` of your own files, the
  `Co-Authored-By: Claude Opus 4.8 (1M context)` trailer, "maintainer merges PRs"); and the
  definition of done (suite green + ruff clean + a boundary test for any new scorer).
- **README** — replace the "A `CONTRIBUTING.md` will accompany..." sentence with a link to
  `CONTRIBUTING.md` and `docs/extending.md`; tick the relevant roadmap box; add a one-line
  `agon run --plugin ...` to the command list.
- **CLAUDE.md** — add `templates/` to the layout note and a line that custom scorers load via
  `--plugin` (module or file).

## File structure (planned)

- **Create** `agon/scoring/plugins.py`.
- **Modify** `agon/cli/app.py` (`run` gains `--plugin`), `agon/scoring/base.py`
  (`ScorerRegistry.get` message hint).
- **Create** `templates/your-eval/{dataset.yaml,scorer.py,test_scorer.py,sut_adapter.py,run.py,README.md}`.
- **Create** `examples/text_to_sql/{schema.sql,dataset.yaml,sql_scorer.py,run.py}`.
- **Create** `docs/extending.md`, `CONTRIBUTING.md`,
  `docs/decisions/ADR-0008-extensibility-contract.md`.
- **Create** `tests/test_plugins.py`, `tests/test_template.py`, `tests/test_text_to_sql.py`.
- **Modify** `README.md`, `CLAUDE.md`.

## Testing strategy

- TDD. The pure cores get boundary tests: `load_plugins` (file path, dotted module, failure) and
  `compare_sql` (identical, equivalent, wrong, malformed) asserted directly, no CLI/Inspect in the
  loop. Registry/`sys.modules` mutations made by a test are undone in that test so suite order is
  deterministic.
- Integration (all offline, no key, no downloads): `agon run --plugin examples/text_to_sql/sql_scorer.py
  examples/text_to_sql/dataset.yaml` resolves the scorer and reports; `python examples/text_to_sql/run.py`
  yields the expected mixed pass/fail; `python templates/your-eval/run.py` produces a digest.
- All printed/CLI output stays **ASCII** (cp1252): `-> `, `[...]`, `loaded plugin scorers: ...` — no
  Unicode arrows/dashes. Markdown/YAML/docstrings may be UTF-8.
- Definition of done: full suite green (+ new tests), `ruff` clean (line-length 100), and the three
  offline integration commands above each succeed and emit reports.

## Consequences

- A newcomer can stand up a brand-new eval — dataset, custom scorer, and their own system — from a
  copy-me folder and a single guide, and run it from the CLI with `--plugin`. The harness reads as an
  all-purpose kit, not a fixed in-house suite.
- The text-to-SQL example demonstrates the core thesis of the project in miniature: a naive scorer
  (`exact_match`) is *wrong* here, and writing the right custom scorer is a few dozen lines — failure
  is data, and the harness makes adding the catch trivial.
- The three extension points become a documented, stable contract (ADR-0008), so future milestones
  extend rather than re-invent. `--plugin` is a small, well-bounded surface; entry-point discovery is
  left as a clearly-scoped future option.
- Still zero new dependencies, still fully offline, still inside the 20-minute reproducibility budget.
