"""Tests for workflow experiment repositories."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.workflows import (
    InMemoryWorkflowExperimentRepository,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowExperimentRepository,
    WorkflowMetadata,
    WorkflowScorecard,
    require_workflow_experiment_repository,
)

FIRST_EXPERIMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_EXPERIMENT_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_RUN_ID = UUID("66666666-6666-6666-6666-666666666666")

FIRST_EVALUATION_ID = UUID("77777777-7777-7777-7777-777777777777")
SECOND_EVALUATION_ID = UUID("88888888-8888-8888-8888-888888888888")

RECORDED_AT = datetime(
    2026,
    8,
    20,
    20,
    0,
    tzinfo=UTC,
)


def create_observation(
    *,
    workflow_id: UUID,
    run_id: UUID,
    evaluation_id: UUID,
    score: float,
) -> WorkflowExperimentObservation:
    """Create deterministic experiment evidence."""

    return WorkflowExperimentObservation(
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow-{workflow_id}",
            description="Execute a deterministic workflow.",
            version="1.0.0",
        ),
        run_id=run_id,
        evaluation_id=evaluation_id,
        scorecard=WorkflowScorecard(
            quality_score=score,
            reliability_score=score,
            latency_score=score,
            cost_score=score,
            overall_score=score,
            rationale="Deterministic test score.",
        ),
    )


def create_experiment(
    *,
    experiment_id: UUID,
    workflow_id: UUID,
    run_id: UUID,
    evaluation_id: UUID,
) -> WorkflowExperimentRecord:
    """Create one deterministic workflow experiment."""

    observation = create_observation(
        workflow_id=workflow_id,
        run_id=run_id,
        evaluation_id=evaluation_id,
        score=1.0,
    )

    return WorkflowExperimentRecord(
        id=experiment_id,
        observations=(observation,),
        ranking=(run_id,),
        recorded_at=RECORDED_AT,
    )


def test_in_memory_experiment_repository_saves_and_gets_experiment() -> None:
    repository = InMemoryWorkflowExperimentRepository()

    experiment = create_experiment(
        experiment_id=FIRST_EXPERIMENT_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
    )

    repository.save(experiment)

    assert repository.get(FIRST_EXPERIMENT_ID) is experiment


def test_in_memory_experiment_repository_returns_none_for_unknown_id() -> None:
    repository = InMemoryWorkflowExperimentRepository()

    assert repository.get(FIRST_EXPERIMENT_ID) is None


def test_in_memory_experiment_repository_preserves_insertion_order() -> None:
    repository = InMemoryWorkflowExperimentRepository()

    first = create_experiment(
        experiment_id=FIRST_EXPERIMENT_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
    )

    second = create_experiment(
        experiment_id=SECOND_EXPERIMENT_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        run_id=SECOND_RUN_ID,
        evaluation_id=SECOND_EVALUATION_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.experiments() == (
        first,
        second,
    )


def test_in_memory_experiment_repository_filters_by_workflow() -> None:
    repository = InMemoryWorkflowExperimentRepository()

    first = create_experiment(
        experiment_id=FIRST_EXPERIMENT_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
    )

    second = create_experiment(
        experiment_id=SECOND_EXPERIMENT_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        run_id=SECOND_RUN_ID,
        evaluation_id=SECOND_EVALUATION_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.experiments_for_workflow(FIRST_WORKFLOW_ID) == (first,)

    assert repository.experiments_for_workflow(SECOND_WORKFLOW_ID) == (second,)


def test_in_memory_experiment_repository_rejects_duplicate_experiment() -> None:
    repository = InMemoryWorkflowExperimentRepository()

    experiment = create_experiment(
        experiment_id=FIRST_EXPERIMENT_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
    )

    repository.save(experiment)

    with pytest.raises(
        ValueError,
        match=(f"Workflow experiment {FIRST_EXPERIMENT_ID} already exists"),
    ):
        repository.save(experiment)


def test_experiment_repository_satisfies_protocol() -> None:
    repository: WorkflowExperimentRepository = require_workflow_experiment_repository(
        InMemoryWorkflowExperimentRepository()
    )

    assert repository.experiments() == ()
