"""Tests for completed evaluation result models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)


def test_evaluation_result_records_a_passing_evaluation() -> None:
    result = EvaluationResult(
        id=UUID("f36df416-b959-4f8a-91ca-28faef080160"),
        evaluator_name="exact-match",
        evaluator_version="1.0.0",
        score=1.0,
        threshold=1.0,
        status=EvaluationStatus.PASSED,
        reason="The actual value exactly matched the expected value.",
        evidence=(
            EvaluationEvidence(
                label="expected",
                value="duplicate_charge",
            ),
            EvaluationEvidence(
                label="actual",
                value="duplicate_charge",
            ),
        ),
    )

    assert result.score == 1.0
    assert result.threshold == 1.0
    assert result.status is EvaluationStatus.PASSED
    assert result.passed is True
    assert result.evidence[0].value == "duplicate_charge"


def test_evaluation_result_records_a_failed_evaluation() -> None:
    result = EvaluationResult(
        evaluator_name="exact-match",
        score=0.0,
        threshold=1.0,
        status=EvaluationStatus.FAILED,
        reason="The actual value did not match the expected value.",
    )

    assert result.status is EvaluationStatus.FAILED
    assert result.passed is False


@pytest.mark.parametrize(
    "score",
    (
        -0.01,
        1.01,
    ),
)
def test_evaluation_result_rejects_scores_outside_normalized_range(
    score: float,
) -> None:
    with pytest.raises(ValidationError):
        EvaluationResult(
            evaluator_name="test-evaluator",
            score=score,
            status=EvaluationStatus.FAILED,
            reason="Invalid score used by test.",
        )


@pytest.mark.parametrize(
    "threshold",
    (
        -0.01,
        1.01,
    ),
)
def test_evaluation_result_rejects_invalid_thresholds(
    threshold: float,
) -> None:
    with pytest.raises(ValidationError):
        EvaluationResult(
            evaluator_name="test-evaluator",
            score=0.5,
            threshold=threshold,
            status=EvaluationStatus.FAILED,
            reason="Invalid threshold used by test.",
        )


def test_evaluation_result_is_immutable() -> None:
    result = EvaluationResult(
        evaluator_name="exact-match",
        score=1.0,
        status=EvaluationStatus.PASSED,
        reason="The values matched.",
    )

    with pytest.raises(ValidationError):
        result.score = 0.0


def test_evaluation_result_round_trips_through_json() -> None:
    result = EvaluationResult(
        id=UUID("3f182d53-7b25-4acf-ad70-d3723a7db469"),
        evaluator_name="exact-match",
        evaluator_version="1.0.0",
        score=1.0,
        threshold=1.0,
        status=EvaluationStatus.PASSED,
        reason="The actual value exactly matched the expected value.",
        evidence=(
            EvaluationEvidence(
                label="expected",
                value={
                    "category": "duplicate_charge",
                },
            ),
            EvaluationEvidence(
                label="actual",
                value={
                    "category": "duplicate_charge",
                },
            ),
        ),
    )

    serialized = result.model_dump_json()
    restored = EvaluationResult.model_validate_json(serialized)

    assert restored == result


def test_evaluation_result_rejects_status_that_conflicts_with_score() -> None:
    with pytest.raises(
        ValidationError,
        match="Evaluation status must agree with score and threshold",
    ):
        EvaluationResult(
            evaluator_name="exact-match",
            score=0.0,
            threshold=1.0,
            status=EvaluationStatus.PASSED,
            reason="This result is internally inconsistent.",
        )


def test_evaluation_result_can_pass_at_a_configured_threshold() -> None:
    result = EvaluationResult(
        evaluator_name="semantic-similarity",
        score=0.86,
        threshold=0.80,
        status=EvaluationStatus.PASSED,
        reason="The semantic similarity exceeded the configured threshold.",
    )

    assert result.passed is True
