"""Tests for preserving workflow failure policies."""

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
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("83d774b0-04c5-45ac-ae52-46dccefe9389")
STEP_ID = UUID("8073dc2d-96f1-47fe-a49c-1900d361925f")
STRATEGY_ID = UUID("cc3b851e-eb17-4d58-afc8-a967c456a63f")


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


def create_specification(
    *,
    failure_policy: WorkflowFailurePolicy,
) -> WorkflowSpecification:
    """Create a workflow with the supplied failure policy."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failure policy workflow",
            description="Verify failure policy preservation.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Failure policy step",
                        description="Failure policy step.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Run.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                failure_policy=failure_policy,
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a deterministic model catalog."""

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
    """Create a deterministic model registry."""

    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(),
        }
    )


def test_step_defaults_to_fail_workflow() -> None:
    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Default failure policy workflow",
            description="Verify default failure policy.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Default step",
                        description="Default step.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Run.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )

    assert specification.steps[0].failure_policy is WorkflowFailurePolicy.FAIL_WORKFLOW


def test_specification_preserves_failure_policy() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.CONTINUE,
    )

    assert specification.steps[0].failure_policy is WorkflowFailurePolicy.CONTINUE


def test_failure_policy_round_trips_through_json() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
    )

    restored = WorkflowSpecification.model_validate_json(specification.model_dump_json())

    assert restored.steps[0].failure_policy is WorkflowFailurePolicy.SKIP_DEPENDENTS


def test_candidate_generation_preserves_failure_policy() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.CONTINUE,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].failure_policy is WorkflowFailurePolicy.CONTINUE


def test_default_failure_policy_survives_candidate_generation() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].failure_policy is WorkflowFailurePolicy.FAIL_WORKFLOW
