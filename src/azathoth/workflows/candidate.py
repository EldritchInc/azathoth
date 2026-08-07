"""Executable workflow candidates."""

from dataclasses import dataclass
from uuid import UUID

from azathoth.strategies import Strategy
from azathoth.workflows.models import WorkflowMetadata


@dataclass(frozen=True)
class WorkflowCandidateStep:
    """One executable strategy placed within a workflow candidate."""

    id: UUID
    strategy: Strategy
    depends_on: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class WorkflowCandidate:
    """An executable workflow generated from a workflow specification."""

    metadata: WorkflowMetadata
    steps: tuple[WorkflowCandidateStep, ...]

    def __post_init__(self) -> None:
        """Validate executable workflow topology."""

        if not self.steps:
            raise ValueError("Workflow candidates must contain at least one step.")

        step_ids = tuple(step.id for step in self.steps)
        known_ids = set(step_ids)

        if len(step_ids) != len(known_ids):
            raise ValueError("Workflow candidate step identifiers must be unique.")

        dependencies_by_step = {step.id: step.depends_on for step in self.steps}

        for step in self.steps:
            if step.id in step.depends_on:
                raise ValueError("Workflow candidate steps cannot depend on themselves.")

            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("Workflow candidate step dependencies must be unique.")

            if not set(step.depends_on).issubset(known_ids):
                raise ValueError(
                    "Workflow candidate dependencies must reference steps in the same candidate."
                )

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(step_id: UUID) -> None:
            if step_id in visited:
                return

            if step_id in visiting:
                raise ValueError("Workflow candidate dependency graph must be acyclic.")

            visiting.add(step_id)

            for dependency_id in dependencies_by_step[step_id]:
                visit(dependency_id)

            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)

    def execution_layers(
        self,
    ) -> tuple[tuple[WorkflowCandidateStep, ...], ...]:
        """Return dependency-safe executable steps grouped into layers."""

        remaining = list(self.steps)
        completed_ids: set[UUID] = set()
        layers: list[tuple[WorkflowCandidateStep, ...]] = []

        while remaining:
            ready = tuple(
                step for step in remaining if set(step.depends_on).issubset(completed_ids)
            )

            if not ready:
                raise RuntimeError(
                    "Validated workflow candidate topology could not produce an execution layer."
                )

            layers.append(ready)

            ready_ids = {step.id for step in ready}
            completed_ids.update(ready_ids)

            remaining = [step for step in remaining if step.id not in ready_ids]

        return tuple(layers)
