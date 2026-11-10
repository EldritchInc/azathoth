"""Persistence contracts for organizational model portfolios."""

from typing import Protocol

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_provenance import PortfolioProvenance
from azathoth.revisions import Author
from azathoth.sensitivity import DataPolicy


class ModelPortfolioRepository(Protocol):
    """Persist and retrieve authorized model portfolio entries."""

    def save(
        self,
        entry: ModelPortfolioEntry,
        *,
        author: Author | None = None,
    ) -> None:
        """Persist one authorized model entry, and record who added it and when (ADR 0122)."""

        ...

    def provenance(
        self,
        identifier: str,
    ) -> PortfolioProvenance | None:
        """Return who added one portfolio entry and when, if it is in the portfolio."""

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

    def delete(
        self,
        identifier: str,
    ) -> None:
        """Delete one authorized model entry and its provenance."""

        ...

    def set_data_policy(
        self,
        identifier: str,
        policy: DataPolicy,
    ) -> ModelPortfolioEntry:
        """Declare what one entry's provider does with data, and return the entry (ADR 0123).

        The entry keeps its place in the portfolio and its provenance, which
        records who added it.

        Raises:
            ValueError: The entry does not exist.
        """

        ...
