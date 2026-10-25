"""Executable workflow candidates."""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from azathoth.strategies import Strategy
from azathoth.workflows.condition import WorkflowCondition
from azathoth.workflows.failure import WorkflowFailurePolicy
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.references import declaring_step_ids
from azathoth.workflows.retry import WorkflowRetryPolicy
from azathoth.workflows.value import (
    WorkflowInputBinding,
    WorkflowNamedValueReference,
    WorkflowResultReference,
    WorkflowValueBinding,
)


class WorkflowCandidateSignature(BaseModel):
    """Identify one resolved executable workflow configuration.

    The workflow revision names the imported specification revision the
    candidate was generated from. It is absent for candidates generated
    outside a revisioned catalog and for records written before revisions.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: UUID

    workflow_revision: int | None = Field(
        default=None,
        ge=1,
    )

    strategy_ids: tuple[UUID, ...] = Field(
        min_length=1,
    )


@dataclass(frozen=True)
class WorkflowCandidateStep:
    """An executable strategy bound to one workflow step."""

    id: UUID
    strategy: Strategy
    depends_on: tuple[UUID, ...] = ()
    inputs: tuple[WorkflowInputBinding, ...] = ()
    outputs: tuple[WorkflowValueBinding, ...] = ()
    conditions: tuple[WorkflowCondition, ...] = ()
    retry_policy: WorkflowRetryPolicy = field(
        default_factory=WorkflowRetryPolicy,
    )
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW


@dataclass(frozen=True)
class WorkflowCandidate:
    """An executable workflow generated from a workflow specification.

    The optional result carries the specification's declared result, so the
    value judged during evaluation is the value production would return. The
    optional revision names the specification revision the candidate was
    generated from, so every run of it records where it came from.
    """

    metadata: WorkflowMetadata
    steps: tuple[WorkflowCandidateStep, ...]
    result: WorkflowResultReference | None = None
    revision: int | None = None

    def __post_init__(self) -> None:
        """Validate executable workflow topology."""

        if not self.steps:
            raise ValueError("Workflow candidates must contain at least one step.")

        if self.revision is not None and self.revision < 1:
            raise ValueError("Workflow candidate revision must be at least 1.")

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

        if isinstance(
            self.result,
            WorkflowNamedValueReference,
        ):
            if not declaring_step_ids(
                self.result.name,
                self.steps,
            ):
                raise ValueError(
                    "Workflow candidate result must name a value declared by at least one "
                    "candidate step."
                )

        elif self.result is not None:
            producer = next(
                (step for step in self.steps if step.id == self.result.producer_step_id),
                None,
            )

            if producer is None:
                raise ValueError(
                    "Workflow candidate result must reference a step in the same candidate."
                )

            if self.result.name not in {output.name for output in producer.outputs}:
                raise ValueError(
                    "Workflow candidate result must reference an output declared by its step."
                )

    @property
    def signature(
        self,
    ) -> WorkflowCandidateSignature:
        """Return the deterministic identity of this resolved candidate."""

        return WorkflowCandidateSignature(
            workflow_id=self.metadata.id,
            workflow_revision=self.revision,
            strategy_ids=tuple(step.strategy.metadata.id for step in self.steps),
        )

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
