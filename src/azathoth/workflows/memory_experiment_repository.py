"""Deterministic in-memory persistence for workflow experiment records."""

from uuid import UUID

from azathoth.workflows.experiment_record import (
    WorkflowExperimentRecord,
)
from azathoth.workflows.experiment_repository import (
    WorkflowExperimentRepository,
)


class InMemoryWorkflowExperimentRepository:
    """Store immutable workflow experiment records in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._experiments: dict[
            UUID,
            WorkflowExperimentRecord,
        ] = {}

    def save(
        self,
        experiment: WorkflowExperimentRecord,
    ) -> None:
        """Persist one experiment without replacing existing evidence."""

        if experiment.id in self._experiments:
            raise ValueError(f"Workflow experiment {experiment.id} already exists.")

        self._experiments[experiment.id] = experiment

    def get(
        self,
        experiment_id: UUID,
    ) -> WorkflowExperimentRecord | None:
        """Return one experiment by identifier."""

        return self._experiments.get(experiment_id)

    def experiments(
        self,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return all experiments in insertion order."""

        return tuple(self._experiments.values())

    def experiments_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return experiments containing one workflow."""

        return tuple(
            experiment
            for experiment in self._experiments.values()
            if any(
                observation.workflow.id == workflow_id for observation in experiment.observations
            )
        )


def require_workflow_experiment_repository(
    repository: WorkflowExperimentRepository,
) -> WorkflowExperimentRepository:
    """Return a repository after static protocol validation."""

    return repository
