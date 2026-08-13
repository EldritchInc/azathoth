"""Workflow optimization session models."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    model_validator,
)

from azathoth.optimization.workflow import WorkflowOptimizationResult
from azathoth.workflows.candidate import WorkflowCandidate


class WorkflowOptimizationSession(BaseModel):
    """Record the generations produced during workflow optimization."""

    model_config = ConfigDict(
        frozen=True,
    )

    initial_candidates: tuple[
        InstanceOf[WorkflowCandidate],
        ...,
    ] = Field(
        min_length=1,
    )

    generations: tuple[WorkflowOptimizationResult, ...] = ()

    @model_validator(mode="after")
    def validate_generation_sequence(self) -> "WorkflowOptimizationSession":
        """Ensure optimization generations are consecutive starting at one."""

        actual_generations = tuple(generation.generation for generation in self.generations)
        expected_generations = tuple(
            range(
                1,
                len(self.generations) + 1,
            )
        )

        if actual_generations != expected_generations:
            raise ValueError("Workflow optimization generations must be consecutive starting at 1.")

        return self
