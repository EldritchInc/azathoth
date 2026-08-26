"""Tests for prompt candidate model-selection authority."""

from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
    generate_prompt_candidates,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata


def create_metadata(
    *,
    model: str,
    capabilities: frozenset[ModelCapability] = frozenset(),
) -> ModelMetadata:
    """Create deterministic model metadata."""

    return ModelMetadata(
        provider="example",
        model=model,
        display_name=model,
        capabilities=capabilities,
        context_window_tokens=128_000,
    )


def create_registry(
    *models: ModelMetadata,
) -> LanguageModelRegistry:
    """Create executable deterministic models for metadata."""

    return LanguageModelRegistry(
        models={
            model.identifier: DeterministicLanguageModel(
                provider=model.provider,
                model=model.model,
            )
            for model in models
        }
    )


def create_specification(
    *,
    model_selection: PortfolioModelSelection | FixedModelSelection,
) -> PromptStrategySpec:
    """Create one deterministic prompt specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            name="example",
            description="Example prompt strategy.",
        ),
        prompt=Prompt(text="Return success."),
        model_selection=model_selection,
    )


def test_portfolio_selection_generates_all_eligible_executable_models() -> None:
    first = create_metadata(
        model="first",
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
    )
    second = create_metadata(
        model="second",
    )
    third = create_metadata(
        model="third",
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
    )

    specification = create_specification(
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                )
            )
        )
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(
            models=(
                first,
                second,
                third,
            )
        ),
        registry=create_registry(
            first,
            second,
            third,
        ),
    )

    assert tuple(
        candidate.model_binding.identifier
        for candidate in candidates
        if candidate.model_binding is not None
    ) == (
        "example/first",
        "example/third",
    )


def test_fixed_selection_generates_only_required_model() -> None:
    first = create_metadata(
        model="first",
    )
    second = create_metadata(
        model="second",
    )

    specification = create_specification(
        model_selection=FixedModelSelection(
            provider="example",
            model="second",
        )
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(
            models=(
                first,
                second,
            )
        ),
        registry=create_registry(
            first,
            second,
        ),
    )

    assert len(candidates) == 1

    binding = candidates[0].model_binding

    assert binding is not None
    assert binding.identifier == "example/second"


def test_fixed_selection_does_not_substitute_missing_model() -> None:
    available = create_metadata(
        model="available",
    )

    specification = create_specification(
        model_selection=FixedModelSelection(
            provider="example",
            model="missing",
        )
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(models=(available,)),
        registry=create_registry(
            available,
        ),
    )

    assert candidates == ()


def test_fixed_selection_requires_executable_registered_model() -> None:
    fixed = create_metadata(
        model="fixed",
    )

    specification = create_specification(
        model_selection=FixedModelSelection(
            provider="example",
            model="fixed",
        )
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(models=(fixed,)),
        registry=LanguageModelRegistry(),
    )

    assert candidates == ()


def test_fixed_selection_candidate_has_no_selection_requirements() -> None:
    fixed = create_metadata(
        model="fixed",
    )

    specification = create_specification(
        model_selection=FixedModelSelection(
            provider="example",
            model="fixed",
        )
    )

    candidates = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(models=(fixed,)),
        registry=create_registry(
            fixed,
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].model_requirements is None
