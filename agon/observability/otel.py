"""Tracer + exporter configuration. The [otel] extra provides the SDK.

Backends: in-memory (tests), console (offline demo), LangSmith (OTLP /otel), generic OTLP.
"""

from __future__ import annotations

import os
from typing import Any

SERVICE_NAME = "agon-eval-harness"


def _build_tracer(exporter: Any, *, service_name: str = SERVICE_NAME) -> Any:
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("agon.observability")


def in_memory_tracer() -> tuple[Any, Any]:
    """Return (tracer, exporter) backed by an in-memory span store — for tests."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    return _build_tracer(exporter), exporter


def console_tracer() -> Any:
    """Tracer that prints spans to stdout — an offline observability demo (no account)."""
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return _build_tracer(ConsoleSpanExporter())


def otlp_tracer(endpoint: str, headers: dict[str, str] | None = None) -> Any:
    """Tracer exporting to any OTLP/HTTP endpoint (e.g. a Grafana Tempo collector)."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return _build_tracer(OTLPSpanExporter(endpoint=endpoint, headers=headers or {}))


def langsmith_tracer(
    api_key: str | None = None,
    *,
    endpoint: str | None = None,
    project: str | None = None,
) -> Any:
    """Tracer exporting GenAI spans to LangSmith's OTLP endpoint (no LangChain SDK needed).

    Reads ``LANGSMITH_API_KEY`` / ``OTEL_EXPORTER_OTLP_ENDPOINT`` / ``LANGSMITH_PROJECT`` from the
    environment when arguments are omitted.
    """
    key = api_key or os.environ.get("LANGSMITH_API_KEY")
    if not key:
        raise ValueError("LangSmith export requires LANGSMITH_API_KEY (or api_key=...)")
    base = endpoint or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.smith.langchain.com/otel"
    )
    # OTLP/HTTP traces are posted to <base>/v1/traces.
    url = base.rstrip("/") + "/v1/traces"
    headers = {"x-api-key": key}
    proj = project or os.environ.get("LANGSMITH_PROJECT")
    if proj:
        headers["Langsmith-Project"] = proj
    return otlp_tracer(url, headers)
