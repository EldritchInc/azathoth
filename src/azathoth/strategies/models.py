"""Domain models shared by executable Azathoth strategies."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from azathoth.context import ContextEvent


class StrategyMetadata(BaseModel):
    """Stable identifying information for an executable strategy."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class StrategyOutcome(BaseModel):
    """The direct output produced by a strategy implementation."""

    model_config = ConfigDict(frozen=True)

    output: JsonValue
    events: tuple[ContextEvent, ...] = ()
