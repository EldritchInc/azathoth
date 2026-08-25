"""Tests for reconstructing model portfolios from repositories."""

from pathlib import Path

from azathoth.providers import (
    InMemoryModelPortfolioRepository,
    ModelPortfolioEntry,
    ModelPortfolioLoader,
    SQLiteModelPortfolioRepository,
)


def create_entry(
    *,
    provider: str = "openrouter",
    model: str = "example/frontier",
) -> ModelPortfolioEntry:
    """Create one deterministic model portfolio entry."""

    return ModelPortfolioEntry(
        provider=provider,
        model=model,
    )


def test_portfolio_loader_reconstructs_empty_portfolio() -> None:
    repository = InMemoryModelPortfolioRepository()

    portfolio = ModelPortfolioLoader(repository).load_portfolio()

    assert portfolio.entries == ()
    assert portfolio.identifiers == ()


def test_portfolio_loader_reconstructs_repository_entries() -> None:
    repository = InMemoryModelPortfolioRepository()

    first = create_entry(model="example/alpha")

    second = create_entry(model="example/beta")

    repository.save(first)

    repository.save(second)

    portfolio = ModelPortfolioLoader(repository).load_portfolio()

    assert portfolio.entries == (
        first,
        second,
    )

    assert portfolio.identifiers == (
        "openrouter/example/alpha",
        "openrouter/example/beta",
    )


def test_portfolio_loader_preserves_repository_order() -> None:
    repository = InMemoryModelPortfolioRepository()

    entries = (
        create_entry(
            provider="provider-a",
            model="gamma",
        ),
        create_entry(
            provider="provider-b",
            model="alpha",
        ),
        create_entry(
            provider="provider-a",
            model="beta",
        ),
    )

    for entry in entries:
        repository.save(entry)

    portfolio = ModelPortfolioLoader(repository).load_portfolio()

    assert portfolio.entries == entries


def test_portfolio_loader_reconstructs_sqlite_portfolio_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "portfolio.db"

    first = create_entry(model="example/alpha")

    second = create_entry(
        provider="other",
        model="example/beta",
    )

    repository = SQLiteModelPortfolioRepository(database)

    repository.save(first)

    repository.save(second)

    reconstructed_repository = SQLiteModelPortfolioRepository(database)

    portfolio = ModelPortfolioLoader(reconstructed_repository).load_portfolio()

    assert portfolio.entries == (
        first,
        second,
    )


def test_portfolio_loader_returns_new_immutable_view_each_time() -> None:
    repository = InMemoryModelPortfolioRepository()

    entry = create_entry()

    repository.save(entry)

    loader = ModelPortfolioLoader(repository)

    first = loader.load_portfolio()
    second = loader.load_portfolio()

    assert first == second
    assert first is not second

    assert first.entries == (entry,)
