"""Tests for preserving workflow retry policies."""

from uuid import UUID

from azathoth.prompting import PromptStrategySpec
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
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("d0d0cf1c-d36d-4327-82d6-7eae629f9df6")
STEP_ID = UUID("6bca68c0-3fb8-4eb0-b7cb-24d3bfb0d6d4")
STRATEGY_ID = UUID("74dfb77c-df91-44f8-a4d8-9f8d95bdfd4d")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
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


def create_specification() -> WorkflowSpecification:
    """Create a workflow with a retry policy."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Retry workflow",
            description="Verify retry policy preservation.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Retry step",
                        description="Retry step.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Retry.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=4,
                    initial_delay_seconds=0.5,
                    backoff_multiplier=2.0,
                    maximum_delay_seconds=5.0,
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="test-model",
                display_name="Test Model",
                context_window_tokens=32000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(),
        }
    )


def test_specification_preserves_retry_policy() -> None:
    specification = create_specification()

    policy = specification.steps[0].retry_policy

    assert policy.max_attempts == 4
    assert policy.initial_delay_seconds == 0.5
    assert policy.backoff_multiplier == 2.0
    assert policy.maximum_delay_seconds == 5.0


def test_retry_policy_round_trips_through_json() -> None:
    specification = create_specification()

    restored = WorkflowSpecification.model_validate_json(specification.model_dump_json())

    assert restored.steps[0].retry_policy == specification.steps[0].retry_policy


def test_candidate_generation_preserves_retry_policy() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    policy = candidate.steps[0].retry_policy

    assert policy.max_attempts == 4
    assert policy.initial_delay_seconds == 0.5
    assert policy.backoff_multiplier == 2.0
    assert policy.maximum_delay_seconds == 5.0


def test_default_retry_policy_is_preserved() -> None:
    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Default retry workflow",
            description="Default retry policy.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Default step",
                        description="Default.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Default.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
            ),
        ),
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].retry_policy == WorkflowRetryPolicy()
