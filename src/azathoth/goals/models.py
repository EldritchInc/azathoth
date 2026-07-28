"""Domain models describing what Azathoth is trying to accomplish."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    """A desired outcome against which strategies can be evaluated."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    success_criteria: tuple[str, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = ()
