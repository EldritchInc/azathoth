"""Deterministic in-memory persistence for model portfolio entries."""

from datetime import UTC, datetime

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_provenance import PortfolioProvenance
from azathoth.providers.portfolio_repository import (
    ModelPortfolioRepository,
)
from azathoth.revisions import Author, content_digest
from azathoth.sensitivity import DataPolicy


class InMemoryModelPortfolioRepository:
    """Store authorized model portfolio entries in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._entries: dict[
            str,
            ModelPortfolioEntry,
        ] = {}

        self._provenance: dict[
            str,
            PortfolioProvenance,
        ] = {}

    def save(
        self,
        entry: ModelPortfolioEntry,
        *,
        author: Author | None = None,
    ) -> None:
        """Persist one entry without replacing existing policy, and record its provenance."""

        if entry.identifier in self._entries:
            raise ValueError(f"Model portfolio entry {entry.identifier!r} already exists.")

        self._entries[entry.identifier] = entry
        self._provenance[entry.identifier] = PortfolioProvenance(
            identifier=entry.identifier,
            content_digest=content_digest(entry),
            author=author,
            added_at=datetime.now(UTC),
        )

    def provenance(
        self,
        identifier: str,
    ) -> PortfolioProvenance | None:
        """Return who added one portfolio entry and when, if it is in the portfolio."""

        return self._provenance.get(identifier)

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one portfolio entry by identifier."""

        return self._entries.get(identifier)

    def delete(
        self,
        identifier: str,
    ) -> None:
        """Delete one authorized model entry and its provenance."""

        if identifier not in self._entries:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

        del self._entries[identifier]
        del self._provenance[identifier]

    def entries(
        self,
    ) -> tuple[
        ModelPortfolioEntry,
        ...,
    ]:
        """Return all portfolio entries in insertion order."""

        return tuple(self._entries.values())

    def set_data_policy(
        self,
        identifier: str,
        policy: DataPolicy,
    ) -> ModelPortfolioEntry:
        """Declare what one entry's provider does with data, keeping its place and provenance.

        Raises:
            ValueError: The entry does not exist.
        """

        entry = self._entries.get(identifier)

        if entry is None:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

        declared = entry.model_copy(update={"data_policy": policy})

        self._entries[identifier] = declared

        return declared


def require_model_portfolio_repository(
    repository: ModelPortfolioRepository,
) -> ModelPortfolioRepository:
    """Return a repository after static protocol validation."""

    return repository
