"""Deterministic in-memory persistence for model portfolio entries."""

from datetime import UTC, datetime

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_provenance import PolicyDeclaration, PortfolioProvenance
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

        self._declarations: dict[
            str,
            PolicyDeclaration,
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

        added_at = datetime.now(UTC)

        self._entries[entry.identifier] = entry
        self._provenance[entry.identifier] = PortfolioProvenance(
            identifier=entry.identifier,
            content_digest=content_digest(entry),
            author=author,
            added_at=added_at,
        )

        if not entry.data_policy.unknown:
            self._declarations[entry.identifier] = PolicyDeclaration(
                identifier=entry.identifier,
                author=author,
                declared_at=added_at,
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
        self._declarations.pop(identifier, None)

    def policy_declaration(
        self,
        identifier: str,
    ) -> PolicyDeclaration | None:
        """Return who declared one entry's data policy and when, if it was declared."""

        return self._declarations.get(identifier)

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
        *,
        author: Author | None = None,
    ) -> ModelPortfolioEntry:
        """Declare what one entry's provider does with data, keeping its place and provenance.

        Who declared it, and when, replace any earlier declaration.

        Raises:
            ValueError: The entry does not exist.
        """

        entry = self._entries.get(identifier)

        if entry is None:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

        declared = entry.model_copy(update={"data_policy": policy})

        self._entries[identifier] = declared
        self._declarations[identifier] = PolicyDeclaration(
            identifier=identifier,
            author=author,
            declared_at=datetime.now(UTC),
        )

        return declared


def require_model_portfolio_repository(
    repository: ModelPortfolioRepository,
) -> ModelPortfolioRepository:
    """Return a repository after static protocol validation."""

    return repository
