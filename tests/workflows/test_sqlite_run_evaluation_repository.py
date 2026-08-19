"""Tests for SQLite workflow run evaluation persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.workflows import (
    SQLiteWorkflowRunEvaluationRepository,
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
    19,
    19,
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
    """Create deterministic run-linked evaluator evidence."""

    passed = score >= 1.0

    return WorkflowRunEvaluation(
        run_id=run_id,
        evaluation=EvaluationResult(
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
        ),
        evaluated_at=EVALUATED_AT,
    )


def test_sqlite_run_evaluation_repository_saves_and_gets_evaluation(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

    run_evaluation = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=1.0,
    )

    repository.save(run_evaluation)

    restored = repository.get(FIRST_EVALUATION_ID)

    assert restored == run_evaluation
    assert restored is not run_evaluation


def test_sqlite_run_evaluation_repository_returns_none_for_unknown_id(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

    assert repository.get(FIRST_EVALUATION_ID) is None


def test_sqlite_run_evaluation_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

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


def test_sqlite_run_evaluation_repository_filters_by_run(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

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


def test_sqlite_run_evaluation_repository_returns_empty_for_unknown_run(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

    repository.save(
        create_run_evaluation(
            evaluation_id=FIRST_EVALUATION_ID,
            run_id=FIRST_RUN_ID,
            evaluator_name="exact-match",
            score=1.0,
        )
    )

    assert repository.evaluations_for_run(SECOND_RUN_ID) == ()


def test_sqlite_run_evaluation_repository_rejects_duplicate_evaluation(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")

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


def test_sqlite_run_evaluation_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evaluations.db"

    run_evaluation = create_run_evaluation(
        evaluation_id=FIRST_EVALUATION_ID,
        run_id=FIRST_RUN_ID,
        evaluator_name="exact-match",
        score=0.0,
    )

    SQLiteWorkflowRunEvaluationRepository(database).save(run_evaluation)

    restored = SQLiteWorkflowRunEvaluationRepository(database).get(FIRST_EVALUATION_ID)

    assert restored == run_evaluation
    assert restored is not run_evaluation

    assert restored is not None
    assert restored.id == FIRST_EVALUATION_ID
    assert restored.run_id == FIRST_RUN_ID
    assert restored.evaluation == run_evaluation.evaluation
    assert restored.evaluated_at == EVALUATED_AT


def test_sqlite_run_evaluation_preserves_full_evaluator_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evaluations.db"

    run_evaluation = WorkflowRunEvaluation(
        run_id=FIRST_RUN_ID,
        evaluation=EvaluationResult(
            id=FIRST_EVALUATION_ID,
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
        ),
        evaluated_at=EVALUATED_AT,
    )

    SQLiteWorkflowRunEvaluationRepository(database).save(run_evaluation)

    restored = SQLiteWorkflowRunEvaluationRepository(database).get(FIRST_EVALUATION_ID)

    assert restored is not None

    assert restored.evaluation.evaluator_name == "exact-match"
    assert restored.evaluation.evaluator_version == "1.0.0"
    assert restored.evaluation.score == 0.0
    assert restored.evaluation.threshold == 1.0
    assert restored.evaluation.status is EvaluationStatus.FAILED
    assert restored.evaluation.reason == ("Actual value did not exactly match expected value.")
    assert restored.evaluation.evidence == (
        EvaluationEvidence(
            label="expected",
            value="negative",
        ),
        EvaluationEvidence(
            label="actual",
            value="positive",
        ),
    )


def test_sqlite_run_evaluation_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: WorkflowRunEvaluationRepository = require_workflow_run_evaluation_repository(
        SQLiteWorkflowRunEvaluationRepository(tmp_path / "evaluations.db")
    )

    assert repository.evaluations() == ()
