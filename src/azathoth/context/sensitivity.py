"""The sensitivity a run's input was labelled with, recorded in its initial context (ADR 0123)."""

from datetime import UTC, datetime
from typing import Final

from azathoth.context.models import Context, ContextEvent
from azathoth.sensitivity import Sensitivity

INPUT_SENSITIVITY_EVENT_TYPE: Final = "workflow.input.sensitivity"
"""The event type of the label a run's input was given."""

SENSITIVITY_PAYLOAD_KEY: Final = "sensitivity"
"""The key of the label in a sensitivity event's payload."""


def create_input_sensitivity_event(
    sensitivity: Sensitivity,
    *,
    producer: str,
    occurred_at: datetime | None = None,
) -> ContextEvent:
    """Create the event that records the label a run's input was given."""

    return ContextEvent(
        event_type=INPUT_SENSITIVITY_EVENT_TYPE,
        payload={SENSITIVITY_PAYLOAD_KEY: sensitivity.value},
        producer=producer,
        occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC),
    )


def input_sensitivities(
    context: Context,
) -> tuple[Sensitivity, ...]:
    """Return every label a context records its input was given, in order.

    Raises:
        ValueError: A sensitivity event holds no label Azathoth knows.
    """

    labels: list[Sensitivity] = []

    for event in context.by_type(INPUT_SENSITIVITY_EVENT_TYPE):
        value = event.payload.get(SENSITIVITY_PAYLOAD_KEY)

        try:
            labels.append(Sensitivity(str(value)))
        except ValueError as exc:
            raise ValueError(
                f"A {INPUT_SENSITIVITY_EVENT_TYPE} event holds no label Azathoth knows: {value!r}."
            ) from exc

    return tuple(labels)


__all__ = [
    "INPUT_SENSITIVITY_EVENT_TYPE",
    "SENSITIVITY_PAYLOAD_KEY",
    "create_input_sensitivity_event",
    "input_sensitivities",
]
