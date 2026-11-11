"""Generate executable context-aware prompt strategy candidates."""

from uuid import uuid5

from azathoth.prompting.context_strategy import (
    ContextPromptStrategy,
)
from azathoth.prompting.model_selection import (
    PortfolioModelSelection,
)
from azathoth.prompting.models import ModelBinding
from azathoth.prompting.specifications import (
    ContextPromptStrategySpec,
)
from azathoth.providers import (
    LanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelQuery,
    ModelRequirements,
    model_catalog_for_portfolio,
)
from azathoth.sensitivity import DataPolicy, Sensitivity, may_receive
from azathoth.strategies import StrategyMetadata


def generate_context_prompt_candidates(
    specification: ContextPromptStrategySpec,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    *,
    portfolio: ModelPortfolio,
    sensitivity: Sensitivity | None = None,
) -> tuple[ContextPromptStrategy, ...]:
    """Generate executable context prompt candidates allowed by authority.

    Each candidate holds its model's declared data policy from the portfolio,
    or None for a model outside it (ADR 0123). For a run labelled
    `sensitivity`, the candidates whose model may receive input so labelled
    come first, in their own order; the rest follow, so a restricted run
    that has no such model is refused, saying why, when it sends.
    """

    selection = specification.model_selection

    if isinstance(
        selection,
        PortfolioModelSelection,
    ):
        portfolio_catalog = model_catalog_for_portfolio(
            catalog=catalog,
            portfolio=portfolio,
        )

        eligible_models = portfolio_catalog.find(
            ModelQuery.from_requirements(
                selection.requirements,
            )
        )

        model_requirements: ModelRequirements | None = selection.requirements
    else:
        fixed_model = catalog.get(
            selection.identifier,
        )

        eligible_models = (fixed_model,) if fixed_model is not None else ()

        model_requirements = None

    candidates: list[ContextPromptStrategy] = []

    for model_metadata in eligible_models:
        language_model = registry.get(
            model_metadata.identifier,
        )

        if language_model is None:
            continue

        entry = portfolio.get(model_metadata.identifier)

        candidates.append(
            _build_candidate(
                specification=specification,
                model_metadata=model_metadata,
                language_model=language_model,
                model_requirements=model_requirements,
                data_policy=None if entry is None else entry.data_policy,
            )
        )

    return (
        *(candidate for candidate in candidates if _receives(candidate, sensitivity)),
        *(candidate for candidate in candidates if not _receives(candidate, sensitivity)),
    )


def _receives(
    candidate: ContextPromptStrategy,
    sensitivity: Sensitivity | None,
) -> bool:
    """Return whether a candidate's model may receive input with this label."""

    return may_receive(candidate.data_policy, sensitivity)


def _build_candidate(
    *,
    specification: ContextPromptStrategySpec,
    model_metadata: ModelMetadata,
    language_model: LanguageModel,
    model_requirements: ModelRequirements | None,
    data_policy: DataPolicy | None,
) -> ContextPromptStrategy:
    """Build one executable context-aware prompt strategy candidate."""

    return ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=uuid5(
                specification.metadata.id,
                model_metadata.identifier,
            ),
            name=(f"{specification.metadata.name} [{model_metadata.identifier}]"),
            description=specification.metadata.description,
            version=specification.metadata.version,
        ),
        template=specification.template,
        language_model=language_model,
        model_requirements=model_requirements,
        model_binding=ModelBinding(
            identifier=model_metadata.identifier,
        ),
        output_format=specification.output_format,
        model_input_modalities=model_metadata.input_modalities,
        citations=specification.citations,
        data_policy=data_policy,
    )
