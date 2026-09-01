"""Tests for SQLite model portfolio persistence."""

from pathlib import Path

import pytest

from azathoth.providers import (
    ModelPortfolioEntry,
    ModelPortfolioRepository,
    SQLiteModelPortfolioRepository,
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


def create_repository(
    database: Path,
) -> SQLiteModelPortfolioRepository:
    """Create one SQLite model portfolio repository."""

    return SQLiteModelPortfolioRepository(database)


def test_sqlite_portfolio_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: ModelPortfolioRepository = create_repository(tmp_path / "portfolio.db")

    assert repository.entries() == ()


def test_sqlite_portfolio_repository_persists_entry(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

    entry = create_entry()

    repository.save(entry)

    assert repository.get(entry.identifier) == entry


def test_sqlite_portfolio_repository_persists_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "portfolio.db"

    entry = create_entry()

    create_repository(database).save(entry)

    repository = create_repository(database)

    assert repository.get(entry.identifier) == entry


def test_sqlite_portfolio_repository_returns_none_for_unknown_entry(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

    assert repository.get("openrouter/example/missing") is None


def test_sqlite_portfolio_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

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


def test_sqlite_portfolio_repository_preserves_order_across_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "portfolio.db"

    first = create_entry(model="example/alpha")

    second = create_entry(model="example/beta")

    repository = create_repository(database)

    repository.save(first)

    repository.save(second)

    reconstructed = create_repository(database)

    assert reconstructed.entries() == (
        first,
        second,
    )


def test_sqlite_portfolio_repository_allows_same_native_model_across_providers(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

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


def test_sqlite_portfolio_repository_rejects_duplicate_identifier(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

    entry = create_entry()

    repository.save(entry)

    with pytest.raises(
        ValueError,
        match=("Model portfolio entry 'openrouter/example/frontier' already exists"),
    ):
        repository.save(entry)


def test_sqlite_portfolio_repository_rejects_equivalent_duplicate_entry(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "portfolio.db")

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


def test_sqlite_portfolio_repository_deletes_entry(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "portfolio.db",
    )

    entry = create_entry()

    repository.save(entry)
    repository.delete(entry.identifier)

    assert repository.get(entry.identifier) is None
    assert repository.entries() == ()


def test_sqlite_portfolio_repository_delete_persists_across_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "portfolio.db"

    first = create_entry(
        model="example/alpha",
    )
    second = create_entry(
        model="example/beta",
    )

    repository = create_repository(database)

    repository.save(first)
    repository.save(second)
    repository.delete(first.identifier)

    reconstructed = create_repository(database)

    assert reconstructed.entries() == (second,)


def test_sqlite_portfolio_repository_delete_preserves_remaining_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "portfolio.db",
    )

    first = create_entry(
        model="example/alpha",
    )
    second = create_entry(
        model="example/beta",
    )
    third = create_entry(
        model="example/gamma",
    )

    repository.save(first)
    repository.save(second)
    repository.save(third)

    repository.delete(second.identifier)

    assert repository.entries() == (
        first,
        third,
    )


def test_sqlite_portfolio_repository_rejects_deleting_unknown_entry(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "portfolio.db",
    )

    with pytest.raises(
        ValueError,
        match="does not exist",
    ):
        repository.delete(
            "openrouter/example/missing",
        )
