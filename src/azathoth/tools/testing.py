"""Domain models describing durable tool verification."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ToolTestCase(BaseModel):
    """Describe a deterministic verification case for a tool."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    tool_id: UUID
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: dict[str, JsonValue]
    expected_output: dict[str, JsonValue]
