"""Domain models used to define Azathoth optimization jobs."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.context import Context
from azathoth.evaluation import EvaluationResult, ExpectedOutcome
from azathoth.execution import ExecutionResult
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


class OptimizationRun(BaseModel):
    """The complete result of executing and evaluating one strategy."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    example_id: UUID
    execution: ExecutionResult
    evaluation: EvaluationResult
    started_at: datetime
    completed_at: datetime

    @model_validator(mode="after")
    def validate_completion_time(self) -> "OptimizationRun":
        """Ensure the run does not complete before it starts."""

        if self.completed_at < self.started_at:
            raise ValueError("Optimization run cannot complete before it starts.")

        return self

    @property
    def passed(self) -> bool:
        """Return whether the evaluated strategy run passed."""

        return self.evaluation.passed
