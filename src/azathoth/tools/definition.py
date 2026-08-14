"""Domain models describing durable tool contracts."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ToolInputSchema(BaseModel):
    """Describe the structured input accepted by a tool."""

    model_config = ConfigDict(frozen=True)

    json_schema: dict[str, JsonValue]


class ToolOutputSchema(BaseModel):
    """Describe the structured output produced by a tool."""

    model_config = ConfigDict(frozen=True)

    json_schema: dict[str, JsonValue]


class ToolDefinition(BaseModel):
    """Describe a durable, versioned tool capability."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    input_schema: ToolInputSchema
    output_schema: ToolOutputSchema
