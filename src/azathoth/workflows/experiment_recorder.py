"""Durable recording of workflow experiment evidence."""

from dataclasses import dataclass

from azathoth.workflows.experiment_repository import WorkflowExperimentRepository
from azathoth.workflows.run_evaluation_repository import WorkflowRunEvaluationRepository
from azathoth.workflows.run_repository import WorkflowRunRepository


@dataclass(frozen=True)
class WorkflowExperimentEvidenceRecorder:
    """Group the repositories that receive durable experiment evidence.

    Every candidate run is saved, including failed runs. Every evaluated run
    has its evaluation saved. Each completed experiment is saved as one record
    whose observations reference those runs and evaluations.
    """

    runs: WorkflowRunRepository
    evaluations: WorkflowRunEvaluationRepository
    experiments: WorkflowExperimentRepository


__all__ = [
    "WorkflowExperimentEvidenceRecorder",
]
