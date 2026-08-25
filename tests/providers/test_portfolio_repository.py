"""Tests for model portfolio persistence."""

import pytest

from azathoth.providers import (
    InMemoryModelPortfolioRepository,
    ModelPortfolioEntry,
    ModelPortfolioRepository,
    require_model_portfolio_repository,
)


def create_entry(
    *,
    provider: str = "openrouter",
    model: str = "example/frontier",
) -> ModelPortfolioEntry:
    """Create one deterministic portfolio entry."""

    return ModelPortfolioEntry(
        provider=provider,
        model=model,
    )


def test_memory_portfolio_repository_satisfies_protocol() -> None:
    repository = InMemoryModelPortfolioRepository()

    resolved = require_model_portfolio_repository(repository)

    assert resolved is repository


def test_memory_portfolio_repository_persists_entry() -> None:
    repository: ModelPortfolioRepository = InMemoryModelPortfolioRepository()

    entry = create_entry()

    repository.save(entry)

    assert repository.get(entry.identifier) is entry


def test_memory_portfolio_repository_returns_none_for_unknown_entry() -> None:
    repository: ModelPortfolioRepository = InMemoryModelPortfolioRepository()

    assert repository.get("openrouter/example/missing") is None


def test_memory_portfolio_repository_preserves_insertion_order() -> None:
    repository: ModelPortfolioRepository = InMemoryModelPortfolioRepository()

    first = create_entry(model="example/alpha")

    second = create_entry(model="example/beta")

    third = create_entry(
        provider="other",
        model="example/gamma",
    )

    repository.save(first)

    repository.save(second)

    repository.save(third)

    assert repository.entries() == (
        first,
        second,
        third,
    )


def test_memory_portfolio_repository_allows_same_native_model_across_providers() -> None:
    repository = InMemoryModelPortfolioRepository()

    first = create_entry(
        provider="provider-a",
        model="frontier",
    )

    second = create_entry(
        provider="provider-b",
        model="frontier",
    )

    repository.save(first)

    repository.save(second)

    assert repository.entries() == (
        first,
        second,
    )


def test_memory_portfolio_repository_rejects_duplicate_identifier() -> None:
    repository = InMemoryModelPortfolioRepository()

    entry = create_entry()

    repository.save(entry)

    with pytest.raises(
        ValueError,
        match=("Model portfolio entry 'openrouter/example/frontier' already exists"),
    ):
        repository.save(entry)


def test_memory_portfolio_repository_rejects_equivalent_duplicate_entry() -> None:
    repository = InMemoryModelPortfolioRepository()

    first = create_entry()

    second = create_entry()

    assert first is not second
    assert first.identifier == second.identifier

    repository.save(first)

    with pytest.raises(
        ValueError,
        match=("Model portfolio entry 'openrouter/example/frontier' already exists"),
    ):
        repository.save(second)


def test_memory_portfolio_repository_starts_empty() -> None:
    repository = InMemoryModelPortfolioRepository()

    assert repository.entries() == ()
