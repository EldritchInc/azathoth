"""Generate executable prompt strategy candidates."""

from uuid import uuid5

from azathoth.prompting.model_selection import (
    PortfolioModelSelection,
)
from azathoth.prompting.models import ModelBinding
from azathoth.prompting.specifications import PromptStrategySpec
from azathoth.prompting.strategy import PromptStrategy
from azathoth.providers import (
    LanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelQuery,
    ModelRequirements,
)
from azathoth.strategies import StrategyMetadata


def generate_prompt_candidates(
    specification: PromptStrategySpec,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> tuple[PromptStrategy, ...]:
    """Generate executable candidates allowed by model-selection authority."""

    selection = specification.model_selection

    if isinstance(
        selection,
        PortfolioModelSelection,
    ):
        eligible_models = catalog.find(ModelQuery.from_requirements(selection.requirements))
        model_requirements: ModelRequirements | None = selection.requirements
    else:
        fixed_model = catalog.get(selection.identifier)

        eligible_models = (fixed_model,) if fixed_model is not None else ()
        model_requirements = None

    candidates: list[PromptStrategy] = []

    for model_metadata in eligible_models:
        language_model = registry.get(model_metadata.identifier)

        if language_model is None:
            continue

        candidates.append(
            _build_candidate(
                specification=specification,
                model_metadata=model_metadata,
                language_model=language_model,
                model_requirements=model_requirements,
            )
        )

    return tuple(candidates)


def _build_candidate(
    *,
    specification: PromptStrategySpec,
    model_metadata: ModelMetadata,
    language_model: LanguageModel,
    model_requirements: ModelRequirements | None,
) -> PromptStrategy:
    """Build one executable prompt strategy candidate."""

    return PromptStrategy(
        metadata=StrategyMetadata(
            id=uuid5(
                specification.metadata.id,
                model_metadata.identifier,
            ),
            name=(f"{specification.metadata.name} [{model_metadata.identifier}]"),
            description=specification.metadata.description,
            version=specification.metadata.version,
        ),
        prompt=specification.prompt,
        language_model=language_model,
        model_requirements=model_requirements,
        model_binding=ModelBinding(
            identifier=model_metadata.identifier,
        ),
    )
