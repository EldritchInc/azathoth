"""Tests for generating executable workflow candidates."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.prompting import (
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCapability,
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
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("6cecbfd6-2783-41d7-b868-a5ead037aeb2")
CLASSIFICATION_STEP_ID = UUID("39e169cf-00a6-4728-bc97-ce1d95021470")
REASONING_STEP_ID = UUID("b4ae6fa8-09df-41a7-94e6-c3eb94ad66a7")
CLASSIFICATION_STRATEGY_ID = UUID("20cf4513-4206-413c-a377-d7c6c73d97c2")
REASONING_STRATEGY_ID = UUID("efcc83d6-73e6-4d43-b00a-ccf73eac9297")


class StubLanguageModel:
    """A deterministic language model with configured identity and output."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        response_text: str,
    ) -> None:
        self._provider = provider
        self._model = model
        self._response_text = response_text
        self.received_prompt: Prompt | None = None

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Record the prompt and return a deterministic response."""

        self.received_prompt = prompt

        return ModelResponse(
            text=self._response_text,
            provider=self._provider,
            model=self._model,
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


def require_prompt_strategy(
    strategy: Strategy,
) -> PromptStrategy:
    """Narrow a generic workflow strategy to a prompt strategy."""

    assert isinstance(strategy, PromptStrategy)

    return strategy


def create_classification_step() -> WorkflowStepSpecification:
    """Create a structured-output classification step."""

    return WorkflowStepSpecification(
        id=CLASSIFICATION_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=CLASSIFICATION_STRATEGY_ID,
                name="Classify request",
                description="Classify the supplied support request.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Classify the supplied support request.",
            ),
            model_requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                minimum_context_window_tokens=32_000,
            ),
        ),
    )


def create_reasoning_step() -> WorkflowStepSpecification:
    """Create a tool-capable reasoning step."""

    return WorkflowStepSpecification(
        id=REASONING_STEP_ID,
        depends_on=(CLASSIFICATION_STEP_ID,),
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=REASONING_STRATEGY_ID,
                name="Reason about request",
                description="Reason about the request using tools when needed.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Reason about the request and use tools when needed.",
            ),
            model_requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                minimum_context_window_tokens=128_000,
            ),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Classify and resolve request",
            description=("Classify a request before running a tool-capable reasoning step."),
            version="1.0.0",
        ),
        steps=(
            create_classification_step(),
            create_reasoning_step(),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a catalog with independently eligible step models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="classifier",
                display_name="Provider A Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="reasoner",
                display_name="Provider B Reasoner",
                capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                context_window_tokens=200_000,
            ),
            ModelMetadata(
                provider="provider-c",
                model="general",
                display_name="Provider C General",
                context_window_tokens=200_000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable models matching the catalog."""

    return LanguageModelRegistry(
        models={
            "provider-a/classifier": StubLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text="classification-result",
            ),
            "provider-b/reasoner": StubLanguageModel(
                provider="provider-b",
                model="reasoner",
                response_text="reasoning-result",
            ),
            "provider-c/general": StubLanguageModel(
                provider="provider-c",
                model="general",
                response_text="general-result",
            ),
        }
    )


def test_generate_workflow_candidate_preserves_workflow_metadata() -> None:
    specification = create_workflow()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.metadata == specification.metadata


def test_generate_workflow_candidate_preserves_step_order() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert tuple(step.metadata.name for step in candidate.steps) == (
        "Classify request [provider-a/classifier]",
        "Reason about request [provider-b/reasoner]",
    )


def test_generate_workflow_candidate_binds_each_step_independently() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    classification_step = require_prompt_strategy(candidate.steps[0])
    reasoning_step = require_prompt_strategy(candidate.steps[1])

    classification_binding = classification_step.model_binding
    reasoning_binding = reasoning_step.model_binding

    assert classification_binding is not None
    assert reasoning_binding is not None

    assert classification_binding.identifier == "provider-a/classifier"
    assert reasoning_binding.identifier == "provider-b/reasoner"


