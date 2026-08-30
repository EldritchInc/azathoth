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
    ModelPortfolio,
    ModelPortfolioEntry,
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


def test_portfolio_selection_generates_all_eligible_authorized_models() -> None:
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

    catalog = ModelCatalog(
        models=(
            first,
            second,
            third,
        )
    )

    portfolio = ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider=first.provider,
                model=first.model,
            ),
            ModelPortfolioEntry(
                provider=second.provider,
                model=second.model,
            ),
            ModelPortfolioEntry(
                provider=third.provider,
                model=third.model,
            ),
        )
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
        catalog=catalog,
        registry=create_registry(
            first,
            second,
            third,
        ),
        portfolio=portfolio,
    )

    assert tuple(
        candidate.model_binding.identifier
        for candidate in candidates
        if candidate.model_binding is not None
    ) == (
        "example/first",
        "example/third",
    )


def test_portfolio_selection_excludes_current_unauthorized_model() -> None:
    authorized = create_metadata(
        model="authorized",
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
    )

    unauthorized = create_metadata(
        model="unauthorized",
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
                authorized,
                unauthorized,
            )
        ),
        registry=create_registry(
            authorized,
            unauthorized,
        ),
        portfolio=ModelPortfolio(
            entries=(
                ModelPortfolioEntry(
                    provider=authorized.provider,
                    model=authorized.model,
                ),
            )
        ),
    )

    assert len(candidates) == 1

    binding = candidates[0].model_binding

    assert binding is not None
    assert binding.identifier == authorized.identifier


def test_fixed_selection_generates_required_model_outside_portfolio() -> None:
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
        portfolio=ModelPortfolio(),
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
        portfolio=ModelPortfolio(),
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
        portfolio=ModelPortfolio(),
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
        portfolio=ModelPortfolio(),
    )

    assert len(candidates) == 1
    assert candidates[0].model_requirements is None
