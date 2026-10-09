"""Tests for human-readable workflow experiment rendering."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import (
    render_workflow_experiment,
    render_workflow_experiment_summaries,
)
from azathoth.workflows import (
    WorkflowCandidateSignature,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowScorecard,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")

SECOND_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555552")

LOSING_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

WINNING_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

LOSING_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1")

WINNING_EVALUATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2")

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


def create_observation(
    *,
    run_id: UUID,
    evaluation_id: UUID,
    strategy_id: UUID,
    scorecard: WorkflowScorecard,
) -> WorkflowExperimentObservation:
    """Create one observation of the rendered workflow."""

    return WorkflowExperimentObservation(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="rendered workflow",
            description="Workflow used to test experiment rendering.",
            version="1.0.0",
        ),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=WORKFLOW_ID,
            strategy_ids=(strategy_id,),
        ),
        run_id=run_id,
        evaluation_id=evaluation_id,
        scorecard=scorecard,
    )


def create_experiment(
    experiment_id: UUID = FIRST_EXPERIMENT_ID,
) -> WorkflowExperimentRecord:
    """Create a two-candidate experiment whose winner was observed second."""

    return WorkflowExperimentRecord(
        id=experiment_id,
        observations=(
            create_observation(
                run_id=LOSING_RUN_ID,
                evaluation_id=LOSING_EVALUATION_ID,
                strategy_id=FIRST_STRATEGY_ID,
                scorecard=create_scorecard(0.4),
            ),
            create_observation(
                run_id=WINNING_RUN_ID,
                evaluation_id=WINNING_EVALUATION_ID,
                strategy_id=SECOND_STRATEGY_ID,
                scorecard=create_scorecard(
                    0.9,
                    rationale="Correct and inexpensive.",
                ),
            ),
        ),
        ranking=(
            WINNING_RUN_ID,
            LOSING_RUN_ID,
        ),
        recorded_at=RECORDED_AT,
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
            f"{SECOND_EXPERIMENT_ID}  2026-10-09T16:00:00+00:00  2 candidates  "
            f"winner {WINNING_RUN_ID}  overall 0.900000"
        ),
        (
            f"{FIRST_EXPERIMENT_ID}  2026-10-09T16:00:00+00:00  2 candidates  "
            f"winner {WINNING_RUN_ID}  overall 0.900000"
        ),
    ]


def test_summary_of_no_experiments_is_empty() -> None:
    assert render_workflow_experiment_summaries(()) == ""


def test_detail_renders_experiment_with_observations_in_rank_order() -> None:
    assert render_workflow_experiment(create_experiment()) == "\n".join(
        (
            f"Experiment ID: {FIRST_EXPERIMENT_ID}",
            "Recorded: 2026-10-09T16:00:00+00:00",
            "Candidates: 2",
            f"Winner Run ID: {WINNING_RUN_ID}",
            "",
            "Rank 1",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Run ID: {WINNING_RUN_ID}",
            f"Evaluation ID: {WINNING_EVALUATION_ID}",
            f"Strategy IDs: {SECOND_STRATEGY_ID}",
            "Quality: 0.900000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.900000",
            "Rationale: Correct and inexpensive.",
            "",
            "Rank 2",
            "Workflow: rendered workflow",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Run ID: {LOSING_RUN_ID}",
            f"Evaluation ID: {LOSING_EVALUATION_ID}",
            f"Strategy IDs: {FIRST_STRATEGY_ID}",
            "Quality: 0.400000",
            "Reliability: 1.000000",
            "Latency: 0.500000",
            "Cost: 0.250000",
            "Overall: 0.400000",
        )
    )
