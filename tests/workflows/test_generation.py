"""Tests for generating executable workflow candidates."""

import asyncio
from uuid import UUID, uuid5

import pytest

from azathoth.context import Context
from azathoth.prompting import PromptStrategy, PromptStrategySpec
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("0dd90e7c-0fd2-4994-84fd-14dc1ac2f63d")

CLASSIFICATION_STEP_ID = UUID("23546067-3fc4-47b4-95c4-2531c1f74db8")
REASONING_STEP_ID = UUID("cc9de32b-58ea-4a5b-bf17-16d9524298e6")

CLASSIFICATION_STRATEGY_ID = UUID("7f578d78-54bc-4dd1-a9fa-082bb5e0f1a7")
REASONING_STRATEGY_ID = UUID("c8c79156-2b38-4438-98c6-d9b421844e6e")


class StubLanguageModel:
    """A deterministic executable language model."""

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

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
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


def create_classification_step() -> WorkflowStepSpecification:
    """Create a structured-output classification step."""

    return WorkflowStepSpecification(
        id=CLASSIFICATION_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=CLASSIFICATION_STRATEGY_ID,
                name="Classify request",
                description="Determine the category of the request.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Classify the supplied request.",
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
        outputs=(
            WorkflowValueBinding(
                name="classification",
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
                description="Reason about the classified request.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Reason about the classified request.",
            ),
            model_requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                minimum_context_window_tokens=64_000,
            ),
        ),
        outputs=(
            WorkflowValueBinding(
                name="resolution",
            ),
        ),
    )


def create_workflow_specification() -> WorkflowSpecification:
    """Create a deterministic two-step workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Classify and reason",
            description="Classify a request before reasoning about the result.",
            version="1.0.0",
        ),
        steps=(
            create_classification_step(),
            create_reasoning_step(),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create models suitable for different workflow steps."""

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
                context_window_tokens=32_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="reasoner",
                display_name="Provider B Reasoner",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                        ModelCapability.TOOL_USE,
                    }
                ),
                context_window_tokens=128_000,
            ),
            ModelMetadata(
                provider="provider-c",
                model="basic",
                display_name="Provider C Basic",
                context_window_tokens=128_000,
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
                response_text="billing",
            ),
            "provider-b/reasoner": StubLanguageModel(
                provider="provider-b",
                model="reasoner",
                response_text="resolved",
            ),
            "provider-c/basic": StubLanguageModel(
                provider="provider-c",
                model="basic",
                response_text="unused",
            ),
        }
    )


def generate_candidate() -> WorkflowCandidate:
    """Generate the standard deterministic workflow candidate."""

    return generate_workflow_candidate(
        specification=create_workflow_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )


def test_generation_preserves_workflow_metadata() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.metadata == specification.metadata


def test_generation_preserves_workflow_step_order() -> None:
    candidate = generate_candidate()

    assert len(candidate.steps) == 2
    assert tuple(step.strategy.metadata.name for step in candidate.steps) == (
        "Classify request [provider-a/classifier]",
        "Reason about request [provider-b/reasoner]",
    )


def test_generation_produces_prompt_strategy_steps() -> None:
    candidate = generate_candidate()

    assert all(isinstance(step.strategy, PromptStrategy) for step in candidate.steps)


def test_generation_preserves_step_scoped_model_requirements() -> None:
    specification = create_workflow_specification()
    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    classification = candidate.steps[0].strategy
    reasoning = candidate.steps[1].strategy

    assert isinstance(classification, PromptStrategy)
    assert isinstance(reasoning, PromptStrategy)

    assert (
        classification.model_requirements == specification.steps[0].specification.model_requirements
    )
    assert reasoning.model_requirements == specification.steps[1].specification.model_requirements
    assert classification.model_requirements != reasoning.model_requirements


def test_generation_preserves_step_scoped_model_bindings() -> None:
    candidate = generate_candidate()

    classification = candidate.steps[0].strategy
    reasoning = candidate.steps[1].strategy

    assert isinstance(classification, PromptStrategy)
    assert isinstance(reasoning, PromptStrategy)

    classification_binding = classification.model_binding
    reasoning_binding = reasoning.model_binding

    assert classification_binding is not None
    assert reasoning_binding is not None
    assert classification_binding.identifier == "provider-a/classifier"
    assert reasoning_binding.identifier == "provider-b/reasoner"
    assert classification_binding != reasoning_binding


def test_generation_preserves_workflow_value_bindings() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].outputs == specification.steps[0].outputs
    assert candidate.steps[1].outputs == specification.steps[1].outputs

    assert candidate.steps[0].outputs == (
        WorkflowValueBinding(
            name="classification",
        ),
    )
    assert candidate.steps[1].outputs == (
        WorkflowValueBinding(
            name="resolution",
        ),
    )


