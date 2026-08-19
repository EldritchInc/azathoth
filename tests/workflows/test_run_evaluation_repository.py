"""Tests for workflow run evaluation repositories."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.workflows import (
    InMemoryWorkflowRunEvaluationRepository,
    WorkflowRunEvaluation,
    WorkflowRunEvaluationRepository,
    require_workflow_run_evaluation_repository,
)

FIRST_EVALUATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_EVALUATION_ID = UUID("22222222-2222-2222-2222-222222222222")
THIRD_EVALUATION_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")

EVALUATED_AT = datetime(
    2026,
    8,
    18,
    20,
    0,
    tzinfo=UTC,
)


def create_run_evaluation(
    *,
    evaluation_id: UUID,
    run_id: UUID,
    evaluator_name: str,
    score: float,
) -> WorkflowRunEvaluation:
    """Create deterministic run-linked evaluation evidence."""

    passed = score >= 1.0

    evaluation = EvaluationResult(
        id=evaluation_id,
        evaluator_name=evaluator_name,
        evaluator_version="1.0.0",
        score=score,
        threshold=1.0,
        status=(EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED),
        reason=("Evaluation passed." if passed else "Evaluation failed."),
        evidence=(
            EvaluationEvidence(
                label="actual",
                value="result",
            ),
        ),
    )

    return WorkflowRunEvaluation(
        run_id=run_id,
        evaluation=evaluation,
        evaluated_at=EVALUATED_AT,
    )


def test_in_memory_run_evaluation_repository_saves_and_gets_evaluation() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    run_evaluation = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    repository.save(run_evaluation)

    assert repository.get(FIRST_EVALUATION_ID) is run_evaluation


def test_in_memory_run_evaluation_repository_returns_none_for_unknown_id() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    assert repository.get(FIRST_EVALUATION_ID) is None


def test_in_memory_run_evaluation_repository_preserves_insertion_order() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    first = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    second = create_run_evaluation(
        evaluation_id=SECOND_EVALUATION_ID,
        run_id=SECOND_RUN_ID,
        evaluator_name="schema",
        score=0.0,
    )

    repository.save(first)
    repository.save(second)

    assert repository.evaluations() == (
        first,
        second,
    )


def test_in_memory_run_evaluation_repository_filters_by_run() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    first = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    second = create_run_evaluation(
        evaluation_id=SECOND_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="schema",
        score=0.0,
    )

    third = create_run_evaluation(
        evaluation_id=THIRD_EVALUATION_ID,
        run_id=SECOND_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    repository.save(first)
    repository.save(second)
    repository.save(third)

    assert repository.evaluations_for_run(FIRST_RUN_ID) == (
        first,
        second,
    )

    assert repository.evaluations_for_run(SECOND_RUN_ID) == (third,)


def test_in_memory_run_evaluation_repository_returns_empty_for_unknown_run() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    repository.save(
        create_run_evaluation(
            evaluation_id=FIRST_EVALUATION_ID,
            run_id=FIRST_RUN_ID,
            evaluator_name="exact-match",
            score=1.0,
        )
    )

    assert repository.evaluations_for_run(SECOND_RUN_ID) == ()


def test_in_memory_run_evaluation_repository_rejects_duplicate_evaluation() -> None:
    repository = InMemoryWorkflowRunEvaluationRepository()

    run_evaluation = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    repository.save(run_evaluation)

    with pytest.raises(
        ValueError,
        match=(f"Workflow run evaluation {FIRST_EVALUATION_ID} already exists"),
    ):
        repository.save(run_evaluation)


def test_run_evaluation_repository_satisfies_protocol() -> None:
    repository: WorkflowRunEvaluationRepository = require_workflow_run_evaluation_repository(
        InMemoryWorkflowRunEvaluationRepository()
    )

    assert repository.evaluations() == ()
