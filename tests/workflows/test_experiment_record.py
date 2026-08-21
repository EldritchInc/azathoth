"""Tests for durable workflow experiment records."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowScorecard,
)

EXPERIMENT_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")

FIRST_EVALUATION_ID = UUID("66666666-6666-6666-6666-666666666666")
SECOND_EVALUATION_ID = UUID("77777777-7777-7777-7777-777777777777")

RECORDED_AT = datetime(
    2026,
    8,
    20,
    20,
    0,
    tzinfo=UTC,
)


def create_scorecard(
    overall_score: float,
) -> WorkflowScorecard:
    """Create deterministic workflow scoring evidence."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=overall_score,
        latency_score=overall_score,
        cost_score=overall_score,
        overall_score=overall_score,
        rationale="Deterministic test score.",
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


def create_first_observation() -> WorkflowExperimentObservation:
    """Create the first experiment observation."""

    return create_observation(
        workflow_id=FIRST_WORKFLOW_ID,
        workflow_name="first workflow",
        run_id=FIRST_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
        score=0.75,
    )


def create_second_observation() -> WorkflowExperimentObservation:
    """Create the second experiment observation."""

    return create_observation(
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        run_id=SECOND_RUN_ID,
        evaluation_id=SECOND_EVALUATION_ID,
        score=0.95,
    )


def create_experiment() -> WorkflowExperimentRecord:
    """Create one deterministic durable experiment."""

    return WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        observations=(
            create_first_observation(),
            create_second_observation(),
        ),
        ranking=(
            SECOND_RUN_ID,
            FIRST_RUN_ID,
        ),
        recorded_at=RECORDED_AT,
    )


def test_experiment_records_observations() -> None:
    experiment = create_experiment()

    assert experiment.observations == (
        create_first_observation(),
        create_second_observation(),
    )


def test_experiment_ranking_uses_run_identity() -> None:
    experiment = create_experiment()

    assert experiment.ranking == (
        SECOND_RUN_ID,
        FIRST_RUN_ID,
    )


def test_experiment_returns_winning_observation() -> None:
    experiment = create_experiment()

    assert experiment.winner == (create_second_observation())


def test_experiment_finds_observation_by_run() -> None:
    experiment = create_experiment()

    assert experiment.observation_for_run(FIRST_RUN_ID) == create_first_observation()


def test_experiment_returns_none_for_unknown_run() -> None:
    experiment = create_experiment()

    assert experiment.observation_for_run(UUID("88888888-8888-8888-8888-888888888888")) is None


def test_experiment_rejects_duplicate_run_ids() -> None:
    first = create_first_observation()

    duplicate = create_observation(
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        run_id=FIRST_RUN_ID,
        evaluation_id=SECOND_EVALUATION_ID,
        score=0.95,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique run identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                first,
                duplicate,
            ),
            ranking=(FIRST_RUN_ID,),
        )


def test_experiment_rejects_duplicate_evaluation_ids() -> None:
    first = create_first_observation()

    duplicate = create_observation(
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        run_id=SECOND_RUN_ID,
        evaluation_id=FIRST_EVALUATION_ID,
        score=0.95,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique evaluation identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                first,
                duplicate,
            ),
            ranking=(
                FIRST_RUN_ID,
                SECOND_RUN_ID,
            ),
        )


def test_experiment_rejects_duplicate_ranking_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="ranking cannot contain duplicate run identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                create_second_observation(),
            ),
            ranking=(
                FIRST_RUN_ID,
                FIRST_RUN_ID,
            ),
        )


def test_experiment_requires_ranking_to_cover_all_observations() -> None:
    with pytest.raises(
        ValidationError,
        match="must reference every observed run exactly once",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                create_second_observation(),
            ),
            ranking=(FIRST_RUN_ID,),
        )


def test_experiment_round_trips_through_json() -> None:
    experiment = create_experiment()

    restored = WorkflowExperimentRecord.model_validate_json(experiment.model_dump_json())

    assert restored == experiment


def test_experiment_is_immutable() -> None:
    experiment = create_experiment()

    with pytest.raises(ValidationError):
        experiment.ranking = (
            FIRST_RUN_ID,
            SECOND_RUN_ID,
        )