def test_generate_workflow_candidate_preserves_step_requirements() -> None:
    specification = create_workflow()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    classification_step = require_prompt_strategy(candidate.steps[0])
    reasoning_step = require_prompt_strategy(candidate.steps[1])

    assert (
        classification_step.model_requirements
        == specification.steps[0].specification.model_requirements
    )
    assert (
        reasoning_step.model_requirements == specification.steps[1].specification.model_requirements
    )


def test_generated_workflow_steps_are_executable() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    outcomes = tuple(asyncio.run(step.run(Context())) for step in candidate.steps)

    assert tuple(outcome.output for outcome in outcomes) == (
        "classification-result",
        "reasoning-result",
    )

    assert outcomes[0].metrics is not None
    assert outcomes[0].metrics.provider == "provider-a"
    assert outcomes[0].metrics.model == "classifier"

    assert outcomes[1].metrics is not None
    assert outcomes[1].metrics.provider == "provider-b"
    assert outcomes[1].metrics.model == "reasoner"


def test_workflow_candidate_generation_is_deterministic() -> None:
    specification = create_workflow()

    first = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )
    second = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    first_prompt_steps = tuple(require_prompt_strategy(step) for step in first.steps)
    second_prompt_steps = tuple(require_prompt_strategy(step) for step in second.steps)

    assert first.metadata == second.metadata
    assert tuple(step.metadata.id for step in first.steps) == tuple(
        step.metadata.id for step in second.steps
    )
    assert tuple(step.model_binding for step in first_prompt_steps) == tuple(
        step.model_binding for step in second_prompt_steps
    )


def test_generation_selects_first_eligible_executable_model() -> None:
    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="classifier",
                display_name="Provider A Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-d",
                model="classifier",
                display_name="Provider D Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="reasoner",
                display_name="Provider B Reasoner",
                capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                context_window_tokens=200_000,
            ),
        )
    )
    registry = LanguageModelRegistry(
        models={
            "provider-a/classifier": StubLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text="provider-a-result",
            ),
            "provider-d/classifier": StubLanguageModel(
                provider="provider-d",
                model="classifier",
                response_text="provider-d-result",
            ),
            "provider-b/reasoner": StubLanguageModel(
                provider="provider-b",
                model="reasoner",
                response_text="reasoning-result",
            ),
        }
    )

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=registry,
    )

    classification_step = require_prompt_strategy(candidate.steps[0])
    classification_binding = classification_step.model_binding

    assert classification_binding is not None
    assert classification_binding.identifier == "provider-a/classifier"


def test_generation_skips_eligible_model_missing_from_registry() -> None:
    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-missing",
                model="classifier",
                display_name="Missing Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-a",
                model="classifier",
                display_name="Provider A Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="reasoner",
                display_name="Provider B Reasoner",
                capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                context_window_tokens=200_000,
            ),
        )
    )

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=create_registry(),
    )

    classification_step = require_prompt_strategy(candidate.steps[0])
    classification_binding = classification_step.model_binding

    assert classification_binding is not None
    assert classification_binding.identifier == "provider-a/classifier"


def test_generation_fails_when_step_has_no_executable_candidate() -> None:
    registry = LanguageModelRegistry(
        models={
            "provider-a/classifier": StubLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text="classification-result",
            ),
        }
    )

    with pytest.raises(
        WorkflowGenerationError,
        match="Reason about request",
    ):
        generate_workflow_candidate(
            specification=create_workflow(),
            catalog=create_catalog(),
            registry=registry,
        )


def test_generation_fails_when_step_has_no_eligible_model() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Vision workflow",
            description="A workflow requiring an unavailable vision model.",
        ),
        steps=(
            WorkflowStepSpecification(
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        name="Inspect image",
                        description="Inspect a supplied image.",
                    ),
                    prompt=Prompt(
                        text="Inspect the supplied image.",
                    ),
                    model_requirements=ModelRequirements(
                        required_capabilities=frozenset(
                            {
                                ModelCapability.VISION,
                            }
                        ),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        WorkflowGenerationError,
        match="Inspect image",
    ):
        generate_workflow_candidate(
            specification=workflow,
            catalog=create_catalog(),
            registry=create_registry(),
        )
