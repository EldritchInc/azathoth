"""Deterministic in-memory persistence for provider model observations."""

from uuid import UUID

from azathoth.providers.provider_models import (
    ProviderModelObservation,
)
from azathoth.providers.provider_observation_repository import (
    ProviderModelObservationRepository,
)


class InMemoryProviderModelObservationRepository:
    """Store immutable provider model observations in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._observations: dict[
            UUID,
            ProviderModelObservation,
        ] = {}

    def save(
        self,
        observation: ProviderModelObservation,
    ) -> None:
        """Persist one observation without replacing existing evidence."""

        if observation.id in self._observations:
            raise ValueError(
                "Provider model observation "
                f"{observation.id} already exists."
            )

        self._observations[
            observation.id
        ] = observation

    def get(
        self,
        observation_id: UUID,
    ) -> ProviderModelObservation | None:
        """Return one observation by identifier."""

        return self._observations.get(
            observation_id
        )

    def observations(
        self,
    ) -> tuple[
        ProviderModelObservation,
        ...,
    ]:
        """Return all observations in insertion order."""

        return tuple(
            self._observations.values()
        )

    def observations_for_model(
        self,
        identifier: str,
    ) -> tuple[
        ProviderModelObservation,
        ...,
    ]:
        """Return observations for one model in insertion order."""

        return tuple(
            observation
            for observation in self._observations.values()
            if observation.identifier == identifier
        )

    def latest(
        self,
        identifier: str,
    ) -> ProviderModelObservation | None:
        """Return the latest persisted observation for one model."""

        observations = self.observations_for_model(
            identifier
        )

        if not observations:
            return None

        return observations[-1]


def require_provider_model_observation_repository(
    repository: ProviderModelObservationRepository,
) -> ProviderModelObservationRepository:
    """Return a repository after static protocol validation."""

    return repository
