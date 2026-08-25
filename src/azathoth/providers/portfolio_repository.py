"""Persistence contracts for organizational model portfolios."""

from typing import Protocol

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)


class ModelPortfolioRepository(Protocol):
    """Persist and retrieve authorized model portfolio entries."""

    def save(
        self,
        entry: ModelPortfolioEntry,
    ) -> None:
        """Persist one authorized model entry."""

        ...

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one authorized model by provider-qualified identifier."""

        ...

    def entries(
        self,
    ) -> tuple[
        ModelPortfolioEntry,
        ...,
    ]:
        """Return all authorized models in insertion order."""

        ...
