"""End-to-end tests for conditional workflow execution."""

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
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("934c0599-02d7-48cc-a1dd-e0cbac7b2640")

CLASSIFIER_STEP_ID = UUID("299504bf-6cef-428e-88bf-229cd17f4c3d")
MATH_STEP_ID = UUID("1307ac03-d09f-498a-8640-37dddc683d11")
GENERAL_STEP_ID = UUID("68ddb37a-bdff-4e08-8f30-b1dd07c05f14")

CLASSIFIER_STRATEGY_ID = UUID("05e16ca7-92dd-41c0-9294-ad20827f76cf")
MATH_STRATEGY_ID = UUID("c2f48cf8-b402-4bd8-aa91-0308a70b6c38")
GENERAL_STRATEGY_ID = UUID("52ec0372-fd08-469a-b8ef-80ea3fab865d")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic response."""

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


class ConditionalWorkflowExecutor(StrategyExecutor):
    """Execute generated workflow strategies with deterministic outputs."""

    def __init__(
        self,
        *,
        classification: str,
    ) -> None:
        self._classification = classification
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and return deterministic structured output."""

        self.calls.append((strategy, context))

        output: JsonValue

        if strategy.metadata.name.startswith("Classify request"):
            output = {
                "classification": self._classification,
                "confidence": 0.99,
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
                18,
                30,
                tzinfo=UTC,
            ),
            completed_at=datetime(
                2026,
                8,
                9,
                18,
                30,
                1,
                tzinfo=UTC,
            ),
        )


def create_workflow_specification() -> WorkflowSpecification:
    """Create a workflow containing two conditional branches."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Conditional request routing",
            description=("Classify a request and execute the matching reasoning branch."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=CLASSIFIER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=CLASSIFIER_STRATEGY_ID,
                        name="Classify request",
                        description="Classify the incoming request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=MATH_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=MATH_STRATEGY_ID,
                        name="Solve math request",
                        description="Reason about a mathematical request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Solve the mathematical request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
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
            WorkflowStepSpecification(
                id=GENERAL_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=GENERAL_STRATEGY_ID,
                        name="Handle general request",
                        description="Reason about a general request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Handle the general request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
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


def test_math_classification_executes_only_math_branch() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[1].conditions == (
        WorkflowCondition(
            source=WorkflowValueReference(
                producer_step_id=CLASSIFIER_STEP_ID,
                name="classification",
            ),
            expected="math",
        ),
    )

    executor = ConditionalWorkflowExecutor(
        classification="math",
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
        "Classify request [test-provider/test-model]",
        "Solve math request [test-provider/test-model]",
    )

    classification_values = run.values_named("classification")

    assert len(classification_values) == 1
    assert classification_values[0].value == "math"
    assert classification_values[0].producer_step_id == CLASSIFIER_STEP_ID

    classifier_run = next(step for step in run.steps if step.step_id == CLASSIFIER_STEP_ID)
    math_run = next(step for step in run.steps if step.step_id == MATH_STEP_ID)
    general_run = next(step for step in run.steps if step.step_id == GENERAL_STEP_ID)

    assert classifier_run.status is WorkflowStepStatus.EXECUTED
    assert classifier_run.execution is not None

    assert math_run.status is WorkflowStepStatus.EXECUTED
    assert math_run.execution is not None

    assert general_run.status is WorkflowStepStatus.SKIPPED
    assert general_run.execution is None
    assert general_run.values == ()


def test_general_classification_executes_only_general_branch() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = ConditionalWorkflowExecutor(
        classification="general",
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
        "Classify request [test-provider/test-model]",
        "Handle general request [test-provider/test-model]",
    )

    classification_values = run.values_named("classification")

    assert len(classification_values) == 1
    assert classification_values[0].value == "general"

    math_run = next(step for step in run.steps if step.step_id == MATH_STEP_ID)
    general_run = next(step for step in run.steps if step.step_id == GENERAL_STEP_ID)

    assert math_run.status is WorkflowStepStatus.SKIPPED
    assert math_run.execution is None
    assert math_run.values == ()

    assert general_run.status is WorkflowStepStatus.EXECUTED
    assert general_run.execution is not None


def test_conditional_workflow_preserves_declared_step_order() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalWorkflowExecutor(
                classification="math",
            ),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        CLASSIFIER_STEP_ID,
        MATH_STEP_ID,
        GENERAL_STEP_ID,
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.SKIPPED,
    )


def test_conditional_execution_does_not_pollute_shared_context() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ConditionalWorkflowExecutor(
                classification="math",
            ),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert all(event.event_type != "workflow.input.bound" for event in run.final_context.events)
