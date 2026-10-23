"""Tests for human-readable workflow experiment rendering."""

import json
from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import (
    render_workflow_experiment,
    render_workflow_experiment_summaries,
)
from azathoth.workflows import (
    WorkflowCandidateSignature,
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowScorecard,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

BENCHMARK_ID = UUID("22222222-2222-4222-8222-222222222222")

FIRST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")

SECOND_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555552")

LOSING_OBSERVATION_ID = UUID("66666666-6666-4666-8666-666666666661")

WINNING_OBSERVATION_ID = UUID("66666666-6666-4666-8666-666666666662")

FIRST_CASE_ID = UUID("77777777-7777-4777-8777-777777777771")

SECOND_CASE_ID = UUID("77777777-7777-4777-8777-777777777772")

LOSING_FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

LOSING_SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

WINNING_FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999993")

WINNING_SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999994")

LOSING_FIRST_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1")

LOSING_SECOND_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2")

WINNING_FIRST_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3")

WINNING_SECOND_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee4")

LEGACY_LOSING_RUN_ID = UUID("abababab-abab-4bab-8bab-abababababa1")

LEGACY_WINNING_RUN_ID = UUID("abababab-abab-4bab-8bab-abababababa2")

LEGACY_LOSING_EVALUATION_ID = UUID("cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdc1")

LEGACY_WINNING_EVALUATION_ID = UUID("cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdc2")

RECORDED_AT = datetime(
    2026,
    10,
    9,
    16,
    0,
    tzinfo=UTC,
)


def create_scorecard(
    overall_score: float,
    *,
    rationale: str = "",
) -> WorkflowScorecard:
    """Create a scorecard with distinguishable dimensions."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=1.0,
        latency_score=0.5,
        cost_score=0.25,
        overall_score=overall_score,
        rationale=rationale,
    )


def create_metadata() -> WorkflowMetadata:
    """Create the rendered workflow's metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="rendered workflow",
        description="Workflow used to test experiment rendering.",
        version="1.0.0",
    )


def create_observation(
    *,
    observation_id: UUID,
    strategy_id: UUID,
    cases: tuple[WorkflowExperimentCaseObservation, ...],
    scorecard: WorkflowScorecard,
) -> WorkflowExperimentObservation:
    """Create one observation of the rendered workflow."""

    return WorkflowExperimentObservation(
        id=observation_id,
        workflow=create_metadata(),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=WORKFLOW_ID,
            strategy_ids=(strategy_id,),
        ),
        cases=cases,
        scorecard=scorecard,
    )


def create_experiment(
    experiment_id: UUID = FIRST_EXPERIMENT_ID,
) -> WorkflowExperimentRecord:
    """Create a two-candidate benchmark experiment whose winner was observed second."""

    return WorkflowExperimentRecord(
        id=experiment_id,
        benchmark_id=BENCHMARK_ID,
        observations=(
            create_observation(
                observation_id=LOSING_OBSERVATION_ID,
                strategy_id=FIRST_STRATEGY_ID,
                cases=(
                    WorkflowExperimentCaseObservation(
                        case_id=FIRST_CASE_ID,
                        run_id=LOSING_FIRST_RUN_ID,
                        evaluation_id=LOSING_FIRST_EVALUATION_ID,
                        passed=True,
                    ),
                    WorkflowExperimentCaseObservation(
                        case_id=SECOND_CASE_ID,
                        run_id=LOSING_SECOND_RUN_ID,
                        evaluation_id=LOSING_SECOND_EVALUATION_ID,
                        passed=False,
                    ),
                ),
                scorecard=create_scorecard(0.4),
            ),
            create_observation(
                observation_id=WINNING_OBSERVATION_ID,
                strategy_id=SECOND_STRATEGY_ID,
                cases=(
                    WorkflowExperimentCaseObservation(
                        case_id=FIRST_CASE_ID,
                        run_id=WINNING_FIRST_RUN_ID,
                        evaluation_id=WINNING_FIRST_EVALUATION_ID,
                        passed=True,
                    ),
                    WorkflowExperimentCaseObservation(
                        case_id=SECOND_CASE_ID,
                        run_id=WINNING_SECOND_RUN_ID,
                        evaluation_id=WINNING_SECOND_EVALUATION_ID,
                        passed=True,
                    ),
                ),
                scorecard=create_scorecard(
                    0.9,
                    rationale="Correct and inexpensive.",
                ),
            ),
        ),
        ranking=(
            WINNING_OBSERVATION_ID,
            LOSING_OBSERVATION_ID,
        ),
        recorded_at=RECORDED_AT,
    )


