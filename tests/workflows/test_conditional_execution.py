"""Tests for conditional workflow execution."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowCondition,
    WorkflowConditionOperator,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("842c60ba-ff46-4525-8241-c7f781566042")

CLASSIFIER_STEP_ID = UUID("cc9a2dc8-887c-40bd-a27b-f65ec653d720")
MATH_STEP_ID = UUID("b89946e0-79b1-4fa8-8387-ea62dc289e55")
GENERAL_STEP_ID = UUID("9211851a-25f0-4e8b-91fa-f0587dd52c75")

CLASSIFIER_STRATEGY_ID = UUID("f3485219-39ec-4217-87dc-d391ed392b64")
MATH_STRATEGY_ID = UUID("1eb09815-f691-4ecb-98ef-d17f73ff2ef2")
GENERAL_STRATEGY_ID = UUID("e29209fa-3ddb-4eb5-8b31-e776ea15884d")


class StubStrategy:
    """A deterministic workflow strategy."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(self, context: Context) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(output=None)


class ConditionalExecutor(StrategyExecutor):
    """Return deterministic outputs for conditional workflow tests."""

    def __init__(
        self,
        *,
        classification: str,
    ) -> None:
        self.classification = classification
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and return a deterministic output."""

        self.calls.append(strategy.metadata.name)

        output: JsonValue

        if strategy.metadata.name == "Classifier":
            output = {
                "classification": self.classification,
                "confidence": 0.94,
                "documents": 3,
            }
        else:
            output = {
                "result": strategy.metadata.name,
            }

        started_at = datetime(
            2026,
            8,
            9,
            18,
            30,
            tzinfo=UTC,
        )
        completed_at = datetime(
            2026,
            8,
            9,
            18,
            30,
            1,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context,
            started_at=started_at,
            completed_at=completed_at,
        )


def create_candidate() -> WorkflowCandidate:
    """Create a workflow with mutually exclusive conditional branches."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Conditional routing workflow",
            description="Route requests using a classification value.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=CLASSIFIER_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=CLASSIFIER_STRATEGY_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=MATH_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=MATH_STRATEGY_ID,
                    name="Math reasoner",
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="classification",
                        ),
                        expected="math",
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=GENERAL_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=GENERAL_STRATEGY_ID,
                    name="General reasoner",
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="classification",
                        ),
                        expected="general",
                    ),
                ),
            ),
        ),
    )


def test_matching_condition_executes_step() -> None:
    executor = ConditionalExecutor(
        classification="math",
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert executor.calls == [
        "Classifier",
        "Math reasoner",
    ]

    math_step = next(step for step in run.steps if step.step_id == MATH_STEP_ID)

    assert math_step.status is WorkflowStepStatus.EXECUTED
    assert math_step.execution is not None


def test_non_matching_condition_skips_step() -> None:
    executor = ConditionalExecutor(
        classification="math",
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    general_step = next(step for step in run.steps if step.step_id == GENERAL_STEP_ID)

    assert general_step.status is WorkflowStepStatus.SKIPPED
    assert general_step.execution is None
    assert general_step.values == ()


def test_unconditional_step_always_executes() -> None:
    executor = ConditionalExecutor(
        classification="general",
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    classifier_step = run.steps[0]

    assert classifier_step.step_id == CLASSIFIER_STEP_ID
    assert classifier_step.status is WorkflowStepStatus.EXECUTED


def test_only_matching_branch_executes() -> None:
    executor = ConditionalExecutor(
        classification="general",
    )

    asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert executor.calls == [
        "Classifier",
        "General reasoner",
    ]


def test_skipped_step_is_recorded_without_execution_evidence() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    skipped = tuple(step for step in run.steps if step.status is WorkflowStepStatus.SKIPPED)

    assert len(skipped) == 1
    assert skipped[0].step_id == GENERAL_STEP_ID
    assert skipped[0].execution is None


def test_all_conditions_must_match() -> None:
    candidate = create_candidate()

    math_step = candidate.steps[1]

    candidate_with_multiple_conditions = WorkflowCandidate(
        metadata=candidate.metadata,
        steps=(
            candidate.steps[0],
            WorkflowCandidateStep(
                id=math_step.id,
                strategy=math_step.strategy,
                depends_on=math_step.depends_on,
                inputs=math_step.inputs,
                outputs=math_step.outputs,
                conditions=(
                    *math_step.conditions,
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="classification",
                        ),
                        expected="general",
                    ),
                ),
            ),
            candidate.steps[2],
        ),
    )

    executor = ConditionalExecutor(
        classification="math",
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate_with_multiple_conditions,
            context=Context(),
        )
    )

    math_run = next(step for step in run.steps if step.step_id == MATH_STEP_ID)

    assert math_run.status is WorkflowStepStatus.SKIPPED


