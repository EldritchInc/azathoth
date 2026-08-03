"""Generate executable prompt strategy candidates."""

from uuid import uuid5

from azathoth.prompting.models import ModelBinding
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
    """Generate executable candidates for eligible registered models."""

    eligible_models = catalog.find(
        ModelQuery.from_requirements(
            specification.model_requirements
        )
    )

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
            description=specification.metadata.description,
            version=specification.metadata.version,
        )

        candidates.append(
            PromptStrategy(
                metadata=candidate_metadata,
                prompt=specification.prompt,
                language_model=language_model,
                model_requirements=specification.model_requirements,
                model_binding=ModelBinding(
                    identifier=model_metadata.identifier,
                ),
            )
        )

    return tuple(candidates)