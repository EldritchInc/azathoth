"""Tests for preserving workflow condition operators."""

from uuid import UUID

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
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCondition,
    WorkflowConditionOperator,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("cd6c0f15-4b08-4fd7-8764-e67ad44adcc8")

PRODUCER_STEP_ID = UUID("387d1766-82f7-45ee-8478-2d47cabcc19f")
CONSUMER_STEP_ID = UUID("5cb0de61-3236-46e2-9dae-d29a766d8dc5")

PRODUCER_STRATEGY_ID = UUID("58ff0438-085d-4290-b765-79b7e95459cf")
CONSUMER_STRATEGY_ID = UUID("393995d1-ae8f-42b0-8b21-a764c6487612")


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


def create_workflow_specification(
    *,
    operator: WorkflowConditionOperator,
) -> WorkflowSpecification:
    """Create a workflow containing one operator-based condition."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Condition operator preservation",
            description=("Verify condition operators survive workflow representation."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PRODUCER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=PRODUCER_STRATEGY_ID,
                        name="Score request",
                        description="Produce a confidence score.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Score the request.",
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
                id=CONSUMER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=CONSUMER_STRATEGY_ID,
                        name="Handle confident request",
                        description=(
                            "Handle requests whose confidence satisfies the configured condition."
                        ),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Handle the confident request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                depends_on=(PRODUCER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=PRODUCER_STEP_ID,
                            name="confidence",
                        ),
                        operator=operator,
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


def test_workflow_specification_preserves_condition_operator() -> None:
    specification = create_workflow_specification(
        operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
    )

    condition = specification.steps[1].conditions[0]

    assert condition.operator is WorkflowConditionOperator.GREATER_THAN_OR_EQUAL
    assert condition.expected == 0.9


def test_workflow_specification_round_trip_preserves_condition_operator() -> None:
    specification = create_workflow_specification(
        operator=WorkflowConditionOperator.LESS_THAN,
    )

    restored = WorkflowSpecification.model_validate_json(specification.model_dump_json())

    condition = restored.steps[1].conditions[0]

    assert condition.operator is WorkflowConditionOperator.LESS_THAN
    assert condition.expected == 0.9


def test_candidate_generation_preserves_condition_operator() -> None:
    specification = create_workflow_specification(
        operator=WorkflowConditionOperator.NOT_EQUAL,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    condition = candidate.steps[1].conditions[0]

    assert condition.operator is WorkflowConditionOperator.NOT_EQUAL
    assert condition.expected == 0.9


def test_candidate_generation_preserves_complete_condition() -> None:
    specification = create_workflow_specification(
        operator=WorkflowConditionOperator.GREATER_THAN,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[1].conditions == specification.steps[1].conditions


def test_default_equality_operator_survives_candidate_generation() -> None:
    specification = create_workflow_specification(
        operator=WorkflowConditionOperator.EQUAL,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    condition = candidate.steps[1].conditions[0]

    assert condition.operator is WorkflowConditionOperator.EQUAL


def test_all_condition_operators_survive_candidate_generation() -> None:
    operators = (
        WorkflowConditionOperator.EQUAL,
        WorkflowConditionOperator.NOT_EQUAL,
        WorkflowConditionOperator.GREATER_THAN,
        WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        WorkflowConditionOperator.LESS_THAN,
        WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
    )

    for operator in operators:
        specification = create_workflow_specification(
            operator=operator,
        )

        candidate = generate_workflow_candidate(
            specification=specification,
            catalog=create_catalog(),
            registry=create_registry(),
        )

        condition = candidate.steps[1].conditions[0]

        assert condition.operator is operator
