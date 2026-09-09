"""Tests for context-aware prompt candidate generation."""

from uuid import UUID

from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
    generate_context_prompt_candidates,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelRequirements,
)
from azathoth.strategies import StrategyMetadata

STRATEGY_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_IDENTIFIER = "provider-a/classifier"
SECOND_IDENTIFIER = "provider-b/classifier"


def create_specification(
    *,
    fixed: bool = False,
) -> ContextPromptStrategySpec:
    """Create one durable context-aware prompt specification."""

    selection = (
        FixedModelSelection(
            provider="provider-a",
            model="classifier",
        )
        if fixed
        else PortfolioModelSelection(
            requirements=ModelRequirements(),
        )
    )

    return ContextPromptStrategySpec(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="Classify request",
            description="Classify one externally supplied request.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Classify: {request}",
            bindings=(
                PromptBinding(
                    variable_name="request",
                    event_type="request.received",
                    field_name="input",
                ),
            ),
        ),
        model_selection=selection,
    )


def create_catalog() -> ModelCatalog:
    """Create deterministic model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="classifier",
                display_name="Provider A Classifier",
                context_window_tokens=8_192,
            ),
            ModelMetadata(
                provider="provider-b",
                model="classifier",
                display_name="Provider B Classifier",
                context_window_tokens=8_192,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create deterministic executable language models."""

    return LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: DeterministicLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text="positive",
            ),
            SECOND_IDENTIFIER: DeterministicLanguageModel(
                provider="provider-b",
                model="classifier",
                response_text="positive",
            ),
        }
    )


def create_portfolio() -> ModelPortfolio:
    """Authorize both deterministic models."""

    return ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider="provider-a",
                model="classifier",
            ),
            ModelPortfolioEntry(
                provider="provider-b",
                model="classifier",
            ),
        )
    )


def test_context_prompt_candidates_generate_authorized_models() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
    )

    assert len(candidates) == 2

    assert all(
        isinstance(
            candidate,
            ContextPromptStrategy,
        )
        for candidate in candidates
    )

    assert tuple(
        candidate.model_binding.identifier
        for candidate in candidates
        if candidate.model_binding is not None
    ) == (
        FIRST_IDENTIFIER,
        SECOND_IDENTIFIER,
    )


def test_context_prompt_candidates_preserve_template() -> None:
    specification = create_specification()

    candidates = generate_context_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
    )

    assert all(candidate.template == specification.template for candidate in candidates)


def test_context_prompt_candidates_preserve_metadata() -> None:
    specification = create_specification()

    candidates = generate_context_prompt_candidates(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
    )

    assert tuple(candidate.metadata.description for candidate in candidates) == (
        specification.metadata.description,
        specification.metadata.description,
    )

    assert tuple(candidate.metadata.version for candidate in candidates) == (
        specification.metadata.version,
        specification.metadata.version,
    )


def test_context_prompt_candidates_are_deterministically_identified() -> None:
    first = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
    )

    second = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
    )

    assert tuple(candidate.metadata.id for candidate in first) == tuple(
        candidate.metadata.id for candidate in second
    )


def test_context_prompt_candidates_respect_fixed_model_selection() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(
            fixed=True,
        ),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=ModelPortfolio(),
    )

    assert len(candidates) == 1

    binding = candidates[0].model_binding

    assert binding is not None
    assert binding.identifier == FIRST_IDENTIFIER


def test_context_prompt_candidates_require_executable_models() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=LanguageModelRegistry(models={}),
        portfolio=create_portfolio(),
    )

    assert candidates == ()


def test_context_prompt_candidates_require_portfolio_authorization() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=ModelPortfolio(),
    )

    assert candidates == ()
