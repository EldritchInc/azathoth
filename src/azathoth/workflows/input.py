"""Canonical external workflow input events."""

from datetime import UTC, datetime

from pydantic import JsonValue

from azathoth.context import ContextEvent
from azathoth.inputs import ResolvedInput

WORKFLOW_INPUT_EVENT_TYPE = "workflow.input.received"

WORKFLOW_INPUT_RESOLVED_EVENT_TYPE = "workflow.input.resolved"


def create_workflow_input_event(
    payload: JsonValue,
    *,
    producer: str,
    occurred_at: datetime | None = None,
) -> ContextEvent:
    """Create one canonical external workflow input event.

    Every source of external input, benchmark cases and production
    invocations alike, emits this event, so a workflow binding its prompt to
    the workflow input renders the same way wherever its input comes from.
    Without an explicit time, the event occurs now.
    """

    return ContextEvent(
        event_type=WORKFLOW_INPUT_EVENT_TYPE,
        payload={
            "input": payload,
        },
        producer=producer,
        occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC),
    )


def create_workflow_input_events(
    resolved: ResolvedInput,
    *,
    producer: str,
    occurred_at: datetime | None = None,
) -> tuple[ContextEvent, ...]:
    """Create the events that deliver one resolved input to a run (ADR 0096).

    The canonical input event holds the resolved value, exactly as for a
    JSON input. When the input was a reference, a `workflow.input.resolved`
    event follows it, at the same time and from the same producer, recording
    the reference's URI, media type, size and content digest. An inline input
    adds no event, so its run records exactly the context it always has.
    """

    occurred = occurred_at if occurred_at is not None else datetime.now(UTC)

    input_event = create_workflow_input_event(
        resolved.value,
        producer=producer,
        occurred_at=occurred,
    )

    if resolved.provenance is None:
        return (input_event,)

    return (
        input_event,
        ContextEvent(
            event_type=WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
            payload=resolved.provenance.model_dump(mode="json"),
            producer=producer,
            occurred_at=occurred,
        ),
    )


__all__ = [
    "WORKFLOW_INPUT_EVENT_TYPE",
    "WORKFLOW_INPUT_RESOLVED_EVENT_TYPE",
    "create_workflow_input_event",
    "create_workflow_input_events",
]
