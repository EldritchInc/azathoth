"""Persistence contracts for configured language model metadata."""

from typing import Protocol

from azathoth.providers.models import ModelMetadata


class ModelRepository(Protocol):
    """Persist and retrieve configured language model metadata."""

    def save(
        self,
        model: ModelMetadata,
    ) -> None:
        """Persist one configured language model."""

        ...

    def get(
        self,
        identifier: str,
    ) -> ModelMetadata | None:
        """Return one configured model by provider-qualified identifier."""

        ...

    def models(
        self,
    ) -> tuple[ModelMetadata, ...]:
        """Return all configured models in insertion order."""

        ...

    def models_for_provider(
        self,
        provider: str,
    ) -> tuple[ModelMetadata, ...]:
        """Return configured models belonging to one provider."""

        ...
