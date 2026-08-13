"""Workflow optimization models and contracts."""

from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
)

from azathoth.workflows.candidate import (
    WorkflowCandidate,
)
from azathoth.workflows.experiment import (
    WorkflowExperimentResult,
)


class WorkflowOptimizationResult(BaseModel):
    """Represent one optimizer-produced workflow generation."""

    model_config = ConfigDict(
        frozen=True,
    )

    generation: int = Field(
        ge=1,
    )

    previous_experiment: WorkflowExperimentResult

    candidates: tuple[
        InstanceOf[WorkflowCandidate],
        ...,
    ] = Field(
        min_length=1,
    )


class WorkflowOptimizer(Protocol):
    """Generate a new workflow population from experiment evidence."""

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Produce the next workflow optimization generation."""

        ...