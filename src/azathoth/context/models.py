"""Event-backed context models used during Azathoth executions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class ContextEvent(BaseModel):
    """A single traceable contribution to the working context."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    producer: str = Field(min_length=1)
    provenance: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    occurred_at: datetime = Field(default_factory=utc_now)


class Context(BaseModel):
    """An immutable, ordered history of context events."""

    model_config = ConfigDict(frozen=True)

    events: tuple[ContextEvent, ...] = ()

    def append(self, event: ContextEvent) -> "Context":
        """Return a new context containing the additional event."""

        return self.model_copy(update={"events": (*self.events, event)})

    def by_type(self, event_type: str) -> tuple[ContextEvent, ...]:
        """Return all events matching the supplied event type."""

        return tuple(event for event in self.events if event.event_type == event_type)

    def latest(self, event_type: str) -> ContextEvent | None:
        """Return the most recent matching event, if one exists."""

        for event in reversed(self.events):
            if event.event_type == event_type:
                return event

        return None