def create_legacy_observation_payload(
    *,
    run_id: UUID,
    evaluation_id: UUID,
    strategy_id: UUID,
    scorecard: WorkflowScorecard,
) -> dict[str, object]:
    """Create one observation payload as written before multi-case records."""

    return {
        "workflow": json.loads(create_metadata().model_dump_json()),
        "candidate_signature": {
            "workflow_id": str(WORKFLOW_ID),
            "strategy_ids": [str(strategy_id)],
        },
        "run_id": str(run_id),
        "evaluation_id": str(evaluation_id),
        "scorecard": json.loads(scorecard.model_dump_json()),
    }


def create_legacy_experiment() -> WorkflowExperimentRecord:
    """Decode a two-candidate experiment written before multi-case records."""

    return WorkflowExperimentRecord.model_validate_json(
        json.dumps(
            {
                "id": str(FIRST_EXPERIMENT_ID),
                "observations": [
                    create_legacy_observation_payload(
                        run_id=LEGACY_LOSING_RUN_ID,
                        evaluation_id=LEGACY_LOSING_EVALUATION_ID,
                        strategy_id=FIRST_STRATEGY_ID,
                        scorecard=create_scorecard(0.4),
                    ),
                    create_legacy_observation_payload(
                        run_id=LEGACY_WINNING_RUN_ID,
                        evaluation_id=LEGACY_WINNING_EVALUATION_ID,
                        strategy_id=SECOND_STRATEGY_ID,
                        scorecard=create_scorecard(0.9),
                    ),
                ],
                "ranking": [
                    str(LEGACY_WINNING_RUN_ID),
                    str(LEGACY_LOSING_RUN_ID),
                ],
                "recorded_at": RECORDED_AT.isoformat(),
            }
        )
    )


def test_summary_renders_one_line_per_experiment_in_given_order() -> None:
    rendered = render_workflow_experiment_summaries(
        (
            create_experiment(SECOND_EXPERIMENT_ID),
            create_experiment(FIRST_EXPERIMENT_ID),
        )
    )

    assert rendered.splitlines() == [
        (
            f"{SECOND_EXPERIMENT_ID}  2026-10-09T16:00:00+00:00  2 candidates  2 cases  "
            f"winner {WINNING_OBSERVATION_ID}  overall 0.900000"
        ),
        (
            f"{FIRST_EXPERIMENT_ID}  2026-10-09T16:00:00+00:00  2 candidates  2 cases  "
            f"winner {WINNING_OBSERVATION_ID}  overall 0.900000"
        ),
    ]


def test_summary_of_no_experiments_is_empty() -> None:
    assert render_workflow_experiment_summaries(()) == ""


def test_summary_of_legacy_experiment_counts_one_case() -> None:
    assert render_workflow_experiment_summaries((create_legacy_experiment(),)) == (
        f"{FIRST_EXPERIMENT_ID}  2026-10-09T16:00:00+00:00  2 candidates  1 cases  "
        f"winner {LEGACY_WINNING_RUN_ID}  overall 0.900000"
    )


