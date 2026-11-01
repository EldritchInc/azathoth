"""Tests for the tracing interface and its no-op default (ADR 0100)."""

import pytest

from azathoth.telemetry import (
    NO_SPAN,
    NO_TELEMETRY,
    NoTelemetry,
    Telemetry,
    active_telemetry,
    traced,
    use_telemetry,
)
from tests.telemetry.fakes import RecordingTelemetry


def test_no_telemetry_is_disabled_and_records_nothing() -> None:
    telemetry: Telemetry = NoTelemetry()

    span = telemetry.start_span("azathoth.run", {"azathoth.run.id": "x"})

    assert telemetry.enabled is False
    assert span is NO_SPAN
    assert telemetry.trace_context() == {}
    assert telemetry.trace_context(span) == {}

    span.set_attributes({"a": 1})
    span.add_event("e", {"b": 2})
    span.set_error("ValueError")
    span.end()

    telemetry.deactivate(telemetry.activate(span))
    telemetry.shutdown()


def test_no_telemetry_is_the_default() -> None:
    assert active_telemetry() is NO_TELEMETRY


def test_use_telemetry_replaces_and_returns_the_previous_one() -> None:
    recording = RecordingTelemetry()

    previous = use_telemetry(recording)

    try:
        assert previous is NO_TELEMETRY
        assert active_telemetry() is recording
    finally:
        assert use_telemetry(previous) is recording

    assert active_telemetry() is NO_TELEMETRY


def test_traced_runs_a_block_inside_one_current_span() -> None:
    telemetry = RecordingTelemetry()

    with traced(telemetry, "azathoth.run", {"azathoth.run.id": "r"}) as span:
        child = telemetry.start_span("azathoth.step")
        child.end()

        assert telemetry.trace_context() != {}

    assert telemetry.trace_context() == {}

    (run, step) = telemetry.spans

    assert run is span
    assert run.attributes == {"azathoth.run.id": "r"}
    assert run.ended and run.error_type is None
    assert step.parent is run


def test_traced_marks_the_span_failed_by_type_and_raises_again() -> None:
    telemetry = RecordingTelemetry()

    with pytest.raises(KeyError), traced(telemetry, "azathoth.run"):
        raise KeyError("a customer's name")

    (span,) = telemetry.spans

    assert span.error_type == "KeyError"
    assert span.ended
    assert "customer" not in repr(span.attributes)
    assert telemetry.trace_context() == {}
