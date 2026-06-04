"""Deterministic, judge-free scorers (PRD §25.1-25.5, §25.10).

These run on the offline path with no API key and no model downloads (except
``semantic_similarity``, which is gated behind the ``[semantic]`` extra).
"""

from __future__ import annotations

import json

from agon.scoring.base import ScoreOutcome, collapse_ws, register


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@register
class ExactMatchScorer:
    scorer_type = "exact_match"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        expected = case.expected.expected_answer
        actual = response.final_answer
        case_sensitive = bool(spec.params.get("case_sensitive", False))
        if expected is None:
            return ScoreOutcome(
                scorer_type=self.scorer_type,
                native_score=False,
                normalized_score=0.0,
                rationale="no expected_answer provided",
            )
        a, e = collapse_ws(actual), collapse_ws(expected)
        if not case_sensitive:
            a, e = a.lower(), e.lower()
        match = a == e
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=match,
            normalized_score=1.0 if match else 0.0,
        )


@register
class JSONSchemaScorer:
    scorer_type = "json_schema"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        import jsonschema

        schema = case.expected.json_schema
        if schema is None:
            return ScoreOutcome(
                scorer_type=self.scorer_type,
                native_score=False,
                normalized_score=0.0,
                rationale="no json_schema provided in expected",
                labels=["format_failure"],
            )
        try:
            parsed = json.loads(response.final_answer)
        except (json.JSONDecodeError, TypeError):
            return ScoreOutcome(
                scorer_type=self.scorer_type,
                native_score=False,
                normalized_score=0.0,
                rationale="response is not valid JSON",
                labels=["format_failure"],
            )
        validator = jsonschema.Draft202012Validator(schema)
        errors = [e.message for e in validator.iter_errors(parsed)]
        valid = not errors
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=valid,
            normalized_score=1.0 if valid else 0.0,
            labels=[] if valid else ["format_failure"],
            details={"validation_errors": errors},
        )


@register
class KeywordContainmentScorer:
    scorer_type = "keyword_containment"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        answer = response.final_answer.lower()
        contains = case.expected.answer_contains
        not_contains = case.expected.answer_not_contains
        hits = sum(1 for k in contains if k.lower() in answer)
        violations = [k for k in not_contains if k.lower() in answer]
        base = hits / max(1, len(contains))
        labels: list[str] = []
        if violations:
            normalized = 0.0
            labels.append("instruction_following_failure")
        else:
            normalized = base
            if base < 1.0:
                labels.append("incomplete_answer")
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=base,
            normalized_score=_clamp(normalized),
            labels=labels,
            details={"hits": hits, "required": len(contains), "violations": violations},
        )


@register
class RougeLScorer:
    scorer_type = "rouge_l"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        from rouge_score import rouge_scorer

        expected = case.expected.expected_answer or ""
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        fmeasure = scorer.score(expected, response.final_answer)["rougeL"].fmeasure
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=fmeasure,
            normalized_score=_clamp(fmeasure),
        )


@register
class SemanticSimilarityScorer:
    scorer_type = "semantic_similarity"
    requires_judge = False

    _model_cache: dict[str, object] = {}

    def _model(self, name: str):
        if name not in self._model_cache:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - exercised only without extra
                raise ImportError(
                    "semantic_similarity requires the [semantic] extra: "
                    "uv sync --extra semantic"
                ) from exc
            self._model_cache[name] = SentenceTransformer(name)
        return self._model_cache[name]

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        expected = case.expected.expected_answer or ""
        model_name = spec.params.get("model", "all-MiniLM-L6-v2")
        model = self._model(model_name)
        emb = model.encode([response.final_answer, expected], normalize_embeddings=True)
        cos = float(emb[0] @ emb[1])  # normalized → dot product == cosine
        normalized = _clamp((cos + 1) / 2)
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=cos,
            normalized_score=normalized,
            details={"cosine": cos, "model": model_name},
        )


def _source_of(citation: str) -> str:
    """Strip a citation fragment: 'doc.pdf#section-4.2' -> 'doc.pdf'."""
    return citation.split("#", 1)[0]


@register
class CitationCheckScorer:
    scorer_type = "citation_check"
    requires_judge = False

    async def score(self, case, response, spec, *, judge=None) -> ScoreOutcome:
        exp = case.expected
        actual = response.citations
        expected = exp.expected_citations
        allowed = exp.allowed_sources

        presence = 1.0 if (not exp.citation_required) or len(actual) > 0 else 0.0
        if expected:
            correctness = len(set(actual) & set(expected)) / max(1, len(expected))
        else:
            correctness = presence
        out_of_scope = (
            any(_source_of(c) not in allowed for c in actual) if allowed else False
        )

        labels: list[str] = []
        if presence == 0.0:
            labels.append("missing_citation")
        if out_of_scope:
            labels.append("wrong_citation")

        normalized = 0.0 if out_of_scope else (presence + correctness) / 2
        return ScoreOutcome(
            scorer_type=self.scorer_type,
            native_score=normalized,
            normalized_score=_clamp(normalized),
            labels=labels,
            details={
                "presence": presence,
                "correctness": correctness,
                "out_of_scope": out_of_scope,
            },
        )
