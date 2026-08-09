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
        """Ensure workflow dependencies and value references are valid."""

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

        for step in self.steps:
            output_names = tuple(binding.name for binding in step.outputs)

            if len(output_names) != len(set(output_names)):
                raise ValueError(
                    "Workflow step output names must be unique within each producer step."
                )

            input_names = tuple(binding.name for binding in step.inputs)

            if len(input_names) != len(set(input_names)):
                raise ValueError(
                    "Workflow step input names must be unique within each consumer step."
                )

            upstream_step_ids = self._upstream_step_ids(step)

            for input_binding in step.inputs:
                producer_step_id = input_binding.source.producer_step_id

                if producer_step_id not in steps_by_id:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "a producer step in the same workflow."
                    )

                producer = steps_by_id[producer_step_id]

                producer_output_names = {output.name for output in producer.outputs}

                if input_binding.source.name not in producer_output_names:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "an output declared by the producer step."
                    )

                if producer_step_id not in upstream_step_ids:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "values produced by upstream workflow steps."
                    )

            for condition in step.conditions:
                producer_step_id = condition.source.producer_step_id

                if producer_step_id not in steps_by_id:
                    raise ValueError(
                        "Workflow conditions must reference a producer step in the same workflow."
                    )

                producer = steps_by_id[producer_step_id]

                producer_output_names = {output.name for output in producer.outputs}

                if condition.source.name not in producer_output_names:
                    raise ValueError(
                        "Workflow conditions must reference "
                        "an output declared by the producer step."
                    )

                if producer_step_id not in upstream_step_ids:
                    raise ValueError(
                        "Workflow conditions must reference "
                        "values produced by upstream workflow steps."
                    )

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

    def _upstream_step_ids(
        self,
        step: WorkflowStepSpecification,
    ) -> set[UUID]:
        """Return all transitive dependencies of a workflow step."""

        steps_by_id = {workflow_step.id: workflow_step for workflow_step in self.steps}

        upstream: set[UUID] = set()
        pending = list(step.depends_on)

        while pending:
            dependency_id = pending.pop()

            if dependency_id in upstream:
                continue

            upstream.add(dependency_id)

            dependency = steps_by_id[dependency_id]
            pending.extend(dependency.depends_on)

        return upstream
