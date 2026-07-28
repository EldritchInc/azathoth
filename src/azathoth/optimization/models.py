"""Domain models used to define Azathoth optimization jobs."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import Context
from azathoth.evaluation import ExpectedOutcome
from azathoth.goals import Goal


class OptimizationExample(BaseModel):
    """A reproducible example of a goal, context, and expected result."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    goal: Goal
    context: Context
    expected_outcome: ExpectedOutcome
    tags: tuple[str, ...] = ()
