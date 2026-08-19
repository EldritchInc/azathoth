"""Tests for evaluator judgments associated with workflow runs."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.workflows import WorkflowRunEvaluation

EVALUATION_ID = UUID("11111111-1111-1111-1111-111111111111")
RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

EVALUATED_AT = datetime(
    2026,
    8,
    18,
    20,
    0,
    tzinfo=UTC,
)


def create_evaluation() -> EvaluationResult:
    """Create one deterministic evaluator judgment."""

    return EvaluationResult(
        id=EVALUATION_ID,
        evaluator_name="exact-match",
        evaluator_version="1.0.0",
        score=0.0,
        threshold=1.0,
        status=EvaluationStatus.FAILED,
        reason="Actual value did not exactly match expected value.",
        evidence=(
            EvaluationEvidence(
                label="expected",
                value="negative",
            ),
            EvaluationEvidence(
                label="actual",
                value="positive",
            ),
        ),
    )


def create_run_evaluation() -> WorkflowRunEvaluation:
    """Create one deterministic run-linked evaluation."""

    return WorkflowRunEvaluation(
        run_id=RUN_ID,
        evaluation=create_evaluation(),
        evaluated_at=EVALUATED_AT,
    )


def test_run_evaluation_records_run_identity() -> None:
    run_evaluation = create_run_evaluation()

    assert run_evaluation.run_id == RUN_ID


def test_run_evaluation_preserves_evaluation_result() -> None:
    evaluation = create_evaluation()

    run_evaluation = WorkflowRunEvaluation(
        run_id=RUN_ID,
        evaluation=evaluation,
        evaluated_at=EVALUATED_AT,
    )

    assert run_evaluation.evaluation == evaluation


def test_run_evaluation_uses_evaluation_identity() -> None:
    run_evaluation = create_run_evaluation()

    assert run_evaluation.id == EVALUATION_ID
    assert run_evaluation.id == run_evaluation.evaluation.id


def test_run_evaluation_records_evaluation_time() -> None:
    run_evaluation = create_run_evaluation()

    assert run_evaluation.evaluated_at == EVALUATED_AT


def test_run_evaluation_round_trips_through_json() -> None:
    run_evaluation = create_run_evaluation()

    restored = WorkflowRunEvaluation.model_validate_json(run_evaluation.model_dump_json())

    assert restored == run_evaluation
    assert restored.id == EVALUATION_ID
    assert restored.run_id == RUN_ID


def test_run_evaluation_is_immutable() -> None:
    run_evaluation = create_run_evaluation()

    with pytest.raises(ValidationError):
        run_evaluation.run_id = UUID("33333333-3333-3333-3333-333333333333")
