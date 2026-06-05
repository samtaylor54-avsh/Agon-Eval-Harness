"""Observability: export Agon eval runs as OpenTelemetry GenAI spans (Phase 2 M3).

Inspect AI does not emit OpenTelemetry, so we export *post-hoc* from the immutable EvalLog —
walking its model / tool / score events into a ``gen_ai.*`` span tree. This is deterministic
and testable (in-memory exporter) and avoids coupling to live-async tracing internals.

Backends: console (offline, no account), LangSmith (OTLP ``/otel``), or any OTLP collector
(e.g. Grafana Tempo). All opt-in — never on the offline default eval path.
"""

from agon.observability.exporter import export_eval_log
from agon.observability.otel import (
    console_tracer,
    in_memory_tracer,
    langsmith_tracer,
    otlp_tracer,
)

__all__ = [
    "console_tracer",
    "export_eval_log",
    "in_memory_tracer",
    "langsmith_tracer",
    "otlp_tracer",
]
