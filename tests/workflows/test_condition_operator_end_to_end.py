"""End-to-end tests for workflow condition operators."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
)
from azathoth.workflows import (
    WorkflowCondition,
    WorkflowConditionOperator,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("2c2f4163-5cff-413b-9ff1-eef0e8c846ce")

SCORER_STEP_ID = UUID("f518eb43-75b0-43f6-b7e9-0f607fc66fd4")
HIGH_CONFIDENCE_STEP_ID = UUID("f60e2247-b27e-40c0-8590-fd51033b6acf")
LOW_CONFIDENCE_STEP_ID = UUID("7488cb7b-045a-4057-a3ca-ed0bbf27398c")

SCORER_STRATEGY_ID = UUID("3a52895f-c361-4221-8609-fca2c91b77ea")
HIGH_CONFIDENCE_STRATEGY_ID = UUID("c8d49a92-1916-416b-8c6f-fefc24855074")
LOW_CONFIDENCE_STRATEGY_ID = UUID("74860ae0-ed57-4f0a-87f2-52a32860cf61")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic language model response."""

        return ModelResponse(
            text="unused",
            provider="test-provider",
            model="test-model",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0.0,
        )


class ConfidenceExecutor(StrategyExecutor):
    """Execute generated strategies with a configured confidence score."""

    def __init__(
        self,
        *,
        confidence: float,
    ) -> None:
        self._confidence = confidence
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and return deterministic structured output."""

        self.calls.append((strategy, context))

        output: JsonValue

        if strategy.metadata.name.startswith("Score request"):
            output = {
                "confidence": self._confidence,
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


def create_workflow_specification() -> WorkflowSpecification:
    """Create a workflow that routes based on confidence."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Confidence routing workflow",
            description=("Route requests according to a structured confidence score."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=SCORER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=SCORER_STRATEGY_ID,
                        name="Score request",
                        description="Produce a request confidence score.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Score the request confidence.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="confidence",
                        path=("confidence",),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=HIGH_CONFIDENCE_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=HIGH_CONFIDENCE_STRATEGY_ID,
                        name="Handle high confidence",
                        description=("Handle requests with sufficient confidence."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Handle the high-confidence request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                depends_on=(SCORER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=SCORER_STEP_ID,
                            name="confidence",
                        ),
                        operator=(WorkflowConditionOperator.GREATER_THAN_OR_EQUAL),
                        expected=0.9,
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=LOW_CONFIDENCE_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=LOW_CONFIDENCE_STRATEGY_ID,
                        name="Handle low confidence",
                        description=("Handle requests below the confidence threshold."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Handle the low-confidence request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                depends_on=(SCORER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=SCORER_STEP_ID,
                            name="confidence",
                        ),
                        operator=WorkflowConditionOperator.LESS_THAN,
                        expected=0.9,
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a model catalog containing one eligible model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="test-model",
                display_name="Test Model",
                context_window_tokens=32_000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create an executable language model registry."""

    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(),
        }
    )


def test_high_confidence_executes_high_confidence_branch() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert (
        candidate.steps[1].conditions[0].operator is WorkflowConditionOperator.GREATER_THAN_OR_EQUAL
    )
    assert candidate.steps[2].conditions[0].operator is WorkflowConditionOperator.LESS_THAN

    executor = ConfidenceExecutor(
        confidence=0.94,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == (
        "Score request [test-provider/test-model]",
        "Handle high confidence [test-provider/test-model]",
    )

    confidence_values = run.values_named("confidence")

    assert len(confidence_values) == 1
    assert confidence_values[0].value == 0.94
    assert confidence_values[0].producer_step_id == SCORER_STEP_ID

    scorer_run = next(step for step in run.steps if step.step_id == SCORER_STEP_ID)
    high_run = next(step for step in run.steps if step.step_id == HIGH_CONFIDENCE_STEP_ID)
    low_run = next(step for step in run.steps if step.step_id == LOW_CONFIDENCE_STEP_ID)

    assert scorer_run.status is WorkflowStepStatus.EXECUTED
    assert scorer_run.execution is not None

    assert high_run.status is WorkflowStepStatus.EXECUTED
    assert high_run.execution is not None

    assert low_run.status is WorkflowStepStatus.SKIPPED
    assert low_run.execution is None
    assert low_run.values == ()


def test_low_confidence_executes_low_confidence_branch() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = ConfidenceExecutor(
        confidence=0.72,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == (
        "Score request [test-provider/test-model]",
        "Handle low confidence [test-provider/test-model]",
    )

    high_run = next(step for step in run.steps if step.step_id == HIGH_CONFIDENCE_STEP_ID)
    low_run = next(step for step in run.steps if step.step_id == LOW_CONFIDENCE_STEP_ID)

    assert high_run.status is WorkflowStepStatus.SKIPPED
    assert high_run.execution is None

    assert low_run.status is WorkflowStepStatus.EXECUTED
    assert low_run.execution is not None


def test_threshold_value_uses_greater_than_or_equal_branch() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = ConfidenceExecutor(
        confidence=0.9,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    high_run = next(step for step in run.steps if step.step_id == HIGH_CONFIDENCE_STEP_ID)
    low_run = next(step for step in run.steps if step.step_id == LOW_CONFIDENCE_STEP_ID)

    assert high_run.status is WorkflowStepStatus.EXECUTED
    assert low_run.status is WorkflowStepStatus.SKIPPED


def test_condition_operator_workflow_preserves_declared_step_order() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ConfidenceExecutor(
                confidence=0.94,
            ),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        SCORER_STEP_ID,
        HIGH_CONFIDENCE_STEP_ID,
        LOW_CONFIDENCE_STEP_ID,
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.SKIPPED,
    )
