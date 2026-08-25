"""Provider-neutral discovery contracts for language model state."""

from typing import Protocol

from azathoth.providers.provider_models import ProviderModel


class ProviderModelDirectory(Protocol):
    """Discover current model state from one language model provider."""

    @property
    def provider(
        self,
    ) -> str:
        """Return the stable provider identifier."""

        ...

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return the provider's currently discoverable models."""

        ...

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one currently discoverable provider model."""

        ...
