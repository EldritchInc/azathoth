"""Tests for complete optimization run records."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    EvaluatorMetadata,
    ExpectedOutcome,
)
from azathoth.execution import ExecutionResult
from azathoth.optimization import OptimizationRun


def create_execution_result() -> ExecutionResult:
    """Create a deterministic execution result for model tests."""

    initial_context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "duplicate_charge"},
                producer="test-suite",
            ),
        )
    )

    final_context = initial_context.append(
        ContextEvent(
            event_type="strategy.execution.completed",
            payload={
                "strategy_name": "Extract customer intent",
            },
            producer="strategy-executor",
        )
    )

    return ExecutionResult(
        strategy_id=UUID("3d8522f1-4ea1-4e58-8f85-f8bd507f76fc"),
        strategy_name="Extract customer intent",
        strategy_version="1.0.0",
        output="duplicate_charge",
        initial_context=initial_context,
        final_context=final_context,
        started_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            1,
            tzinfo=UTC,
        ),
    )


def create_evaluation_result() -> EvaluationResult:
    """Create a deterministic passing evaluation result."""

    return EvaluationResult(
        id=UUID("01181df6-8097-48bb-ab8b-65a48b68be1b"),
        evaluator_name="exact-match",
        evaluator_version="1.0.0",
        score=1.0,
        threshold=1.0,
        status=EvaluationStatus.PASSED,
        reason="Actual value exactly matched expected value.",
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


def test_optimization_run_combines_execution_and_evaluation() -> None:
    execution = create_execution_result()
    evaluation = create_evaluation_result()

    run = OptimizationRun(
        id=UUID("e60413ba-d3cc-463d-a069-ad1795778b31"),
        example_id=UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557"),
        execution=execution,
        evaluation=evaluation,
        started_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            2,
            tzinfo=UTC,
        ),
    )

    assert run.execution == execution
    assert run.evaluation == evaluation
    assert run.example_id == UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557")
    assert run.passed is True


def test_optimization_run_exposes_failed_evaluation_status() -> None:
    failed_evaluation = EvaluationResult(
        evaluator_name="exact-match",
        evaluator_version="1.0.0",
        score=0.0,
        threshold=1.0,
        status=EvaluationStatus.FAILED,
        reason="Actual value did not exactly match expected value.",
    )

    run = OptimizationRun(
        example_id=UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557"),
        execution=create_execution_result(),
        evaluation=failed_evaluation,
        started_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            2,
            tzinfo=UTC,
        ),
    )

    assert run.passed is False


def test_optimization_run_is_immutable() -> None:
    run = OptimizationRun(
        example_id=UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557"),
        execution=create_execution_result(),
        evaluation=create_evaluation_result(),
        started_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            2,
            tzinfo=UTC,
        ),
    )

    with pytest.raises(ValidationError):
        run.example_id = UUID("400cb4d7-a809-4322-9f92-ded5ff4f6676")


def test_optimization_run_round_trips_through_json() -> None:
    run = OptimizationRun(
        id=UUID("e60413ba-d3cc-463d-a069-ad1795778b31"),
        example_id=UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557"),
        execution=create_execution_result(),
        evaluation=create_evaluation_result(),
        started_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            30,
            20,
            0,
            2,
            tzinfo=UTC,
        ),
    )

    serialized = run.model_dump_json()
    restored = OptimizationRun.model_validate_json(serialized)

    assert restored == run


def test_optimization_run_rejects_completion_before_start() -> None:
    with pytest.raises(
        ValidationError,
        match="Optimization run cannot complete before it starts",
    ):
        OptimizationRun(
            example_id=UUID("05dc4933-9861-43bd-a9f8-aeb5b3312557"),
            execution=create_execution_result(),
            evaluation=create_evaluation_result(),
            started_at=datetime(
                2026,
                7,
                30,
                20,
                0,
                2,
                tzinfo=UTC,
            ),
            completed_at=datetime(
                2026,
                7,
                30,
                20,
                0,
                tzinfo=UTC,
            ),
        )


class RecordingEvaluator:
    """A test evaluator that records its inputs."""

    def __init__(self, result: EvaluationResult) -> None:
        self._metadata = EvaluatorMetadata(
            name="recording-evaluator",
            description="Record evaluator inputs for runner tests.",
            version="1.0.0",
        )
        self.result = result
        self.received_expected: ExpectedOutcome | None = None
        self.received_actual: JsonValue = None

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        self.received_expected = expected
        self.received_actual = actual
        return self.result
