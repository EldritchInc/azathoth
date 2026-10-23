"""Tests for durable workflow experiment records."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    WorkflowCandidateSignature,
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowScorecard,
)

EXPERIMENT_ID = UUID("11111111-1111-1111-1111-111111111111")

BENCHMARK_ID = UUID("12121212-1212-1212-1212-121212121212")

FIRST_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")
SECOND_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_OBSERVATION_ID = UUID("abababab-abab-abab-abab-abababababab")
SECOND_OBSERVATION_ID = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")

FIRST_CASE_ID = UUID("c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1")
SECOND_CASE_ID = UUID("c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2")

FIRST_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")
THIRD_RUN_ID = UUID("45454545-4545-4545-4545-454545454545")
FOURTH_RUN_ID = UUID("56565656-5656-5656-5656-565656565656")

FIRST_EVALUATION_ID = UUID("66666666-6666-6666-6666-666666666666")
SECOND_EVALUATION_ID = UUID("77777777-7777-7777-7777-777777777777")
THIRD_EVALUATION_ID = UUID("67676767-6767-6767-6767-676767676767")
FOURTH_EVALUATION_ID = UUID("78787878-7878-7878-7878-787878787878")

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


def create_case(
    *,
    run_id: UUID,
    evaluation_id: UUID,
    case_id: UUID | None = None,
    passed: bool | None = True,
) -> WorkflowExperimentCaseObservation:
    """Create one deterministic case observation."""

    return WorkflowExperimentCaseObservation(
        case_id=case_id,
        run_id=run_id,
        evaluation_id=evaluation_id,
        passed=passed,
    )


def create_observation(
    *,
    observation_id: UUID,
    workflow_id: UUID,
    workflow_name: str,
    strategy_id: UUID,
    cases: tuple[WorkflowExperimentCaseObservation, ...],
    score: float,
) -> WorkflowExperimentObservation:
    """Create one deterministic experiment observation."""

    return WorkflowExperimentObservation(
        id=observation_id,
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=workflow_name,
            description=f"Execute {workflow_name}.",
            version="1.0.0",
        ),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=workflow_id,
            strategy_ids=(strategy_id,),
        ),
        cases=cases,
        scorecard=create_scorecard(score),
    )


def create_first_observation() -> WorkflowExperimentObservation:
    """Create the first experiment observation across two cases."""

    return create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        workflow_name="first workflow",
        strategy_id=FIRST_STRATEGY_ID,
        cases=(
            create_case(
                case_id=FIRST_CASE_ID,
                run_id=FIRST_RUN_ID,
                evaluation_id=FIRST_EVALUATION_ID,
                passed=True,
            ),
            create_case(
                case_id=SECOND_CASE_ID,
                run_id=THIRD_RUN_ID,
                evaluation_id=THIRD_EVALUATION_ID,
                passed=False,
            ),
        ),
        score=0.75,
    )


def create_second_observation() -> WorkflowExperimentObservation:
    """Create the second experiment observation across two cases."""

    return create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        strategy_id=SECOND_STRATEGY_ID,
        cases=(
            create_case(
                case_id=FIRST_CASE_ID,
                run_id=SECOND_RUN_ID,
                evaluation_id=SECOND_EVALUATION_ID,
                passed=True,
            ),
            create_case(
                case_id=SECOND_CASE_ID,
                run_id=FOURTH_RUN_ID,
                evaluation_id=FOURTH_EVALUATION_ID,
                passed=True,
            ),
        ),
        score=0.95,
    )


def create_experiment() -> WorkflowExperimentRecord:
    """Create one deterministic durable benchmark experiment."""

    return WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        benchmark_id=BENCHMARK_ID,
        observations=(
            create_first_observation(),
            create_second_observation(),
        ),
        ranking=(
            SECOND_OBSERVATION_ID,
            FIRST_OBSERVATION_ID,
        ),
        recorded_at=RECORDED_AT,
    )


def create_legacy_observation_payload(
    *,
    workflow_id: UUID,
    workflow_name: str,
    strategy_id: UUID,
    run_id: UUID,
    evaluation_id: UUID,
    score: float,
) -> dict[str, object]:
    """Create one observation payload as written before multi-case records."""

    return {
        "workflow": {
            "id": str(workflow_id),
            "name": workflow_name,
            "description": f"Execute {workflow_name}.",
            "version": "1.0.0",
        },
        "candidate_signature": {
            "workflow_id": str(workflow_id),
            "strategy_ids": [str(strategy_id)],
        },
        "run_id": str(run_id),
        "evaluation_id": str(evaluation_id),
        "scorecard": json.loads(create_scorecard(score).model_dump_json()),
    }


def create_legacy_record_payload() -> str:
    """Create one experiment payload as written before multi-case records."""

    return json.dumps(
        {
            "id": str(EXPERIMENT_ID),
            "observations": [
                create_legacy_observation_payload(
                    workflow_id=FIRST_WORKFLOW_ID,
                    workflow_name="first workflow",
                    strategy_id=FIRST_STRATEGY_ID,
                    run_id=FIRST_RUN_ID,
                    evaluation_id=FIRST_EVALUATION_ID,
                    score=0.75,
                ),
                create_legacy_observation_payload(
                    workflow_id=SECOND_WORKFLOW_ID,
                    workflow_name="second workflow",
                    strategy_id=SECOND_STRATEGY_ID,
                    run_id=SECOND_RUN_ID,
                    evaluation_id=SECOND_EVALUATION_ID,
                    score=0.95,
                ),
            ],
            "ranking": [
                str(SECOND_RUN_ID),
                str(FIRST_RUN_ID),
            ],
            "recorded_at": RECORDED_AT.isoformat(),
        }
    )


def test_experiment_records_observations() -> None:
    experiment = create_experiment()

    assert experiment.observations == (
        create_first_observation(),
        create_second_observation(),
    )


def test_experiment_records_benchmark_identity() -> None:
    assert create_experiment().benchmark_id == BENCHMARK_ID


def test_experiment_benchmark_identity_is_optional() -> None:
    experiment = WorkflowExperimentRecord(
        observations=(create_first_observation(),),
        ranking=(FIRST_OBSERVATION_ID,),
    )

    assert experiment.benchmark_id is None


def test_experiment_ranking_uses_observation_identity() -> None:
    experiment = create_experiment()

    assert experiment.ranking == (
        SECOND_OBSERVATION_ID,
        FIRST_OBSERVATION_ID,
    )


def test_experiment_returns_winning_observation() -> None:
    experiment = create_experiment()

    assert experiment.winner == create_second_observation()


def test_experiment_returns_observations_in_rank_order() -> None:
    experiment = create_experiment()

    assert experiment.ranked_observations == (
        create_second_observation(),
        create_first_observation(),
    )


def test_experiment_finds_observation_by_identifier() -> None:
    experiment = create_experiment()

    assert experiment.observation(FIRST_OBSERVATION_ID) == create_first_observation()
    assert experiment.observation(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None


def test_experiment_finds_observation_by_any_case_run() -> None:
    experiment = create_experiment()

    assert experiment.observation_for_run(FIRST_RUN_ID) == create_first_observation()
    assert experiment.observation_for_run(THIRD_RUN_ID) == create_first_observation()
    assert experiment.observation_for_run(FOURTH_RUN_ID) == create_second_observation()


def test_experiment_returns_none_for_unknown_run() -> None:
    experiment = create_experiment()

    assert experiment.observation_for_run(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None


def test_observation_finds_case_by_run() -> None:
    observation = create_first_observation()

    case = observation.case_for_run(THIRD_RUN_ID)

    assert case is not None
    assert case.case_id == SECOND_CASE_ID
    assert observation.case_for_run(SECOND_RUN_ID) is None


def test_observation_counts_passing_cases() -> None:
    assert create_first_observation().cases_passed == 1
    assert create_second_observation().cases_passed == 2


def test_observation_pass_count_is_unknown_when_any_case_is_unknown() -> None:
    observation = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        workflow_name="first workflow",
        strategy_id=FIRST_STRATEGY_ID,
        cases=(
            create_case(
                run_id=FIRST_RUN_ID,
                evaluation_id=FIRST_EVALUATION_ID,
                passed=None,
            ),
        ),
        score=0.75,
    )

    assert observation.cases_passed is None


def test_observation_requires_at_least_one_case() -> None:
    with pytest.raises(ValidationError):
        create_observation(
            observation_id=FIRST_OBSERVATION_ID,
            workflow_id=FIRST_WORKFLOW_ID,
            workflow_name="first workflow",
            strategy_id=FIRST_STRATEGY_ID,
            cases=(),
            score=0.75,
        )


def test_observation_rejects_duplicate_case_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="cases must use unique case identifiers",
    ):
        create_observation(
            observation_id=FIRST_OBSERVATION_ID,
            workflow_id=FIRST_WORKFLOW_ID,
            workflow_name="first workflow",
            strategy_id=FIRST_STRATEGY_ID,
            cases=(
                create_case(
                    case_id=FIRST_CASE_ID,
                    run_id=FIRST_RUN_ID,
                    evaluation_id=FIRST_EVALUATION_ID,
                ),
                create_case(
                    case_id=FIRST_CASE_ID,
                    run_id=THIRD_RUN_ID,
                    evaluation_id=THIRD_EVALUATION_ID,
                ),
            ),
            score=0.75,
        )


def test_experiment_rejects_duplicate_observation_ids() -> None:
    duplicate = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        strategy_id=SECOND_STRATEGY_ID,
        cases=(
            create_case(
                run_id=SECOND_RUN_ID,
                evaluation_id=SECOND_EVALUATION_ID,
            ),
        ),
        score=0.95,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique observation identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                duplicate,
            ),
            ranking=(FIRST_OBSERVATION_ID,),
        )


def test_experiment_rejects_duplicate_run_ids_across_observations() -> None:
    duplicate = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        strategy_id=SECOND_STRATEGY_ID,
        cases=(
            create_case(
                run_id=THIRD_RUN_ID,
                evaluation_id=SECOND_EVALUATION_ID,
            ),
        ),
        score=0.95,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique run identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                duplicate,
            ),
            ranking=(
                FIRST_OBSERVATION_ID,
                SECOND_OBSERVATION_ID,
            ),
        )


def test_experiment_rejects_duplicate_run_ids_within_observation() -> None:
    duplicate = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        workflow_name="first workflow",
        strategy_id=FIRST_STRATEGY_ID,
        cases=(
            create_case(
                case_id=FIRST_CASE_ID,
                run_id=FIRST_RUN_ID,
                evaluation_id=FIRST_EVALUATION_ID,
            ),
            create_case(
                case_id=SECOND_CASE_ID,
                run_id=FIRST_RUN_ID,
                evaluation_id=THIRD_EVALUATION_ID,
            ),
        ),
        score=0.75,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique run identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(duplicate,),
            ranking=(FIRST_OBSERVATION_ID,),
        )


def test_experiment_rejects_duplicate_evaluation_ids_across_observations() -> None:
    duplicate = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
        strategy_id=SECOND_STRATEGY_ID,
        cases=(
            create_case(
                run_id=SECOND_RUN_ID,
                evaluation_id=THIRD_EVALUATION_ID,
            ),
        ),
        score=0.95,
    )

    with pytest.raises(
        ValidationError,
        match="must use unique evaluation identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                duplicate,
            ),
            ranking=(
                FIRST_OBSERVATION_ID,
                SECOND_OBSERVATION_ID,
            ),
        )


def test_experiment_rejects_duplicate_ranking_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="ranking cannot contain duplicate observation identifiers",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                create_second_observation(),
            ),
            ranking=(
                FIRST_OBSERVATION_ID,
                FIRST_OBSERVATION_ID,
            ),
        )


def test_experiment_requires_ranking_to_cover_all_observations() -> None:
    with pytest.raises(
        ValidationError,
        match="must reference every observation exactly once",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                create_second_observation(),
            ),
            ranking=(FIRST_OBSERVATION_ID,),
        )


def test_experiment_rejects_ranking_by_run_identity() -> None:
    with pytest.raises(
        ValidationError,
        match="must reference every observation exactly once",
    ):
        WorkflowExperimentRecord(
            observations=(
                create_first_observation(),
                create_second_observation(),
            ),
            ranking=(
                SECOND_RUN_ID,
                FIRST_RUN_ID,
            ),
        )


def test_experiment_round_trips_through_json() -> None:
    experiment = create_experiment()

    restored = WorkflowExperimentRecord.model_validate_json(experiment.model_dump_json())

    assert restored == experiment


def test_experiment_is_immutable() -> None:
    experiment = create_experiment()

    with pytest.raises(ValidationError):
        experiment.ranking = (
            FIRST_OBSERVATION_ID,
            SECOND_OBSERVATION_ID,
        )


def test_experiment_observation_requires_candidate_workflow_identity() -> None:
    with pytest.raises(
        ValidationError,
        match="candidate signature must reference the observed workflow",
    ):
        WorkflowExperimentObservation(
            workflow=WorkflowMetadata(
                id=FIRST_WORKFLOW_ID,
                name="first workflow",
                description="Execute first workflow.",
                version="1.0.0",
            ),
            candidate_signature=WorkflowCandidateSignature(
                workflow_id=SECOND_WORKFLOW_ID,
                strategy_ids=(FIRST_STRATEGY_ID,),
            ),
            cases=(
                create_case(
                    run_id=FIRST_RUN_ID,
                    evaluation_id=FIRST_EVALUATION_ID,
                ),
            ),
            scorecard=create_scorecard(0.75),
        )


def test_experiment_records_candidate_identity() -> None:
    experiment = create_experiment()

    assert experiment.observations[0].candidate_signature == WorkflowCandidateSignature(
        workflow_id=FIRST_WORKFLOW_ID,
        strategy_ids=(FIRST_STRATEGY_ID,),
    )

    assert experiment.observations[1].candidate_signature == WorkflowCandidateSignature(
        workflow_id=SECOND_WORKFLOW_ID,
        strategy_ids=(SECOND_STRATEGY_ID,),
    )


def test_legacy_observation_decodes_as_one_unidentified_case() -> None:
    observation = WorkflowExperimentObservation.model_validate(
        create_legacy_observation_payload(
            workflow_id=FIRST_WORKFLOW_ID,
            workflow_name="first workflow",
            strategy_id=FIRST_STRATEGY_ID,
            run_id=FIRST_RUN_ID,
            evaluation_id=FIRST_EVALUATION_ID,
            score=0.75,
        )
    )

    assert observation.id == FIRST_RUN_ID
    assert observation.cases == (
        WorkflowExperimentCaseObservation(
            case_id=None,
            run_id=FIRST_RUN_ID,
            evaluation_id=FIRST_EVALUATION_ID,
            passed=None,
        ),
    )
    assert observation.cases_passed is None
    assert observation.scorecard == create_scorecard(0.75)


def test_legacy_record_decodes_with_run_based_ranking() -> None:
    experiment = WorkflowExperimentRecord.model_validate_json(
        create_legacy_record_payload(),
    )

    assert experiment.id == EXPERIMENT_ID
    assert experiment.benchmark_id is None
    assert experiment.recorded_at == RECORDED_AT
    assert experiment.ranking == (
        SECOND_RUN_ID,
        FIRST_RUN_ID,
    )
    assert experiment.winner.workflow.id == SECOND_WORKFLOW_ID
    assert experiment.winner.cases[0].run_id == SECOND_RUN_ID
    assert experiment.observation_for_run(FIRST_RUN_ID) == experiment.observations[0]


def test_legacy_record_round_trips_in_current_shape() -> None:
    experiment = WorkflowExperimentRecord.model_validate_json(
        create_legacy_record_payload(),
    )

    payload = json.loads(experiment.model_dump_json())

    assert "run_id" not in payload["observations"][0]
    assert payload["observations"][0]["id"] == str(FIRST_RUN_ID)
    assert WorkflowExperimentRecord.model_validate_json(experiment.model_dump_json()) == (
        experiment
    )


def test_legacy_record_decodes_through_sqlite_repository(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteWorkflowExperimentRepository(database)

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            INSERT INTO workflow_experiments (
                experiment_id,
                payload
            )
            VALUES (?, ?)
            """,
            (
                str(EXPERIMENT_ID),
                create_legacy_record_payload(),
            ),
        )

        for workflow_id, run_id, evaluation_id in (
            (FIRST_WORKFLOW_ID, FIRST_RUN_ID, FIRST_EVALUATION_ID),
            (SECOND_WORKFLOW_ID, SECOND_RUN_ID, SECOND_EVALUATION_ID),
        ):
            connection.execute(
                """
                INSERT INTO workflow_experiment_observations (
                    experiment_id,
                    workflow_id,
                    run_id,
                    evaluation_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(EXPERIMENT_ID),
                    str(workflow_id),
                    str(run_id),
                    str(evaluation_id),
                ),
            )

        connection.commit()
    finally:
        connection.close()

    restored = repository.get(EXPERIMENT_ID)

    assert restored is not None
    assert restored.benchmark_id is None
    assert restored.winner.cases[0].run_id == SECOND_RUN_ID
    assert repository.experiments() == (restored,)
    assert repository.experiments_for_workflow(FIRST_WORKFLOW_ID) == (restored,)


def test_multi_case_record_indexes_every_case_in_sqlite(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteWorkflowExperimentRepository(database)

    repository.save(create_experiment())

    connection = sqlite3.connect(database)

    try:
        rows = connection.execute(
            """
            SELECT workflow_id, run_id, evaluation_id
            FROM workflow_experiment_observations
            ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        (str(FIRST_WORKFLOW_ID), str(FIRST_RUN_ID), str(FIRST_EVALUATION_ID)),
        (str(FIRST_WORKFLOW_ID), str(THIRD_RUN_ID), str(THIRD_EVALUATION_ID)),
        (str(SECOND_WORKFLOW_ID), str(SECOND_RUN_ID), str(SECOND_EVALUATION_ID)),
        (str(SECOND_WORKFLOW_ID), str(FOURTH_RUN_ID), str(FOURTH_EVALUATION_ID)),
    ]
    assert repository.get(EXPERIMENT_ID) == create_experiment()
    assert repository.experiments_for_workflow(SECOND_WORKFLOW_ID) == (create_experiment(),)
