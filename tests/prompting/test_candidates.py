"""Tests for generating executable prompt strategy candidates."""

import asyncio
from uuid import UUID, uuid5

from azathoth.context import Context
from azathoth.prompting import (
    PortfolioModelSelection,
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
from azathoth.strategies import StrategyMetadata
from tests.model_authorization import (
    generate_prompt_candidates,
)

SPECIFICATION_ID = UUID("7a0af90c-53dc-4329-aa19-2c38887949fa")


class StubLanguageModel:
    """A deterministic language model with a configured response."""

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
        """Record the prompt and return the configured response."""

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


def create_specification() -> PromptStrategySpec:
    """Create a deterministic structured-output workload."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=SPECIFICATION_ID,
            name="Classify support request",
            description="Return the support category.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Classify this support request.",
        ),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                minimum_context_window_tokens=32_000,
            )
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a catalog containing eligible and ineligible models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="small",
                display_name="Provider A Small",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=64_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="large",
                display_name="Provider B Large",
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
                model="plain",
                display_name="Provider C Plain",
                context_window_tokens=128_000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable models matching two catalog entries."""

    return LanguageModelRegistry(
        models={
            "provider-a/small": StubLanguageModel(
                provider="provider-a",
                model="small",
                response_text="provider-a-result",
            ),
            "provider-b/large": StubLanguageModel(
                provider="provider-b",
                model="large",
                response_text="provider-b-result",
            ),
            "provider-c/plain": StubLanguageModel(
                provider="provider-c",
                model="plain",
                response_text="provider-c-result",
            ),
        }
    )


def require_portfolio_requirements(
    specification: PromptStrategySpec,
) -> ModelRequirements:
    """Return requirements from a portfolio-selected prompt specification."""

    selection = specification.model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )

    return selection.requirements


def test_generate_candidates_for_every_eligible_executable_model() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert len(candidates) == 2
    assert tuple(candidate.metadata.name for candidate in candidates) == (
        "Classify support request [provider-a/small]",
        "Classify support request [provider-b/large]",
    )


def test_generated_candidates_preserve_catalog_order() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert tuple(candidate.metadata.name for candidate in candidates) == (
        "Classify support request [provider-a/small]",
        "Classify support request [provider-b/large]",
    )


def test_generated_candidates_preserve_prompt_and_requirements() -> None:
    specification = create_specification()

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert all(candidate.prompt == specification.prompt for candidate in candidates)
    assert all(
        candidate.model_requirements == require_portfolio_requirements(specification)
        for candidate in candidates
    )


def test_generated_candidate_identity_is_deterministic_per_model() -> None:
    specification = create_specification()

    first_generation = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )
    second_generation = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert tuple(candidate.metadata.id for candidate in first_generation) == tuple(
        candidate.metadata.id for candidate in second_generation
    )

    assert first_generation[0].metadata.id == uuid5(
        SPECIFICATION_ID,
        "provider-a/small",
    )
    assert first_generation[1].metadata.id == uuid5(
        SPECIFICATION_ID,
        "provider-b/large",
    )


def test_generated_candidates_bind_distinct_language_models() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    outcomes = tuple(asyncio.run(candidate.run(Context())) for candidate in candidates)

    assert tuple(outcome.output for outcome in outcomes) == (
        "provider-a-result",
        "provider-b-result",
    )

    assert outcomes[0].metrics is not None
    assert outcomes[0].metrics.provider == "provider-a"
    assert outcomes[0].metrics.model == "small"

    assert outcomes[1].metrics is not None
    assert outcomes[1].metrics.provider == "provider-b"
    assert outcomes[1].metrics.model == "large"


def test_generation_skips_eligible_model_missing_from_registry() -> None:
    registry = LanguageModelRegistry(
        models={
            "provider-a/small": StubLanguageModel(
                provider="provider-a",
                model="small",
                response_text="provider-a-result",
            ),
        }
    )

    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=registry,
    )

    assert len(candidates) == 1
    assert candidates[0].metadata.name == ("Classify support request [provider-a/small]")


def test_generation_returns_empty_tuple_when_no_models_are_eligible() -> None:
    specification = PromptStrategySpec(
        metadata=StrategyMetadata(
            name="Vision workflow",
            description="Perform a vision-dependent task.",
        ),
        prompt=Prompt(
            text="Describe the supplied image.",
        ),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.VISION,
                    }
                ),
            )
        ),
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidates == ()


def test_generation_returns_empty_tuple_for_empty_registry() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=LanguageModelRegistry(),
    )

    assert candidates == ()


def test_generated_candidates_have_model_bindings() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert len(candidates) == 2

    bindings = tuple(candidate.model_binding for candidate in candidates)

    assert all(binding is not None for binding in bindings)
    assert tuple(binding.identifier for binding in bindings if binding is not None) == (
        "provider-a/small",
        "provider-b/large",
    )


def test_candidate_identity_is_derived_from_specification_and_model() -> None:
    specification = create_specification()

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    for candidate in candidates:
        binding = candidate.model_binding

        assert binding is not None
        assert candidate.metadata.id == uuid5(
            specification.metadata.id,
            binding.identifier,
        )


def test_different_model_bindings_get_distinct_candidate_ids() -> None:
    candidates = generate_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert len(candidates) == 2
    assert candidates[0].metadata.id != candidates[1].metadata.id


def test_different_specifications_get_distinct_candidate_ids() -> None:
    first_specification = create_specification()
    second_specification = first_specification.model_copy(
        update={
            "metadata": StrategyMetadata(
                id=UUID("946d33fd-f74c-45af-b899-405b386d409f"),
                name=first_specification.metadata.name,
                description=first_specification.metadata.description,
                version=first_specification.metadata.version,
            )
        }
    )

    first_candidate = generate_prompt_candidates(
        specification=first_specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )[0]
    second_candidate = generate_prompt_candidates(
        specification=second_specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )[0]

    assert first_candidate.metadata.id != second_candidate.metadata.id


def test_generated_candidate_preserves_specification_configuration() -> None:
    specification = create_specification()

    candidate = generate_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )[0]

    assert candidate.prompt == specification.prompt
    assert candidate.model_requirements == candidate.model_requirements
    assert candidate.metadata.description == specification.metadata.description
    assert candidate.metadata.version == specification.metadata.version
