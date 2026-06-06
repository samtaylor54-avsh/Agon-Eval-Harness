# Extending Agon

Agon has three extension surfaces. Pick the smallest one that does the job:

| You want to...                                  | Surface        | Code? |
|-------------------------------------------------|----------------|-------|
| Add new test cases                              | a **dataset**  | No (YAML) |
| Score answers in a way the built-ins can't      | a **scorer**   | Yes (~30 lines) |
| Evaluate **your own** system, not the mock      | a **SUT adapter** | Yes (one function) |

A copy-me skeleton for all three lives in `templates/your-eval/`. A complete worked example
(with a real custom scorer) lives in `examples/text_to_sql/`.

## 1. Add a dataset (no code)

A dataset is a YAML file: a `name` plus a list of `test_cases`. Each case:

- `test_id` (unique, `[a-z0-9_-]`), `name`, `category`, optional `risk_level` (low|medium|high)
- `input.user_message` -- the challenge given to the system
- `expected` -- references the scorer checks (`expected_answer`, `answer_contains`,
  `allowed_sources`, `citation_required`, `json_schema`, ...)
- `scoring` -- one or more `{type, weight, pass_threshold, params}` specs; `type` must name a
  registered scorer (`uv run agon run --help` lists the built-ins, or see `agon/scoring/`)
- `failure_labels` -- the labels a failing case may surface (intersected with what scorers emit)

Run and validate it:

    uv run agon run path/to/your_dataset.yaml --display none

Built-in scorers include `exact_match`, `keyword_containment`, `citation_check`, `json_schema`,
and judge-backed ones (`rubric`, `safety`, `faithfulness`, ...) that need a real provider. See
`examples/datasets/rag_smoke.yaml` for a 20-case reference.

**The test you owe:** none for data alone -- but if a case encodes a real failure you found, that
*is* the regression test (failure is data).

## 2. Add a scorer (Python)

A scorer is a class with `scorer_type`, `requires_judge`, and an async `score(...)` that returns a
normalized `ScoreOutcome`. Register it with `@register`:

```python
from agon.scoring.base import ScoreOutcome, register


@register
class MyScorer:
    scorer_type = "my_scorer"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        passed = ...  # compare response.final_answer to case.expected / spec.params
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[] if passed else ["my_failure_label"],
        )
```

`ScoreOutcome` fields: `scorer_type`, `native_score` (raw value), `normalized_score` (0..1, the
number that gates the case), `labels` (failure labels), `rationale`, `details`.

**Use it from the CLI** without touching agon's source -- point `--plugin` at your module (a dotted
name on `sys.path`) or your `.py` file:

    uv run agon run --plugin my_scorers.py path/to/dataset.yaml --display none

(`--plugin` is repeatable. If a dataset names a scorer that isn't registered, `agon run` aborts
with a list of registered types and a reminder to pass `--plugin`.)

**Worked example:** `examples/text_to_sql/sql_scorer.py` implements `sql_result_match`, which runs
both the candidate and reference SQL against an in-memory SQLite DB and compares result rows -- so
two different-but-equivalent queries both pass, where `exact_match` would wrongly fail one.

**The test you owe:** a boundary test asserting the normalized score at a pass case and a fail case
(and any special path, e.g. malformed input). Keep the comparison logic a pure function so it's
testable without the harness -- see `compare_sql` in the text-to-SQL example and its tests in
`tests/test_text_to_sql.py`.

## 3. Add a SUT adapter (evaluate your own system)

The System Under Test is reached through a normalized contract: an async function
`(SUTRequest) -> SUTResponse`.

```python
from agon.sut import SUTRequest, SUTResponse


async def my_sut(req: SUTRequest) -> SUTResponse:
    answer = call_my_system(req.user_message, req.documents)
    return SUTResponse(final_answer=answer, citations=[...])
```

`SUTRequest`: `user_message`, `documents`, `session_id`, `config_overrides`.
`SUTResponse`: `final_answer`, `citations`, `tool_calls`, `retrieved_documents`, `token_usage`, ...

The CLI cannot wire a Python callable, so drive the eval from a short launcher script (the
`callable` adapter):

```python
from agon.dataset import load_dataset
from agon.reporting import generate_reports
from agon.schemas import RunConfig, SUTConfig
from agon.task import run_eval

dataset = load_dataset("your_dataset.yaml")
config = RunConfig(sut=SUTConfig(adapter="callable"))
log = run_eval(dataset, config, callable_fn=my_sut, display="none")
generate_reports(log, config=config, out_dir="reports")
```

For an HTTP system you don't need a callable at all -- set `adapter="http"`, `endpoint_url`, and a
`field_map` on `SUTConfig` and run from the CLI. See `examples/quickstart.py` (callable) and
`docs/running-real-evals.md` (providers/HTTP).

**The test you owe:** if your adapter does non-trivial mapping (HTTP JSON -> `SUTResponse`), test
that mapping on a representative payload.
