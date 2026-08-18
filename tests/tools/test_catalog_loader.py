"""Tests for repository-backed tool catalog loading."""

from pathlib import Path

from azathoth.tools import (
    SQLiteToolRepository,
    ToolCatalogLoader,
)

from .test_sqlite_repository import (
    SECOND_TOOL_ID,
    create_definition,
    create_implementation,
)


def create_repository(
    tmp_path: Path,
) -> SQLiteToolRepository:
    return SQLiteToolRepository(
        tmp_path / "tools.db",
    )


def test_loads_tool_catalog(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    definition = create_definition()

    repository.save_definition(definition)

    loader = ToolCatalogLoader(repository)

    catalog = loader.load_catalog()

    assert catalog.definitions == (definition,)


def test_loads_implementation_catalog(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    implementation = create_implementation()

    repository.save_implementation(
        implementation,
    )

    loader = ToolCatalogLoader(repository)

    catalog = loader.load_implementation_catalog()

    assert catalog.implementations == (implementation,)


def test_loader_preserves_catalog_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_definition()

    second = create_definition(
        tool_id=SECOND_TOOL_ID,
        name="character_count",
    )

    repository.save_definition(first)
    repository.save_definition(second)

    loader = ToolCatalogLoader(repository)

    catalog = loader.load_catalog()

    assert catalog.definitions == (
        first,
        second,
    )


def test_loader_returns_empty_catalogs(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    loader = ToolCatalogLoader(repository)

    assert loader.load_catalog().definitions == ()
    assert loader.load_implementation_catalog().implementations == ()
