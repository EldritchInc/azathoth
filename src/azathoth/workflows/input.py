"""Canonical external workflow input events."""

from datetime import UTC, datetime

from pydantic import JsonValue

from azathoth.context import ContextEvent

WORKFLOW_INPUT_EVENT_TYPE = "workflow.input.received"


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


__all__ = [
    "WORKFLOW_INPUT_EVENT_TYPE",
    "create_workflow_input_event",
]
