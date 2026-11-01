"""Tests for continuing a trace in a child `azathoth` (ADR 0100).

They need the `otel` extra, which the `dev` extra installs.
"""

import sys

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import ReadableSpan  # noqa: E402
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from azathoth.standard import standard_tool_documents  # noqa: E402
from azathoth.telemetry import use_telemetry  # noqa: E402
from azathoth.telemetry.otel import OpenTelemetryTelemetry  # noqa: E402
from azathoth.telemetry.sdk import sdk_telemetry, span_exporter  # noqa: E402
from azathoth.tools.environment import process_tool_environment  # noqa: E402

PARENT_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "AZATHOTH_DATABASE": "/var/azathoth/azathoth.db",
    "OPENROUTER_API_KEY": "sk-or-secret",
    "AZATHOTH_OTEL": "1",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
    "OTEL_SERVICE_NAME": "support",
    "TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
}


def exported(
    environ: dict[str, str],
) -> tuple[OpenTelemetryTelemetry, InMemorySpanExporter]:
    """Return SDK telemetry exporting to memory, and the exporter."""

    exporter = InMemorySpanExporter()

    return sdk_telemetry(environ, processor=SimpleSpanProcessor(exporter)), exporter


def only(
    exporter: InMemorySpanExporter,
    name: str,
) -> ReadableSpan:
    """Return the one finished span with a name."""

    (span,) = (span for span in exporter.get_finished_spans() if span.name == name)

    return span


@pytest.mark.parametrize("name", ["run_workflow", "loop_workflow"])
def test_a_child_started_by_a_standard_tool_continues_the_trace_under_its_step(
    name: str,
) -> None:
    (document,) = (
        document for document in standard_tool_documents() if document.definition.name == name
    )
    (implementation,) = document.implementations

    parent, parent_exporter = exported({})
    previous = use_telemetry(parent)

    try:
        run = parent.start_span("azathoth.run")
        step = parent.start_span("azathoth.step", parent=run)
        token = parent.activate(step)

        try:
            child_environment = process_tool_environment(
                implementation,
                PARENT_ENVIRONMENT,
                windows=False,
            )
        finally:
            parent.deactivate(token)

        step.end()
        run.end()
    finally:
        use_telemetry(previous)
        parent.shutdown()

    assert child_environment["AZATHOTH_OTEL"] == "1"
    assert child_environment["OTEL_SERVICE_NAME"] == "support"
    assert child_environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://collector:4318"

    child, child_exporter = exported(child_environment)

    child.start_span("azathoth.invocation").end()
    child.shutdown()

    step_span = only(parent_exporter, "azathoth.step")
    invocation_span = only(child_exporter, "azathoth.invocation")

    assert invocation_span.context.trace_id == step_span.context.trace_id
    assert invocation_span.parent is not None
    assert invocation_span.parent.span_id == step_span.context.span_id


def test_the_console_exporter_writes_to_stderr() -> None:
    exporter = span_exporter({"OTEL_TRACES_EXPORTER": "console"})

    assert isinstance(exporter, ConsoleSpanExporter)
    assert exporter.out is sys.stderr
