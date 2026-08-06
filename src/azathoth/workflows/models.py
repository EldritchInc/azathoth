"""Domain models describing model-independent workflows."""

from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.workflows.steps import WorkflowStepSpecification


class WorkflowMetadata(BaseModel):
    """Stable identifying information for a workflow specification."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class WorkflowSpecification(BaseModel):
    """Describe an ordered workflow without runtime dependencies."""

    model_config = ConfigDict(frozen=True)

    metadata: WorkflowMetadata
    steps: tuple[WorkflowStepSpecification, ...] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> Self:
        """Ensure every workflow step has a unique identifier."""

        step_ids = tuple(step.id for step in self.steps)

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step identifiers must be unique.")

        return self

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Self:
        """Ensure workflow dependencies form a valid directed acyclic graph."""

        steps_by_id = {step.id: step for step in self.steps}

        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("Workflow step dependencies must be unique.")

            if step.id in step.depends_on:
                raise ValueError("Workflow steps cannot depend on themselves.")

            for dependency_id in step.depends_on:
                if dependency_id not in steps_by_id:
                    raise ValueError(
                        "Workflow step dependencies must reference steps in the same workflow."
                    )

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(step_id: UUID) -> None:
            """Visit one workflow step while detecting dependency cycles."""

            if step_id in visited:
                return

            if step_id in visiting:
                raise ValueError("Workflow dependency graph must be acyclic.")

            visiting.add(step_id)

            for dependency_id in steps_by_id[step_id].depends_on:
                visit(dependency_id)

            visiting.remove(step_id)
            visited.add(step_id)

        for step in self.steps:
            visit(step.id)

        return self

    def execution_layers(
        self,
    ) -> tuple[tuple[WorkflowStepSpecification, ...], ...]:
        """Return dependency-safe workflow steps grouped into layers."""

        remaining = list(self.steps)
        completed_ids: set[UUID] = set()
        layers: list[tuple[WorkflowStepSpecification, ...]] = []

        while remaining:
            ready = tuple(
                step for step in remaining if set(step.depends_on).issubset(completed_ids)
            )

            if not ready:
                raise RuntimeError(
                    "Validated workflow dependency graph could not produce an execution layer."
                )

            layers.append(ready)

            ready_ids = {step.id for step in ready}
            completed_ids.update(ready_ids)
            remaining = [step for step in remaining if step.id not in ready_ids]

        return tuple(layers)
