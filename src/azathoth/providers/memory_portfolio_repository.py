"""Deterministic in-memory persistence for model portfolio entries."""

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_repository import (
    ModelPortfolioRepository,
)


class InMemoryModelPortfolioRepository:
    """Store authorized model portfolio entries in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._entries: dict[
            str,
            ModelPortfolioEntry,
        ] = {}

    def save(
        self,
        entry: ModelPortfolioEntry,
    ) -> None:
        """Persist one entry without replacing existing policy."""

        if entry.identifier in self._entries:
            raise ValueError(f"Model portfolio entry {entry.identifier!r} already exists.")

        self._entries[entry.identifier] = entry

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
        """Delete one authorized model entry."""

        if identifier not in self._entries:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

        del self._entries[identifier]

    def entries(
        self,
    ) -> tuple[
        ModelPortfolioEntry,
        ...,
    ]:
        """Return all portfolio entries in insertion order."""

        return tuple(self._entries.values())


def require_model_portfolio_repository(
    repository: ModelPortfolioRepository,
) -> ModelPortfolioRepository:
    """Return a repository after static protocol validation."""

    return repository