def test_detail_renders_benchmark_experiment_with_cases_in_rank_order() -> None:
    assert render_workflow_experiment(create_experiment()) == "\n".join(
        (
            f"Experiment ID: {FIRST_EXPERIMENT_ID}",
            "Recorded: 2026-10-09T16:00:00+00:00",
            f"Benchmark: {BENCHMARK_ID}",
            "Candidates: 2",
            "Cases: 2",
            f"Winner Observation ID: {WINNING_OBSERVATION_ID}",
            "",
            "Rank 1",
            f"Observation ID: {WINNING_OBSERVATION_ID}",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Strategy IDs: {SECOND_STRATEGY_ID}",
            "Passed: 2/2",
            (
                f"Case {FIRST_CASE_ID}: passed  run {WINNING_FIRST_RUN_ID}  "
                f"evaluation {WINNING_FIRST_EVALUATION_ID}"
            ),
            (
                f"Case {SECOND_CASE_ID}: passed  run {WINNING_SECOND_RUN_ID}  "
                f"evaluation {WINNING_SECOND_EVALUATION_ID}"
            ),
            "Quality: 0.900000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.900000",
            "Rationale: Correct and inexpensive.",
            "",
            "Rank 2",
            f"Observation ID: {LOSING_OBSERVATION_ID}",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Strategy IDs: {FIRST_STRATEGY_ID}",
            "Passed: 1/2",
            (
                f"Case {FIRST_CASE_ID}: passed  run {LOSING_FIRST_RUN_ID}  "
                f"evaluation {LOSING_FIRST_EVALUATION_ID}"
            ),
            (
                f"Case {SECOND_CASE_ID}: failed  run {LOSING_SECOND_RUN_ID}  "
                f"evaluation {LOSING_SECOND_EVALUATION_ID}"
            ),
            "Quality: 0.400000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.400000",
        )
    )


def test_detail_renders_legacy_experiment_without_benchmark_or_outcomes() -> None:
    assert render_workflow_experiment(create_legacy_experiment()) == "\n".join(
        (
            f"Experiment ID: {FIRST_EXPERIMENT_ID}",
            "Recorded: 2026-10-09T16:00:00+00:00",
            "Benchmark: none",
            "Candidates: 2",
            "Cases: 1",
            f"Winner Observation ID: {LEGACY_WINNING_RUN_ID}",
            "",
            "Rank 1",
            f"Observation ID: {LEGACY_WINNING_RUN_ID}",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Strategy IDs: {SECOND_STRATEGY_ID}",
            "Passed: unknown",
            (
                f"Case none: unknown  run {LEGACY_WINNING_RUN_ID}  "
                f"evaluation {LEGACY_WINNING_EVALUATION_ID}"
            ),
            "Quality: 0.900000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.900000",
            "",
            "Rank 2",
            f"Observation ID: {LEGACY_LOSING_RUN_ID}",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Strategy IDs: {FIRST_STRATEGY_ID}",
            "Passed: unknown",
            (
                f"Case none: unknown  run {LEGACY_LOSING_RUN_ID}  "
                f"evaluation {LEGACY_LOSING_EVALUATION_ID}"
            ),
            "Quality: 0.400000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.400000",
        )
    )


def test_detail_renders_known_outcome_without_case_identifier() -> None:
    experiment = WorkflowExperimentRecord(
        id=FIRST_EXPERIMENT_ID,
        observations=(
            create_observation(
                observation_id=WINNING_OBSERVATION_ID,
                strategy_id=SECOND_STRATEGY_ID,
                cases=(
                    WorkflowExperimentCaseObservation(
                        run_id=WINNING_FIRST_RUN_ID,
                        evaluation_id=WINNING_FIRST_EVALUATION_ID,
                        passed=False,
                    ),
                ),
                scorecard=create_scorecard(0.2),
            ),
        ),
        ranking=(WINNING_OBSERVATION_ID,),
        recorded_at=RECORDED_AT,
    )

    rendered = render_workflow_experiment(experiment).splitlines()

    assert "Passed: 0/1" in rendered
    assert (
        f"Case none: failed  run {WINNING_FIRST_RUN_ID}  evaluation {WINNING_FIRST_EVALUATION_ID}"
    ) in rendered
