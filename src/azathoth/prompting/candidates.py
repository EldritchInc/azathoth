"""Generate executable prompt strategy candidates from specifications."""

from uuid import uuid5

from azathoth.prompting.specifications import PromptStrategySpec
from azathoth.prompting.strategy import PromptStrategy
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelQuery,
)
from azathoth.strategies import StrategyMetadata


def generate_prompt_candidates(
    specification: PromptStrategySpec,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> tuple[PromptStrategy, ...]:
    """Generate one executable strategy for each eligible available model."""

    query = ModelQuery.from_requirements(
        specification.model_requirements
    )
    eligible_models = catalog.find(query)

    candidates: list[PromptStrategy] = []

    for model_metadata in eligible_models:
        language_model = registry.get(model_metadata.identifier)

        if language_model is None:
            continue

        candidate_metadata = StrategyMetadata(
            id=uuid5(
                specification.metadata.id,
                model_metadata.identifier,
            ),
            name=(
                f"{specification.metadata.name} "
                f"[{model_metadata.identifier}]"
            ),
            description=(
                f"{specification.metadata.description} "
                f"Executed using {model_metadata.identifier}."
            ),
            version=specification.metadata.version,
        )

        candidates.append(
            PromptStrategy(
                metadata=candidate_metadata,
                prompt=specification.prompt,
                language_model=language_model,
                model_requirements=specification.model_requirements,
            )
        )

    return tuple(candidates)