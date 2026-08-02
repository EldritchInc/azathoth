"""Immutable catalog of language models available to Azathoth."""

from pydantic import BaseModel, ConfigDict, model_validator

from azathoth.providers.models import ModelMetadata


class ModelCatalog(BaseModel):
    """A reproducible inventory of configured language models."""

    model_config = ConfigDict(frozen=True)

    models: tuple[ModelMetadata, ...] = ()

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "ModelCatalog":
        """Reject duplicate provider-qualified model identifiers."""

        identifiers = tuple(model.identifier for model in self.models)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Model catalog cannot contain duplicate model identifiers.")

        return self

    @property
    def identifiers(self) -> tuple[str, ...]:
        """Return model identifiers in catalog order."""

        return tuple(model.identifier for model in self.models)

    @property
    def providers(self) -> tuple[str, ...]:
        """Return provider names in first-seen order."""

        return tuple(dict.fromkeys(model.provider for model in self.models))

    def get(self, identifier: str) -> ModelMetadata | None:
        """Return a model by provider-qualified identifier."""

        return next(
            (model for model in self.models if model.identifier == identifier),
            None,
        )

    def models_for_provider(
        self,
        provider: str,
    ) -> tuple[ModelMetadata, ...]:
        """Return all models registered for one provider."""

        return tuple(model for model in self.models if model.provider == provider)
