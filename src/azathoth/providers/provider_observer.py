"""Observe provider model state and record meaningful changes."""

from pydantic import (
    BaseModel,
    ConfigDict,
)

from azathoth.providers.provider_directory import (
    ProviderModelDirectory,
)
from azathoth.providers.provider_models import (
    ProviderModel,
    ProviderModelObservation,
)
from azathoth.providers.provider_observation_repository import (
    ProviderModelObservationRepository,
)


class ProviderModelObservationUpdate(BaseModel):
    """Describe the durable result of observing one provider model."""

    model_config = ConfigDict(frozen=True)

    observation: ProviderModelObservation

    created: bool


class ProviderModelObserver:
    """Record provider model state when its normalized facts change."""

    def __init__(
        self,
        *,
        directory: ProviderModelDirectory,
        repository: ProviderModelObservationRepository,
    ) -> None:
        self._directory = directory
        self._repository = repository

    async def observe_model(
        self,
        identifier: str,
    ) -> ProviderModelObservationUpdate | None:
        """Observe one provider-native model identifier."""

        model = await self._directory.model(identifier)

        if model is None:
            return None

        self._validate_provider(model)

        return self._record(model)

    async def observe_models(
        self,
    ) -> tuple[
        ProviderModelObservationUpdate,
        ...,
    ]:
        """Observe every model currently exposed by the provider."""

        models = await self._directory.models()

        self._validate_models(models)

        return tuple(self._record(model) for model in models)

    def _record(
        self,
        model: ProviderModel,
    ) -> ProviderModelObservationUpdate:
        """Record model state only when provider facts changed."""

        latest = self._repository.latest(model.identifier)

        if latest is not None and latest.fingerprint == model.fingerprint:
            return ProviderModelObservationUpdate(
                observation=latest,
                created=False,
            )

        observation = ProviderModelObservation(model=model)

        self._repository.save(observation)

        return ProviderModelObservationUpdate(
            observation=observation,
            created=True,
        )

    def _validate_models(
        self,
        models: tuple[
            ProviderModel,
            ...,
        ],
    ) -> None:
        """Validate one complete provider directory response."""

        for model in models:
            self._validate_provider(model)

        identifiers = tuple(model.identifier for model in models)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Provider model directory cannot return duplicate model identifiers.")

    def _validate_provider(
        self,
        model: ProviderModel,
    ) -> None:
        """Ensure discovered model state belongs to the directory provider."""

        if model.provider != self._directory.provider:
            raise ValueError(
                "Provider model directory "
                f"{self._directory.provider!r} returned "
                f"model {model.identifier!r}."
            )
