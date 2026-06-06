"""Custom scorer for the text-to-SQL example: compare *result rows*, not SQL strings.

Why a custom scorer? Two different SQL strings can return identical rows. ``exact_match``
would wrongly fail an equivalent query; this scorer executes both queries against a fresh
in-memory SQLite DB (stdlib, offline) and compares the result sets.

Use it from the CLI:
    uv run agon run --plugin examples/text_to_sql/sql_scorer.py examples/text_to_sql/dataset.yaml
or from a launcher script (see run.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agon.scoring.base import ScoreOutcome, register

_SCHEMA_CACHE: dict[str, str] = {}


def _load_schema(schema_file: str) -> str:
    path = Path(schema_file)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    key = str(path)
    if key not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[key] = path.read_text(encoding="utf-8")
    return _SCHEMA_CACHE[key]


def _run_query(schema_sql: str, query: str) -> list[tuple]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema_sql)
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def compare_sql(candidate: str, reference: str, schema_sql: str) -> tuple[bool, str | None, str]:
    """Compare candidate vs reference SQL by result rows.

    Returns ``(passed, failure_label, detail)``. Order-insensitive unless the reference
    contains ``order by`` (then row order must match). A candidate that raises is a
    ``sql_error``; a clean-but-wrong result is ``wrong_rows``. A reference that raises is a
    dataset bug and is allowed to propagate (fail loud).
    """
    expected_rows = _run_query(schema_sql, reference)
    try:
        actual_rows = _run_query(schema_sql, candidate)
    except sqlite3.Error as exc:
        return (False, "sql_error", f"candidate query error: {exc}")

    if "order by" in reference.lower():
        match = actual_rows == expected_rows
    else:
        match = sorted(map(repr, actual_rows)) == sorted(map(repr, expected_rows))

    if match:
        return (True, None, f"{len(actual_rows)} rows match")
    return (False, "wrong_rows", f"expected {len(expected_rows)} rows, got {len(actual_rows)}")


@register
class SqlResultMatchScorer:
    scorer_type = "sql_result_match"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        reference = case.expected.expected_answer
        if reference is None:
            return ScoreOutcome(
                scorer_type=self.scorer_type,
                native_score=False,
                normalized_score=0.0,
                rationale="no expected_answer (reference SQL) provided",
            )
        schema_sql = _load_schema(spec.params.get("schema", "schema.sql"))
        passed, label, detail = compare_sql(response.final_answer, reference, schema_sql)
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=passed,
            normalized_score=1.0 if passed else 0.0,
            labels=[label] if label else [],
            rationale=detail,
        )
