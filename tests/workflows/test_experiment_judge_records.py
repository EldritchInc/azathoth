"""Tests for judge calls and cost saved on durable experiment records."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    InMemoryWorkflowExperimentRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    SQLiteWorkflowExperimentRepository,
    WorkflowExperimentCaseObservation,
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
)
from tests.workflows.test_experiment_judge_evidence import (
    JUDGE_COST_USD,
    JudgingEvaluator,
    create_workflows,
)
from tests.workflows.test_experiment_runner import (
    CASE_ID_A,
    CASE_ID_B,
    RecordingEvaluator,
    create_case,
    create_multi_case_dataset,
    create_outcome_evaluator,
    create_scorer,
)

RUN_ID = UUID("12121212-1212-4212-8212-121212121212")
EVALUATION_ID = UUID("34343434-3434-4434-8434-343434343434")


def record_experiment(
    evaluator: RecordingEvaluator,
) -> tuple[WorkflowExperimentResult, WorkflowExperimentRecord]:
    """Run and record both candidates over two cases, returning the saved record."""

    experiments = InMemoryWorkflowExperimentRepository()

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
            recorder=WorkflowExperimentEvidenceRecorder(
                runs=InMemoryWorkflowRunRepository(),
                evaluations=InMemoryWorkflowRunEvaluationRepository(),
                experiments=experiments,
            ),
        ).run(
            workflows=create_workflows(),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="first",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="second",
                    expected_value="success",
                ),
            ),
        )
    )

    record = experiments.get(result.id)

    assert record is not None

    return result, record


def judged_record() -> tuple[WorkflowExperimentResult, WorkflowExperimentRecord]:
    """Record the experiment with two judge calls per evaluation."""

    return record_experiment(
        JudgingEvaluator(
            calls_per_evaluation=2,
            cost_usd_per_call=JUDGE_COST_USD,
        )
    )


def create_case_observation(
    **judging: object,
) -> WorkflowExperimentCaseObservation:
    """Create one case observation with optional judge evidence."""

    return WorkflowExperimentCaseObservation.model_validate(
        {
            "case_id": str(CASE_ID_A),
            "run_id": str(RUN_ID),
            "evaluation_id": str(EVALUATION_ID),
            "passed": True,
            **judging,
        }
    )


def test_recorded_cases_carry_their_judge_calls_and_cost() -> None:
    _, record = judged_record()

    for observation in record.observations:
        for case in observation.cases:
            assert case.judge_calls == 2
            assert case.judge_cost_usd == pytest.approx(2 * JUDGE_COST_USD)


def test_recorded_observations_total_their_cases_judging() -> None:
    _, record = judged_record()

    for observation in record.observations:
        assert observation.judge_calls == 4
        assert observation.judge_cost_usd == pytest.approx(4 * JUDGE_COST_USD)


def test_recorded_judging_agrees_with_the_experiment_result() -> None:
    result, record = judged_record()

    assert tuple(observation.judge_calls for observation in record.observations) == tuple(
        evidence.judge_calls for evidence in result.evidence
    )
    assert tuple(observation.judge_cost_usd for observation in record.observations) == (
        pytest.approx(tuple(evidence.judge_cost_usd for evidence in result.evidence))
    )


def test_recorded_cases_without_judges_carry_no_judging() -> None:
    _, record = record_experiment(RecordingEvaluator())

    for observation in record.observations:
        assert observation.judge_calls == 0
        assert observation.judge_cost_usd == 0.0


def test_recorded_judging_never_changes_recorded_scorecards() -> None:
    _, unjudged = record_experiment(RecordingEvaluator())
    _, judged = judged_record()

    assert tuple(observation.scorecard for observation in judged.observations) == tuple(
        observation.scorecard for observation in unjudged.observations
    )


def test_case_observation_decodes_without_judge_fields() -> None:
    case = create_case_observation()

    assert case.judge_calls == 0
    assert case.judge_cost_usd == 0.0


def test_case_observation_dump_round_trips_judging() -> None:
    case = create_case_observation(
        judge_calls=3,
        judge_cost_usd=0.75,
    )

    dumped = case.model_dump(mode="json")

    assert dumped["judge_calls"] == 3
    assert dumped["judge_cost_usd"] == 0.75
    assert WorkflowExperimentCaseObservation.model_validate(dumped) == case


def test_case_observation_dump_without_judge_keys_decodes_as_unjudged() -> None:
    dumped = create_case_observation(
        judge_calls=3,
        judge_cost_usd=0.75,
    ).model_dump(mode="json")

    del dumped["judge_calls"]
    del dumped["judge_cost_usd"]

    decoded = WorkflowExperimentCaseObservation.model_validate(dumped)

    assert decoded.judge_calls == 0
    assert decoded.judge_cost_usd == 0.0


def test_case_observation_rejects_negative_judge_calls() -> None:
    with pytest.raises(ValidationError):
        create_case_observation(
            judge_calls=-1,
        )


def test_case_observation_rejects_negative_judge_cost() -> None:
    with pytest.raises(ValidationError):
        create_case_observation(
            judge_cost_usd=-0.01,
        )


def test_legacy_single_run_observation_decodes_as_unjudged() -> None:
    _, record = judged_record()

    observation = record.observations[0]

    payload = observation.model_dump(mode="json")

    del payload["cases"]
    del payload["id"]

    payload["run_id"] = str(RUN_ID)
    payload["evaluation_id"] = str(EVALUATION_ID)

    decoded = WorkflowExperimentObservation.model_validate(payload)

    assert decoded.judge_calls == 0
    assert decoded.judge_cost_usd == 0.0


def test_sqlite_experiment_repository_keeps_recorded_judging(
    tmp_path: Path,
) -> None:
    _, record = judged_record()

    repository = SQLiteWorkflowExperimentRepository(tmp_path / "azathoth.db")

    repository.save(record)

    loaded = repository.get(record.id)

    assert loaded == record

    assert loaded is not None
    assert loaded.observations[0].judge_calls == 4
