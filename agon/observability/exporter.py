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
    AGON_RUN_ID,
    AGON_SAMPLE_ID,
    AGON_SCORE_VALUE,
    AGON_SCORER,
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

_MIN_DUR_NS = 1_000_000  # 1ms span for point-in-time events


def _ns(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return int(ts.timestamp() * 1_000_000_000)


def _strval(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    return str(value)


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
        span.set_status(Status(StatusCode.ERROR, str(e.error)))
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


def export_eval_log(log: Any, tracer: Any) -> int:
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
    run_span = tracer.start_span(
        f"eval {log.eval.task}", start_time=run_start, attributes=run_attrs
    )
    run_ctx = otrace.set_span_in_context(run_span)
    spans = 1
    run_end = run_start

    for sample in samples:
        events = sample.events or []
        s_start = _ns(events[0].timestamp) if events else run_start
        sample_span = tracer.start_span(
            f"invoke_agent {sample.id}",
            context=run_ctx,
            start_time=s_start,
            attributes={
                GEN_AI_OPERATION_NAME: OP_INVOKE_AGENT,
                GEN_AI_AGENT_NAME: str(sample.id),
                AGON_SAMPLE_ID: str(sample.id),
            },
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
