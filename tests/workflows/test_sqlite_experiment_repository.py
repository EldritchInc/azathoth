"""Tests for SQLite workflow experiment persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
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


def create_scorecard(
    score: float,
) -> WorkflowScorecard:
    """Create deterministic workflow score evidence."""

    return WorkflowScorecard(
        quality_score=score,
        reliability_score=score,
        latency_score=score,
        cost_score=score,
        overall_score=score,
        rationale="Deterministic experiment score.",
    )


def create_observation(
    *,
    workflow_id: UUID,
    workflow_name: str,
    run_id: UUID,
    evaluation_id: UUID,
    score: float,
) -> WorkflowExperimentObservation:
    """Create one deterministic experiment observation."""

    return WorkflowExperimentObservation(
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=workflow_name,
            description=f"Execute {workflow_name}.",
            version="1.0.0",
        ),
        run_id=run_id,
        evaluation_id=evaluation_id,
        scorecard=create_scorecard(score),
    )


def create_experiment(
    *,
    experiment_id: UUID = FIRST_EXPERIMENT_ID,
) -> WorkflowExperimentRecord:
    """Create one durable experiment with two observations."""

    first = create_observation(
        workflow_id=FIRST_WORKFLOW_ID,
        workflow_name="first workflow",
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
        score=0.75,
    )

    second = create_observation(
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        run_id=SECOND_RUN_ID,
        evaluation_id=SECOND_EVALUATION_ID,
        score=0.95,
    )

    return WorkflowExperimentRecord(
        id=experiment_id,
        observations=(
            first,
            second,
        ),
        ranking=(
            SECOND_RUN_ID,
            FIRST_RUN_ID,
        ),
        recorded_at=RECORDED_AT,
    )


def test_sqlite_experiment_repository_saves_and_gets_experiment(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    experiment = create_experiment()

    repository.save(experiment)

    restored = repository.get(FIRST_EXPERIMENT_ID)

    assert restored == experiment
    assert restored is not experiment


def test_sqlite_experiment_repository_returns_none_for_unknown_id(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    assert repository.get(FIRST_EXPERIMENT_ID) is None


def test_sqlite_experiment_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    first = create_experiment()

    second = WorkflowExperimentRecord(
        id=SECOND_EXPERIMENT_ID,
        observations=(
            create_observation(
                workflow_id=FIRST_WORKFLOW_ID,
                workflow_name="first workflow",
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                evaluation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                score=1.0,
            ),
        ),
        ranking=(UUID("99999999-9999-9999-9999-999999999999"),),
        recorded_at=RECORDED_AT,
    )

    repository.save(first)
    repository.save(second)

    assert repository.experiments() == (
        first,
        second,
    )


def test_sqlite_experiment_repository_filters_by_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    experiment = create_experiment()

    repository.save(experiment)

    assert repository.experiments_for_workflow(FIRST_WORKFLOW_ID) == (experiment,)

    assert repository.experiments_for_workflow(SECOND_WORKFLOW_ID) == (experiment,)


def test_sqlite_experiment_repository_returns_empty_for_unknown_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    repository.save(create_experiment())

    assert repository.experiments_for_workflow(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")) == ()


def test_sqlite_experiment_repository_rejects_duplicate_experiment(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")

    experiment = create_experiment()

    repository.save(experiment)

    with pytest.raises(
        ValueError,
        match=(f"Workflow experiment {FIRST_EXPERIMENT_ID} already exists"),
    ):
        repository.save(experiment)


def test_sqlite_experiment_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "experiments.db"

    experiment = create_experiment()

    SQLiteWorkflowExperimentRepository(database).save(experiment)

    restored = SQLiteWorkflowExperimentRepository(database).get(FIRST_EXPERIMENT_ID)

    assert restored == experiment
    assert restored is not experiment

    assert restored is not None
    assert restored.id == FIRST_EXPERIMENT_ID
    assert restored.recorded_at == RECORDED_AT

    assert restored.ranking == (
        SECOND_RUN_ID,
        FIRST_RUN_ID,
    )

    assert restored.winner.run_id == SECOND_RUN_ID

    assert restored.observation_for_run(FIRST_RUN_ID) == experiment.observation_for_run(
        FIRST_RUN_ID
    )


def test_sqlite_experiment_preserves_evidence_references(
    tmp_path: Path,
) -> None:
    database = tmp_path / "experiments.db"

    experiment = create_experiment()

    SQLiteWorkflowExperimentRepository(database).save(experiment)

    restored = SQLiteWorkflowExperimentRepository(database).get(FIRST_EXPERIMENT_ID)

    assert restored is not None

    first = restored.observation_for_run(FIRST_RUN_ID)
    second = restored.observation_for_run(SECOND_RUN_ID)

    assert first is not None
    assert second is not None

    assert first.workflow.id == FIRST_WORKFLOW_ID
    assert first.run_id == FIRST_RUN_ID
    assert first.evaluation_id == FIRST_EVALUATION_ID

    assert second.workflow.id == SECOND_WORKFLOW_ID
    assert second.run_id == SECOND_RUN_ID
    assert second.evaluation_id == SECOND_EVALUATION_ID


def test_sqlite_experiment_preserves_scorecards(
    tmp_path: Path,
) -> None:
    database = tmp_path / "experiments.db"

    experiment = create_experiment()

    SQLiteWorkflowExperimentRepository(database).save(experiment)

    restored = SQLiteWorkflowExperimentRepository(database).get(FIRST_EXPERIMENT_ID)

    assert restored is not None

    assert restored.observations[0].scorecard == create_scorecard(0.75)

    assert restored.observations[1].scorecard == create_scorecard(0.95)


def test_sqlite_experiment_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: WorkflowExperimentRepository = require_workflow_experiment_repository(
        SQLiteWorkflowExperimentRepository(tmp_path / "experiments.db")
    )

    assert repository.experiments() == ()
