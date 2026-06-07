"""Walk an Inspect EvalLog into an OpenTelemetry GenAI span tree.

Tree shape:
    eval <task>                 (invoke_workflow)
      └─ invoke_agent <sample>  (one per sample)
           ├─ chat <model>      (per model event; tokens, provider)
           ├─ execute_tool <t>  (per tool event; ERROR status on tool errors)
           └─ agon.score <s>    (per score event; scorer + value)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from opentelemetry import trace as otrace
from opentelemetry.trace import Status, StatusCode

from agon.observability.semconv import (
    AGON_CATEGORY,
    AGON_COMPOSITE_SCORE,
    AGON_COST_INPUT_TOKENS,
    AGON_COST_OUTPUT_TOKENS,
    AGON_COST_TOTAL_TOKENS,
    AGON_COST_USD,
    AGON_DATASET_VERSION,
    AGON_ERROR_CATEGORY,
    AGON_ERROR_COUNT,
    AGON_ERROR_COUNT_PREFIX,
    AGON_FAILURE_LABELS,
    AGON_N_CASES,
    AGON_OVERALL_PASS_RATE,
    AGON_PASSED,
    AGON_RECOMMENDATION,
    AGON_RISK_LEVEL,
    AGON_RUN_ID,
    AGON_SAMPLE_ID,
    AGON_SCORE_VALUE,
    AGON_SCORER,
    AGON_SYSTEM_VERSION,
    AGON_TASK,
    GEN_AI_AGENT_NAME,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_NAME,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    OP_CHAT,
    OP_EXECUTE_TOOL,
    OP_INVOKE_AGENT,
    OP_INVOKE_WORKFLOW,
)
from agon.secrets import redact

_MIN_DUR_NS = 1_000_000  # 1ms span for point-in-time events


def _ns(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return int(ts.timestamp() * 1_000_000_000)


def _strval(value: Any) -> str:
    s = json.dumps(value, default=str) if isinstance(value, dict | list) else str(value)
    return redact(s)


def _emit_model(tracer: Any, ctx: Any, e: Any) -> int:
    start = _ns(e.timestamp)
    end = _ns(getattr(e, "completed", None)) or (start + _MIN_DUR_NS)
    model = e.model or "unknown"
    attrs = {
        GEN_AI_OPERATION_NAME: OP_CHAT,
        GEN_AI_PROVIDER_NAME: model.split("/")[0],
        GEN_AI_REQUEST_MODEL: model,
        GEN_AI_RESPONSE_MODEL: model,
    }
    usage = getattr(getattr(e, "output", None), "usage", None)
    if usage is not None:
        attrs[GEN_AI_USAGE_INPUT_TOKENS] = int(usage.input_tokens or 0)
        attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = int(usage.output_tokens or 0)
    span = tracer.start_span(f"chat {model}", context=ctx, start_time=start, attributes=attrs)
    span.end(end_time=end)
    return end


def _emit_tool(tracer: Any, ctx: Any, e: Any) -> int:
    start = _ns(e.timestamp)
    end = _ns(getattr(e, "completed", None)) or (start + _MIN_DUR_NS)
    name = getattr(e, "function", None) or "tool"
    attrs = {GEN_AI_OPERATION_NAME: OP_EXECUTE_TOOL, GEN_AI_TOOL_NAME: name}
    if getattr(e, "id", None):
        attrs[GEN_AI_TOOL_CALL_ID] = str(e.id)
    span = tracer.start_span(
        f"execute_tool {name}", context=ctx, start_time=start, attributes=attrs
    )
    if getattr(e, "error", None):
        span.set_status(Status(StatusCode.ERROR, redact(str(e.error))))
    span.end(end_time=end)
    return end


def _emit_score(tracer: Any, ctx: Any, e: Any) -> int:
    start = _ns(e.timestamp)
    end = start + _MIN_DUR_NS
    scorer = getattr(e, "scorer", None) or "scorer"
    value = getattr(getattr(e, "score", None), "value", None)
    attrs = {AGON_SCORER: scorer, AGON_SCORE_VALUE: _strval(value)}
    span = tracer.start_span(
        f"agon.score {scorer}", context=ctx, start_time=start, attributes=attrs
    )
    span.end(end_time=end)
    return end


_EMITTERS = {"model": _emit_model, "tool": _emit_tool, "score": _emit_score}


def _run_outcome_attrs(d: Any) -> dict[str, Any]:
    """Run-level scalar attributes from a RunDigest. recommendation uses default thresholds."""
    from agon.reporting.generator import recommend
    from agon.schemas import RunConfig

    cfg = RunConfig()
    rec = recommend(
        d, None, pass_threshold=cfg.pass_threshold, investigate_threshold=cfg.investigate_threshold
    )
    attrs: dict[str, Any] = {
        AGON_OVERALL_PASS_RATE: float(d.overall_pass_rate),
        AGON_N_CASES: int(d.n_cases),
        AGON_ERROR_COUNT: int(d.error_count),
        AGON_RECOMMENDATION: rec.value,
        AGON_COST_USD: float(d.cost.total_usd),
        AGON_COST_INPUT_TOKENS: int(d.cost.usage.input),
        AGON_COST_OUTPUT_TOKENS: int(d.cost.usage.output),
        AGON_COST_TOTAL_TOKENS: int(d.cost.usage.total),
    }
    for category, count in d.error_count_by_category.items():
        attrs[AGON_ERROR_COUNT_PREFIX + category] = int(count)
    if d.system_version:
        attrs[AGON_SYSTEM_VERSION] = redact(str(d.system_version))
    if d.dataset_version:
        attrs[AGON_DATASET_VERSION] = redact(str(d.dataset_version))
    return attrs


def _sample_outcome_attrs(rec: Any) -> dict[str, Any]:
    """Per-sample scalar attributes from a SampleRecord. Free-text strings are redacted."""
    attrs: dict[str, Any] = {
        AGON_PASSED: bool(rec.passed),
        AGON_COMPOSITE_SCORE: float(rec.composite_score),
        AGON_CATEGORY: redact(str(rec.category)),
        AGON_RISK_LEVEL: str(rec.risk_level),
    }
    if rec.error_category:
        attrs[AGON_ERROR_CATEGORY] = str(rec.error_category)
    if rec.detected_failure_labels:
        attrs[AGON_FAILURE_LABELS] = redact(",".join(rec.detected_failure_labels))
    return attrs


def export_eval_log(log: Any, tracer: Any, *, digest: Any = None) -> int:
    """Emit the eval log as GenAI spans through ``tracer``. Returns the span count."""
    samples = log.samples or []
    first_ts = _ns(samples[0].events[0].timestamp) if (samples and samples[0].events) else None
    run_start = first_ts or _ns(log.eval.created)

    run_attrs = {
        GEN_AI_OPERATION_NAME: OP_INVOKE_WORKFLOW,
        AGON_RUN_ID: log.eval.run_id,
        AGON_TASK: log.eval.task,
    }
    if log.eval.model:
        run_attrs[GEN_AI_REQUEST_MODEL] = log.eval.model
    if digest is not None:
        run_attrs.update(_run_outcome_attrs(digest))
    records = {r.test_id: r for r in digest.records} if digest is not None else {}
    run_span = tracer.start_span(
        f"eval {log.eval.task}", start_time=run_start, attributes=run_attrs
    )
    run_ctx = otrace.set_span_in_context(run_span)
    spans = 1
    run_end = run_start

    for sample in samples:
        events = sample.events or []
        s_start = _ns(events[0].timestamp) if events else run_start
        sample_attrs = {
            GEN_AI_OPERATION_NAME: OP_INVOKE_AGENT,
            GEN_AI_AGENT_NAME: str(sample.id),
            AGON_SAMPLE_ID: str(sample.id),
        }
        rec = records.get(str(sample.id))
        if rec is not None:
            sample_attrs.update(_sample_outcome_attrs(rec))
        sample_span = tracer.start_span(
            f"invoke_agent {sample.id}",
            context=run_ctx,
            start_time=s_start,
            attributes=sample_attrs,
        )
        spans += 1
        s_ctx = otrace.set_span_in_context(sample_span)
        s_end = s_start
        for e in events:
            emitter = _EMITTERS.get(e.event)
            if emitter is not None:
                s_end = max(s_end, emitter(tracer, s_ctx, e))
                spans += 1
        sample_span.end(end_time=s_end)
        run_end = max(run_end, s_end)

    run_span.end(end_time=run_end)
    return spans
