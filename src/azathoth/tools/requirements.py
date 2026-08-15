"""Domain models describing durable tool requirements."""

from pydantic import BaseModel, ConfigDict, Field


class ToolRequirement(BaseModel):
    """Describe one required tool capability."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    version: str | None = None
    runtime: str | None = None


class ToolRequirements(BaseModel):
    """Describe required tool capabilities."""

    model_config = ConfigDict(frozen=True)

    requirements: tuple[ToolRequirement, ...] = ()


class ToolRequirementMatch(BaseModel):
    """Describe a successful tool requirement match."""

    model_config = ConfigDict(frozen=True)

    requirement: ToolRequirement
    matched: bool
