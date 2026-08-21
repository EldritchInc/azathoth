"""Persistence contracts for durable workflow experiment records."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.experiment_record import (
    WorkflowExperimentRecord,
)


class WorkflowExperimentRepository(Protocol):
    """Persist and retrieve completed workflow experiment records."""

    def save(
        self,
        experiment: WorkflowExperimentRecord,
    ) -> None:
        """Persist one completed workflow experiment."""

        ...

    def get(
        self,
        experiment_id: UUID,
    ) -> WorkflowExperimentRecord | None:
        """Return one experiment by identifier."""

        ...

    def experiments(
        self,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return all experiments in insertion order."""

        ...

    def experiments_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return experiments containing one workflow."""

        ...
