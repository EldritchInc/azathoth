"""Persistence contracts for provider model observations."""

from typing import Protocol
from uuid import UUID

from azathoth.providers.provider_models import (
    ProviderModelObservation,
)


class ProviderModelObservationRepository(Protocol):
    """Persist and retrieve immutable provider model observations."""

    def save(
        self,
        observation: ProviderModelObservation,
    ) -> None:
        """Persist one provider model observation."""

        ...

    def get(
        self,
        observation_id: UUID,
    ) -> ProviderModelObservation | None:
        """Return one provider model observation by identifier."""

        ...

    def observations(
        self,
    ) -> tuple[ProviderModelObservation, ...]:
        """Return all observations in insertion order."""

        ...

    def observations_for_model(
        self,
        identifier: str,
    ) -> tuple[ProviderModelObservation, ...]:
        """Return observations for one provider-qualified model."""

        ...

    def latest(
        self,
        identifier: str,
    ) -> ProviderModelObservation | None:
        """Return the latest persisted observation for one model."""

        ...
