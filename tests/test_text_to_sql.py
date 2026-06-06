"""M7 — text-to-SQL custom scorer: result-set comparison, not string equality."""

from __future__ import annotations

import importlib.util
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "text_to_sql"
SCHEMA_SQL = (EXAMPLE_DIR / "schema.sql").read_text(encoding="utf-8")


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, str(EXAMPLE_DIR / filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sql_scorer = _load_module("t2s_scorer_under_test", "sql_scorer.py")


def test_identical_query_passes():
    ref = "SELECT name FROM employees WHERE dept = 'engineering'"
    ok, label, _ = sql_scorer.compare_sql(ref, ref, SCHEMA_SQL)
    assert ok and label is None


def test_equivalent_but_different_query_passes():
    ref = "SELECT name FROM employees WHERE dept = 'engineering'"
    cand = "SELECT name FROM employees WHERE dept IN ('engineering')"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert ok and label is None


def test_wrong_rows_fails_with_label():
    ref = "SELECT name FROM employees WHERE salary > 100000"
    cand = "SELECT name FROM employees WHERE salary > 50000"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "wrong_rows"


def test_malformed_candidate_fails_with_sql_error():
    ref = "SELECT name FROM employees"
    cand = "SELECT name FROM emploable"  # no such table
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "sql_error"


def test_order_sensitive_when_reference_orders():
    ref = "SELECT name FROM employees ORDER BY salary DESC"
    cand = "SELECT name FROM employees ORDER BY salary ASC"
    ok, label, _ = sql_scorer.compare_sql(cand, ref, SCHEMA_SQL)
    assert not ok and label == "wrong_rows"


async def test_scorer_wraps_compare_into_outcome():
    from agon.schemas import AgonCase, ExpectedBehavior, ScoringSpec
    from agon.sut import SUTResponse

    case = AgonCase(
        test_id="sql_x",
        name="n",
        category="text_to_sql",
        input={"user_message": "names in engineering"},
        expected=ExpectedBehavior(
            expected_answer="SELECT name FROM employees WHERE dept = 'engineering'"
        ),
        scoring=[ScoringSpec(type="sql_result_match", params={"schema": "schema.sql"})],
    )
    resp = SUTResponse(final_answer="SELECT name FROM employees WHERE dept IN ('engineering')")
    scorer = sql_scorer.SqlResultMatchScorer()
    out = await scorer.score(case, resp, case.scoring[0])
    assert out.normalized_score == 1.0
    assert out.labels == []