class NumericConditionalExecutor(StrategyExecutor):
    """Return a numeric workflow value for condition evaluation."""

    def __init__(
        self,
        *,
        score: float,
    ) -> None:
        self.score = score
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and return deterministic structured output."""

        self.calls.append(strategy.metadata.name)

        output: JsonValue

        if strategy.metadata.name == "Scorer":
            output = {
                "score": self.score,
            }
        else:
            output = {
                "result": strategy.metadata.name,
            }

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context,
            started_at=datetime(
                2026,
                8,
                9,
                22,
                0,
                tzinfo=UTC,
            ),
            completed_at=datetime(
                2026,
                8,
                9,
                22,
                0,
                1,
                tzinfo=UTC,
            ),
        )


def create_numeric_condition_candidate(
    *,
    operator: WorkflowConditionOperator,
    expected: JsonValue,
) -> WorkflowCandidate:
    """Create a workflow whose second step uses a numeric condition."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Numeric conditional workflow",
            description="Conditionally execute a step using a numeric value.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=CLASSIFIER_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=CLASSIFIER_STRATEGY_ID,
                    name="Scorer",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="score",
                        path=("score",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=MATH_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=MATH_STRATEGY_ID,
                    name="Conditional reasoner",
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="score",
                        ),
                        operator=operator,
                        expected=expected,
                    ),
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    (
        "operator",
        "expected",
        "actual",
        "should_execute",
    ),
    (
        (
            WorkflowConditionOperator.EQUAL,
            0.9,
            0.9,
            True,
        ),
        (
            WorkflowConditionOperator.EQUAL,
            0.9,
            0.8,
            False,
        ),
        (
            WorkflowConditionOperator.NOT_EQUAL,
            0.9,
            0.8,
            True,
        ),
        (
            WorkflowConditionOperator.NOT_EQUAL,
            0.9,
            0.9,
            False,
        ),
        (
            WorkflowConditionOperator.GREATER_THAN,
            0.9,
            0.95,
            True,
        ),
        (
            WorkflowConditionOperator.GREATER_THAN,
            0.9,
            0.9,
            False,
        ),
        (
            WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
            0.9,
            0.9,
            True,
        ),
        (
            WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
            0.9,
            0.85,
            False,
        ),
        (
            WorkflowConditionOperator.LESS_THAN,
            0.9,
            0.85,
            True,
        ),
        (
            WorkflowConditionOperator.LESS_THAN,
            0.9,
            0.9,
            False,
        ),
        (
            WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
            0.9,
            0.9,
            True,
        ),
        (
            WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
            0.9,
            0.95,
            False,
        ),
    ),
)
def test_runner_evaluates_condition_operator(
    operator: WorkflowConditionOperator,
    expected: JsonValue,
    actual: float,
    should_execute: bool,
) -> None:
    candidate = create_numeric_condition_candidate(
        operator=operator,
        expected=expected,
    )
    executor = NumericConditionalExecutor(
        score=actual,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    conditional_run = next(step for step in run.steps if step.step_id == MATH_STEP_ID)

    if should_execute:
        assert executor.calls == [
            "Scorer",
            "Conditional reasoner",
        ]
        assert conditional_run.status is WorkflowStepStatus.EXECUTED
        assert conditional_run.execution is not None
    else:
        assert executor.calls == [
            "Scorer",
        ]
        assert conditional_run.status is WorkflowStepStatus.SKIPPED
        assert conditional_run.execution is None


def create_numeric_candidate(
    *,
    operator: WorkflowConditionOperator,
    expected: float,
) -> WorkflowCandidate:
    """Create a workflow using a numeric workflow condition."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Confidence routing",
            description="Route based on confidence.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=CLASSIFIER_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=CLASSIFIER_STRATEGY_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="confidence",
                        path=("confidence",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=MATH_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=MATH_STRATEGY_ID,
                    name="High confidence",
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="confidence",
                        ),
                        operator=operator,
                        expected=expected,
                    ),
                ),
            ),
        ),
    )


def test_greater_than_operator_executes_matching_step() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_numeric_candidate(
                operator=WorkflowConditionOperator.GREATER_THAN,
                expected=0.90,
            ),
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.EXECUTED


def test_greater_than_operator_skips_non_matching_step() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_numeric_candidate(
                operator=WorkflowConditionOperator.GREATER_THAN,
                expected=0.95,
            ),
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.SKIPPED


def test_greater_than_or_equal_operator() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_numeric_candidate(
                operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
                expected=0.94,
            ),
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.EXECUTED


def test_less_than_operator() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_numeric_candidate(
                operator=WorkflowConditionOperator.LESS_THAN,
                expected=1.0,
            ),
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.EXECUTED


def test_less_than_or_equal_operator() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=create_numeric_candidate(
                operator=WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
                expected=0.94,
            ),
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.EXECUTED


def test_not_equal_operator() -> None:
    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Not equal",
            description="Route when values differ.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=CLASSIFIER_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=CLASSIFIER_STRATEGY_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=MATH_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=MATH_STRATEGY_ID,
                    name="Reasoner",
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="classification",
                        ),
                        operator=WorkflowConditionOperator.NOT_EQUAL,
                        expected="general",
                    ),
                ),
            ),
        ),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalExecutor(
                classification="math",
            ),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert run.steps[1].status is WorkflowStepStatus.EXECUTED
