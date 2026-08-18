"""Tests for repository-backed tool catalog loading."""

from pathlib import Path

from azathoth.tools import (
    SQLiteToolRepository,
    ToolCatalogLoader,
)

from .test_sqlite_repository import (
    SECOND_TEST_CASE_ID,
    SECOND_TOOL_ID,
    TOOL_ID,
    create_definition,
    create_implementation,
    create_test_case,
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


def test_loads_persisted_test_cases(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_test_case()
    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
        tool_id=SECOND_TOOL_ID,
    )

    repository.save_test_case(first)
    repository.save_test_case(second)

    loader = ToolCatalogLoader(repository)

    assert loader.load_test_cases() == (
        first,
        second,
    )


def test_loads_test_cases_for_one_tool(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_test_case()
    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
        tool_id=SECOND_TOOL_ID,
    )

    repository.save_test_case(first)
    repository.save_test_case(second)

    loader = ToolCatalogLoader(repository)

    assert loader.load_test_cases(TOOL_ID) == (first,)
