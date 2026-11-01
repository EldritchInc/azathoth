"""Tests for telemetry backed by the OpenTelemetry API (ADR 0100).

These need only `opentelemetry-api`, so they run with a fake API tracer.
"""

from datetime import UTC, datetime

import pytest
from opentelemetry.trace import StatusCode

from azathoth.telemetry import NO_SPAN, traced
from azathoth.telemetry.otel import (
    TRACEPARENT_VARIABLE,
    TRACESTATE_VARIABLE,
    OpenTelemetrySpan,
    OpenTelemetryTelemetry,
    extract_trace_context,
)
from tests.telemetry.fakes import FakeApiSpan, FakeApiTracer

PARENT_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"

PARENT_SPAN_ID = "00f067aa0ba902b7"

TRACEPARENT = f"00-{PARENT_TRACE_ID}-{PARENT_SPAN_ID}-01"

MOMENT = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)

MOMENT_NS = 1_793_534_400_000_000_000


def telemetry(
    environ: dict[str, str] | None = None,
) -> tuple[OpenTelemetryTelemetry, FakeApiTracer]:
    """Return telemetry over a fake API tracer, and the tracer."""

    tracer = FakeApiTracer()

    return (
        OpenTelemetryTelemetry(
            tracer,
            parent_context=extract_trace_context(environ or {}),
        ),
        tracer,
    )


def api_span(
    span: object,
) -> FakeApiSpan:
    """Return the fake API span behind one Azathoth span."""

    assert isinstance(span, OpenTelemetrySpan)
    assert isinstance(span.span, FakeApiSpan)

    return span.span


def test_opentelemetry_telemetry_is_enabled() -> None:
    assert telemetry()[0].enabled is True


def test_a_span_carries_its_name_attributes_and_times() -> None:
    otel, tracer = telemetry()

    span = otel.start_span("azathoth.run", {"azathoth.run.id": "r"}, start_time=MOMENT)
    span.end(end_time=MOMENT)

    (recorded,) = tracer.spans

    assert recorded.name == "azathoth.run"
    assert recorded.attributes == {"azathoth.run.id": "r"}
    assert recorded.start_time == MOMENT_NS
    assert recorded.end_time == MOMENT_NS
    assert recorded.ended


def test_attributes_and_events_reach_the_span() -> None:
    otel, _ = telemetry()

    span = otel.start_span("azathoth.step")
    span.set_attributes({"azathoth.step.attempts": 2})
    span.add_event("azathoth.attempt.failed", {"azathoth.attempt.number": 1}, timestamp=MOMENT)

    recorded = api_span(span)

    assert recorded.attributes == {"azathoth.step.attempts": 2}
    assert [(event.name, event.attributes, event.timestamp) for event in recorded.events] == [
        ("azathoth.attempt.failed", {"azathoth.attempt.number": 1}, MOMENT_NS)
    ]


def test_an_error_sets_the_status_and_type_and_records_no_exception() -> None:
    otel, _ = telemetry()

    span = otel.start_span("azathoth.step")
    span.set_error("PromptOutputFormatError")

    recorded = api_span(span)

    assert recorded.status is not None
    assert recorded.status.status_code is StatusCode.ERROR
    assert recorded.status.description is None
    assert recorded.attributes == {"error.type": "PromptOutputFormatError"}


def test_a_span_without_a_parent_is_a_root_when_nothing_is_inherited() -> None:
    otel, tracer = telemetry()

    otel.start_span("azathoth.run")

    assert tracer.spans[0].parent is None


def test_an_explicit_parent_is_used() -> None:
    otel, tracer = telemetry()

    run = otel.start_span("azathoth.run")
    otel.start_span("azathoth.step", parent=run)

    assert tracer.spans[1].parent == api_span(run).context


def test_the_current_span_is_the_default_parent() -> None:
    otel, tracer = telemetry()

    run = otel.start_span("azathoth.run")
    token = otel.activate(run)

    try:
        otel.start_span("azathoth.step")
    finally:
        otel.deactivate(token)

    otel.start_span("azathoth.run")

    assert tracer.spans[1].parent == api_span(run).context
    assert tracer.spans[2].parent is None


def test_an_inherited_traceparent_parents_the_first_span() -> None:
    otel, tracer = telemetry({TRACEPARENT_VARIABLE: TRACEPARENT})

    run = otel.start_span("azathoth.run")
    token = otel.activate(run)

    try:
        otel.start_span("azathoth.step")
    finally:
        otel.deactivate(token)

    (first, second) = tracer.spans

    assert first.parent is not None
    assert f"{first.parent.trace_id:032x}" == PARENT_TRACE_ID
    assert f"{first.parent.span_id:016x}" == PARENT_SPAN_ID
    assert f"{first.context.trace_id:032x}" == PARENT_TRACE_ID
    assert second.parent == first.context


@pytest.mark.parametrize("value", ["", "garbage", "00-0-0-01"])
def test_an_unusable_traceparent_is_ignored(
    value: str,
) -> None:
    assert extract_trace_context({TRACEPARENT_VARIABLE: value}) is None


def test_trace_context_names_the_current_span() -> None:
    otel, _ = telemetry()

    run = otel.start_span("azathoth.run")

    assert otel.trace_context() == {}

    with traced(otel, "azathoth.step") as step:
        context = otel.trace_context()

    recorded = api_span(step).context

    assert context == {
        TRACEPARENT_VARIABLE: f"00-{recorded.trace_id:032x}-{recorded.span_id:016x}-01",
    }
    assert TRACESTATE_VARIABLE not in context
    assert otel.trace_context(run)[TRACEPARENT_VARIABLE].endswith(
        f"-{api_span(run).context.span_id:016x}-01"
    )


def test_a_foreign_span_is_refused() -> None:
    otel, _ = telemetry()

    with pytest.raises(TypeError, match="only accepts spans it started"):
        otel.activate(NO_SPAN)


def test_shutdown_calls_the_providers_shutdown() -> None:
    calls: list[str] = []

    otel = OpenTelemetryTelemetry(FakeApiTracer(), shutdown=lambda: calls.append("shutdown"))

    otel.shutdown()

    assert calls == ["shutdown"]


def test_shutdown_without_a_provider_does_nothing() -> None:
    telemetry()[0].shutdown()
