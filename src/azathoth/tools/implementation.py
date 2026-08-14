"""Domain models describing durable tool implementations."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ToolImplementation(BaseModel):
    """Describe a versioned executable implementation of a tool."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    tool_id: UUID
    tool_version: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    runtime: str = Field(min_length=1)
    source: str = Field(min_length=1)