def test_generation_derives_deterministic_step_identities() -> None:
    first = generate_candidate()
    second = generate_candidate()

    assert tuple(step.strategy.metadata.id for step in first.steps) == tuple(
        step.strategy.metadata.id for step in second.steps
    )

    assert first.steps[0].strategy.metadata.id == uuid5(
        CLASSIFICATION_STRATEGY_ID,
        "provider-a/classifier",
    )
    assert first.steps[1].strategy.metadata.id == uuid5(
        REASONING_STRATEGY_ID,
        "provider-b/reasoner",
    )


def test_generated_steps_have_distinct_identities() -> None:
    candidate = generate_candidate()

    assert candidate.steps[0].strategy.metadata.id != candidate.steps[1].strategy.metadata.id


def test_generated_steps_are_executable() -> None:
    candidate = generate_candidate()

    outcomes = tuple(asyncio.run(step.strategy.run(Context())) for step in candidate.steps)

    assert tuple(outcome.output for outcome in outcomes) == (
        "billing",
        "resolved",
    )

    assert outcomes[0].metrics is not None
    assert outcomes[0].metrics.provider == "provider-a"
    assert outcomes[0].metrics.model == "classifier"

    assert outcomes[1].metrics is not None
    assert outcomes[1].metrics.provider == "provider-b"
    assert outcomes[1].metrics.model == "reasoner"


def test_generated_step_metrics_match_model_bindings() -> None:
    candidate = generate_candidate()

    for candidate_step in candidate.steps:
        strategy = candidate_step.strategy

        assert isinstance(strategy, PromptStrategy)

        outcome = asyncio.run(strategy.run(Context()))
        binding = strategy.model_binding
        metrics = outcome.metrics

        assert binding is not None
        assert metrics is not None
        assert binding.identifier == (f"{metrics.provider}/{metrics.model}")


def test_generation_is_deterministic() -> None:
    first = generate_candidate()
    second = generate_candidate()

    assert first.metadata == second.metadata

    assert tuple(step.strategy.metadata for step in first.steps) == tuple(
        step.strategy.metadata for step in second.steps
    )

    first_bindings = tuple(
        step.strategy.model_binding
        for step in first.steps
        if isinstance(step.strategy, PromptStrategy)
    )
    second_bindings = tuple(
        step.strategy.model_binding
        for step in second.steps
        if isinstance(step.strategy, PromptStrategy)
    )

    assert first_bindings == second_bindings

    assert tuple(step.outputs for step in first.steps) == tuple(
        step.outputs for step in second.steps
    )


def test_generation_fails_when_step_has_no_eligible_model() -> None:
    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Vision workflow",
            description="A workflow requiring an unavailable vision model.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        name="Describe image",
                        description="Describe an image.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Describe the supplied image.",
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

    with pytest.raises(WorkflowGenerationError):
        generate_workflow_candidate(
            specification=specification,
            catalog=create_catalog(),
            registry=create_registry(),
        )


def test_generation_fails_when_eligible_model_is_not_executable() -> None:
    registry = LanguageModelRegistry(
        models={
            "provider-a/classifier": StubLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text="billing",
            ),
        }
    )

    with pytest.raises(WorkflowGenerationError):
        generate_workflow_candidate(
            specification=create_workflow_specification(),
            catalog=create_catalog(),
            registry=registry,
        )


def test_generation_preserves_workflow_step_topology() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert tuple(step.id for step in candidate.steps) == tuple(
        step.id for step in specification.steps
    )
    assert tuple(step.depends_on for step in candidate.steps) == tuple(
        step.depends_on for step in specification.steps
    )


def test_generated_candidate_preserves_execution_layers() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    specification_layers = tuple(
        tuple(step.id for step in layer) for layer in specification.execution_layers()
    )
    candidate_layers = tuple(
        tuple(step.id for step in layer) for layer in candidate.execution_layers()
    )

    assert candidate_layers == specification_layers


def test_generated_candidate_planning_is_deterministic() -> None:
    specification = create_workflow_specification()
    catalog = create_catalog()
    registry = create_registry()

    first = generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
    )
    second = generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
    )

    assert tuple(tuple(step.id for step in layer) for layer in first.execution_layers()) == tuple(
        tuple(step.id for step in layer) for layer in second.execution_layers()
    )

    assert tuple(step.strategy.metadata.id for step in first.steps) == tuple(
        step.strategy.metadata.id for step in second.steps
    )
