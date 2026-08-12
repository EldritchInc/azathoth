"""Tests for computed workflow evaluations."""

from datetime import UTC, datetime

from .test_reliability_computation import create_run


def test_workflow_creates_evaluation() -> None:
    run = create_run()

    evaluation = run.evaluation

    assert evaluation.workflow_id == run.workflow.id

    assert evaluation.statistics == run.statistics

    assert evaluation.reliability == run.reliability


def test_workflow_evaluation_timestamp_is_recent() -> None:
    before = datetime.now(
        tz=UTC,
    )

    evaluation = create_run().evaluation

    after = datetime.now(
        tz=UTC,
    )

    assert before <= evaluation.evaluated_at <= after


def test_workflow_evaluation_is_deterministic_except_timestamp() -> None:
    run = create_run()

    first = run.evaluation
    second = run.evaluation

    assert first.workflow_id == second.workflow_id

    assert first.statistics == second.statistics

    assert first.reliability == second.reliability


def test_workflow_evaluation_matches_underlying_run() -> None:
    run = create_run()

    evaluation = run.evaluation

    assert evaluation.statistics.executed_steps == (run.executed_step_count)

    assert evaluation.statistics.failed_steps == (run.failed_step_count)

    assert evaluation.statistics.retry_count == (run.retry_count)

    assert evaluation.reliability == run.reliability
