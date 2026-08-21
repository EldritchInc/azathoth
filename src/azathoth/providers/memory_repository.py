"""Deterministic in-memory persistence for configured language models."""

from azathoth.providers.models import ModelMetadata
from azathoth.providers.repository import ModelRepository


class InMemoryModelRepository:
    """Store immutable model metadata in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._models: dict[
            str,
            ModelMetadata,
        ] = {}

    def save(
        self,
        model: ModelMetadata,
    ) -> None:
        """Persist one model without replacing existing configuration."""

        identifier = model.identifier

        if identifier in self._models:
            raise ValueError(f"Model {identifier!r} already exists.")

        self._models[identifier] = model

    def get(
        self,
        identifier: str,
    ) -> ModelMetadata | None:
        """Return one configured model by identifier."""

        return self._models.get(identifier)

    def models(
        self,
    ) -> tuple[ModelMetadata, ...]:
        """Return all configured models in insertion order."""

        return tuple(self._models.values())

    def models_for_provider(
        self,
        provider: str,
    ) -> tuple[ModelMetadata, ...]:
        """Return configured models belonging to one provider."""

        return tuple(model for model in self._models.values() if model.provider == provider)


def require_model_repository(
    repository: ModelRepository,
) -> ModelRepository:
    """Return a repository after static protocol validation."""

    return repository
