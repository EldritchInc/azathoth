"""Tests for the trace context a process tool receives (ADR 0100)."""

import asyncio
import sys
from collections.abc import Iterator
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.telemetry import NO_TELEMETRY, use_telemetry
from azathoth.tools import (
    MANAGED_ENVIRONMENT_VARIABLES,
    PROCESS_TOOL_RUNTIME,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    TRACE_CONTEXT_ENVIRONMENT_VARIABLES,
    TRACEPARENT_ENVIRONMENT_VARIABLE,
    TRACESTATE_ENVIRONMENT_VARIABLE,
    ProcessToolExecutor,
    ToolImplementation,
)
from azathoth.tools.environment import process_tool_environment
from tests.telemetry.fakes import RecordingTelemetry

TOOL_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b01")

IMPLEMENTATION_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b11")

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

TRACESTATE = "vendor=opaque"

INHERITED = {
    "PATH": "/usr/bin:/bin",
    "TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    "TRACESTATE": "inherited=1",
}

TRACE_SCRIPT = (
    "import json, os\n"
    "print(json.dumps({name: os.environ.get(name) for name in ('TRACEPARENT', 'TRACESTATE')}))\n"
)


def create_implementation(
    *,
    environment: tuple[str, ...] = (),
    source: str = "print('{}')\n",
) -> ToolImplementation:
    """Create one process implementation with the given grants."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=source,
        command=(sys.executable,),
        environment=environment,
    )


@pytest.fixture
def telemetry() -> Iterator[RecordingTelemetry]:
    """Make a recording telemetry the active one, restoring the previous one after."""

    recording = RecordingTelemetry()
    previous = use_telemetry(recording)

    try:
        yield recording
    finally:
        use_telemetry(previous)


# The managed variables


def test_the_engine_manages_the_timeout_and_the_trace_context() -> None:
    assert TRACEPARENT_ENVIRONMENT_VARIABLE == "TRACEPARENT"
    assert TRACESTATE_ENVIRONMENT_VARIABLE == "TRACESTATE"
    assert TRACE_CONTEXT_ENVIRONMENT_VARIABLES == ("TRACEPARENT", "TRACESTATE")
    assert MANAGED_ENVIRONMENT_VARIABLES == (
        PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
        "TRACEPARENT",
        "TRACESTATE",
    )


def test_the_tools_and_the_tracer_name_the_same_variables() -> None:
    otel = pytest.importorskip("azathoth.telemetry.otel")

    assert otel.TRACEPARENT_VARIABLE == TRACEPARENT_ENVIRONMENT_VARIABLE
    assert otel.TRACESTATE_VARIABLE == TRACESTATE_ENVIRONMENT_VARIABLE


@pytest.mark.parametrize("grant", ["TRACEPARENT", "TRACESTATE"])
def test_the_trace_context_cannot_be_granted(
    grant: str,
) -> None:
    with pytest.raises(ValueError, match=f"{grant} is set by the engine from the active trace"):
        create_implementation(environment=(grant,))


# Building the environment


def test_an_inherited_trace_context_never_reaches_a_tool() -> None:
    environment = process_tool_environment(
        create_implementation(environment=("TRACE*",)),
        INHERITED,
        windows=False,
        trace_context={},
    )

    assert environment == {"PATH": "/usr/bin:/bin"}


def test_an_inherited_trace_context_is_stripped_in_any_case_on_windows() -> None:
    environment = process_tool_environment(
        create_implementation(environment=("TRACE*", "traceparent")),
        {"Path": "C:\\Windows", "traceparent": TRACEPARENT, "TraceState": TRACESTATE},
        windows=True,
        trace_context={},
    )

    assert environment == {"Path": "C:\\Windows"}


def test_a_traced_step_gives_its_tool_its_own_trace_context() -> None:
    environment = process_tool_environment(
        create_implementation(),
        INHERITED,
        windows=False,
        trace_context={"TRACEPARENT": TRACEPARENT, "TRACESTATE": TRACESTATE},
    )

    assert environment == {
        "PATH": "/usr/bin:/bin",
        "TRACEPARENT": TRACEPARENT,
        "TRACESTATE": TRACESTATE,
    }


def test_an_empty_tracestate_is_left_out() -> None:
    environment = process_tool_environment(
        create_implementation(),
        {},
        windows=False,
        trace_context={"TRACEPARENT": TRACEPARENT, "TRACESTATE": ""},
    )

    assert environment == {"TRACEPARENT": TRACEPARENT}


def test_only_the_trace_context_is_taken_from_the_trace() -> None:
    environment = process_tool_environment(
        create_implementation(),
        {},
        windows=False,
        trace_context={"TRACEPARENT": TRACEPARENT, "BAGGAGE": "user=jane"},
    )

    assert environment == {"TRACEPARENT": TRACEPARENT}


def test_the_trace_context_defaults_to_the_active_telemetrys_current_span(
    telemetry: RecordingTelemetry,
) -> None:
    span = telemetry.start_span("azathoth.step")
    token = telemetry.activate(span)

    try:
        environment = process_tool_environment(create_implementation(), INHERITED, windows=False)
    finally:
        telemetry.deactivate(token)

    assert environment["TRACEPARENT"] == telemetry.trace_context(span)["TRACEPARENT"]
    assert "TRACESTATE" not in environment


def test_without_a_current_span_a_tool_receives_no_trace_context(
    telemetry: RecordingTelemetry,
) -> None:
    environment = process_tool_environment(create_implementation(), INHERITED, windows=False)

    assert environment == {"PATH": "/usr/bin:/bin"}


def test_without_tracing_a_tool_receives_no_trace_context() -> None:
    previous = use_telemetry(NO_TELEMETRY)

    try:
        environment = process_tool_environment(create_implementation(), INHERITED, windows=False)
    finally:
        use_telemetry(previous)

    assert environment == {"PATH": "/usr/bin:/bin"}


# A real subprocess


def test_a_real_process_sees_its_steps_trace_context(
    telemetry: RecordingTelemetry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACEPARENT", INHERITED["TRACEPARENT"])
    monkeypatch.setenv("TRACESTATE", INHERITED["TRACESTATE"])

    span = telemetry.start_span("azathoth.step")

    async def execute() -> dict[str, JsonValue]:
        token = telemetry.activate(span)

        try:
            return await ProcessToolExecutor().execute(
                create_implementation(source=TRACE_SCRIPT),
                {},
            )
        finally:
            telemetry.deactivate(token)

    assert asyncio.run(execute()) == {
        "TRACEPARENT": telemetry.trace_context(span)["TRACEPARENT"],
        "TRACESTATE": None,
    }


def test_a_real_process_outside_a_trace_sees_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACEPARENT", INHERITED["TRACEPARENT"])

    output = asyncio.run(
        ProcessToolExecutor().execute(create_implementation(source=TRACE_SCRIPT), {})
    )

    assert output == {"TRACEPARENT": None, "TRACESTATE": None}
