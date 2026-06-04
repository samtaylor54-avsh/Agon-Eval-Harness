"""Reporting: Markdown / JSON / JUnit-XML emitters + release recommendation."""

from agon.reporting.generator import (
    generate_reports,
    recommend,
    render_json,
    render_junit_xml,
    render_markdown,
)

__all__ = [
    "generate_reports",
    "recommend",
    "render_json",
    "render_junit_xml",
    "render_markdown",
]
