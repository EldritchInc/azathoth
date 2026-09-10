"""Canonical external workflow input events."""

from pydantic import JsonValue

from azathoth.context import ContextEvent

WORKFLOW_INPUT_EVENT_TYPE = "workflow.input.received"


def create_workflow_input_event(
    payload: JsonValue,
    *,
    producer: str,
) -> ContextEvent:
    """Create one canonical external workflow input event."""

    return ContextEvent(
        event_type=WORKFLOW_INPUT_EVENT_TYPE,
        payload={
            "input": payload,
        },
        producer=producer,
    )


__all__ = [
    "WORKFLOW_INPUT_EVENT_TYPE",
    "create_workflow_input_event",
]
