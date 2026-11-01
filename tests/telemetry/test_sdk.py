"""Tests for exporting through the OpenTelemetry SDK (ADR 0100).

They need the `otel` extra, which the `dev` extra installs.
"""

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import ReadableSpan  # noqa: E402
from opentelemetry.sdk.trace.export import (  # noqa: E402
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode  # noqa: E402

from azathoth import __version__  # noqa: E402
from azathoth.telemetry import (  # noqa: E402
    OTEL_ENABLED_VARIABLE,
    configure_from_environment,
    traced,
)
from azathoth.telemetry.otel import TRACEPARENT_VARIABLE, OpenTelemetryTelemetry  # noqa: E402
from azathoth.telemetry.sdk import (  # noqa: E402
    DEFAULT_SERVICE_NAME,
    TelemetryConfigurationError,
    sdk_telemetry,
    service_resource,
    span_exporter,
)

PARENT_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"

TRACEPARENT = f"00-{PARENT_TRACE_ID}-00f067aa0ba902b7-01"


def exported(
    environ: dict[str, str] | None = None,
) -> tuple[OpenTelemetryTelemetry, InMemorySpanExporter]:
    """Return SDK telemetry exporting to memory, and the exporter."""

    exporter = InMemorySpanExporter()

    return (
        sdk_telemetry(environ or {}, processor=SimpleSpanProcessor(exporter)),
        exporter,
    )


def finished(
    exporter: InMemorySpanExporter,
) -> tuple[ReadableSpan, ...]:
    """Return the spans an exporter received."""

    return tuple(exporter.get_finished_spans())


def test_tracing_on_configures_sdk_telemetry() -> None:
    telemetry = configure_from_environment(
        {OTEL_ENABLED_VARIABLE: "1", "OTEL_TRACES_EXPORTER": "none"},
    )

    assert isinstance(telemetry, OpenTelemetryTelemetry)
    assert telemetry.enabled

    telemetry.shutdown()


def test_spans_are_exported_with_their_parents_and_attributes() -> None:
    telemetry, exporter = exported()

    with traced(telemetry, "azathoth.run", {"azathoth.run.id": "r"}):
        step = telemetry.start_span("azathoth.step", {"azathoth.step.attempts": 1})
        step.set_error("ValueError")
        step.end()

    telemetry.shutdown()

    step_span, run_span = finished(exporter)

    assert run_span.name == "azathoth.run"
    assert dict(run_span.attributes or {}) == {"azathoth.run.id": "r"}
    assert step_span.parent is not None
    assert step_span.parent.span_id == run_span.context.span_id
    assert step_span.status.status_code is StatusCode.ERROR
    assert dict(step_span.attributes or {})["error.type"] == "ValueError"
    assert len(step_span.events) == 0


def test_an_inherited_traceparent_continues_its_trace() -> None:
    telemetry, exporter = exported({TRACEPARENT_VARIABLE: TRACEPARENT})

    telemetry.start_span("azathoth.run").end()
    telemetry.shutdown()

    (span,) = finished(exporter)

    assert f"{span.context.trace_id:032x}" == PARENT_TRACE_ID


def test_the_service_is_azathoth_by_default() -> None:
    attributes = dict(service_resource({}).attributes)

    assert attributes["service.name"] == DEFAULT_SERVICE_NAME == "azathoth"
    assert attributes["service.version"] == __version__


def test_an_explicit_service_name_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "triage-worker")

    attributes = dict(service_resource({"OTEL_SERVICE_NAME": "triage-worker"}).attributes)

    assert attributes["service.name"] == "triage-worker"


def test_the_exporter_is_otlp_over_http_by_default() -> None:
    exporter = span_exporter({})

    assert type(exporter).__module__ == "opentelemetry.exporter.otlp.proto.http.trace_exporter"


def test_the_console_and_no_exporters_are_supported() -> None:
    assert isinstance(span_exporter({"OTEL_TRACES_EXPORTER": "console"}), ConsoleSpanExporter)
    assert span_exporter({"OTEL_TRACES_EXPORTER": "none"}) is None


@pytest.mark.parametrize("name", ["zipkin", "otlp,console", "jaeger"])
def test_other_exporters_are_refused(
    name: str,
) -> None:
    with pytest.raises(TelemetryConfigurationError, match="supported exporters: otlp, console"):
        span_exporter({"OTEL_TRACES_EXPORTER": name})
