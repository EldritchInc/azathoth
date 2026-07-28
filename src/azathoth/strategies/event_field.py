"""A deterministic strategy for extracting data from structured context."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import Context, ContextEvent
from azathoth.strategies.exceptions import (
    RequiredEventNotFoundError,
    RequiredFieldNotFoundError,
)
from azathoth.strategies.models import StrategyMetadata, StrategyOutcome


class EventFieldStrategy(BaseModel):
    """Extract a field from the latest event of a configured type."""

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    event_type: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    output_event_type: str | None = None

    async def run(self, context: Context) -> StrategyOutcome:
        """Extract the configured field from the latest matching event."""

        source_event = context.latest(self.event_type)

        if source_event is None:
            raise RequiredEventNotFoundError(
                f"No context event found with type {self.event_type!r}."
            )

        if self.field_name not in source_event.payload:
            raise RequiredFieldNotFoundError(
                f"Context event {self.event_type!r} does not contain field {self.field_name!r}."
            )

        output = source_event.payload[self.field_name]

        if self.output_event_type is None:
            return StrategyOutcome(output=output)

        output_event = ContextEvent(
            event_type=self.output_event_type,
            payload={
                "value": output,
                "source_event_id": str(source_event.id),
                "source_event_type": source_event.event_type,
                "source_field": self.field_name,
            },
            producer=str(self.metadata.id),
            provenance=str(source_event.id),
            confidence=source_event.confidence,
        )

        return StrategyOutcome(
            output=output,
            events=(output_event,),
        )
