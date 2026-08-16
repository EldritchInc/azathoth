"""Tests for immutable tool implementation catalogs."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import (
    ToolImplementation,
    ToolImplementationCatalog,
)

FIRST_IMPLEMENTATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")
THIRD_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")
WORD_COUNT_ID = UUID("44444444-4444-4444-4444-444444444444")
SENTENCE_COUNT_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_implementation(
    *,
    implementation_id: UUID = FIRST_IMPLEMENTATION_ID,
    tool_id: UUID = WORD_COUNT_ID,
    tool_version: str = "1.0.0",
    implementation_version: str = "1.0.0",
    runtime: str = "python",
) -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=implementation_id,
        tool_id=tool_id,
        tool_version=tool_version,
        version=implementation_version,
        runtime=runtime,
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def test_implementation_catalog_defaults_to_empty() -> None:
    catalog = ToolImplementationCatalog()

    assert catalog.implementations == ()
    assert catalog.identifiers == ()


def test_implementation_catalog_records_implementations() -> None:
    implementation = create_implementation()
    catalog = ToolImplementationCatalog(
        implementations=(implementation,),
    )

    assert catalog.implementations == (implementation,)
    assert catalog.identifiers == (FIRST_IMPLEMENTATION_ID,)


def test_implementation_catalog_gets_implementation_by_identifier() -> None:
    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        implementation_version="2.0.0",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
        )
    )

    assert catalog.get(FIRST_IMPLEMENTATION_ID) == first
    assert catalog.get(SECOND_IMPLEMENTATION_ID) == second


def test_implementation_catalog_returns_none_for_unknown_identifier() -> None:
    catalog = ToolImplementationCatalog(
        implementations=(create_implementation(),),
    )

    assert catalog.get(THIRD_IMPLEMENTATION_ID) is None


def test_implementation_catalog_returns_implementations_for_tool() -> None:
    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        implementation_version="2.0.0",
    )
    other = create_implementation(
        implementation_id=THIRD_IMPLEMENTATION_ID,
        tool_id=SENTENCE_COUNT_ID,
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
            other,
        )
    )

    assert catalog.implementations_for(WORD_COUNT_ID) == (
        first,
        second,
    )
    assert catalog.implementations_for(SENTENCE_COUNT_ID) == (other,)


def test_implementation_catalog_returns_implementations_for_tool_version() -> None:
    first = create_implementation(
        tool_version="1.0.0",
    )
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        tool_version="2.0.0",
    )
    third = create_implementation(
        implementation_id=THIRD_IMPLEMENTATION_ID,
        tool_version="2.0.0",
        implementation_version="1.1.0",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
            third,
        )
    )

    assert catalog.implementations_for_version(
        WORD_COUNT_ID,
        "1.0.0",
    ) == (first,)
    assert catalog.implementations_for_version(
        WORD_COUNT_ID,
        "2.0.0",
    ) == (
        second,
        third,
    )


def test_implementation_catalog_returns_empty_for_unknown_tool() -> None:
    catalog = ToolImplementationCatalog(
        implementations=(create_implementation(),),
    )

    assert catalog.implementations_for(SENTENCE_COUNT_ID) == ()
    assert (
        catalog.implementations_for_version(
            SENTENCE_COUNT_ID,
            "1.0.0",
        )
        == ()
    )


def test_implementation_catalog_returns_empty_for_unknown_tool_version() -> None:
    catalog = ToolImplementationCatalog(
        implementations=(create_implementation(),),
    )

    assert (
        catalog.implementations_for_version(
            WORD_COUNT_ID,
            "9.0.0",
        )
        == ()
    )


def test_implementation_catalog_allows_multiple_implementations() -> None:
    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        runtime="javascript",
    )

    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
        )
    )

    assert catalog.implementations_for_version(
        WORD_COUNT_ID,
        "1.0.0",
    ) == (
        first,
        second,
    )


def test_implementation_catalog_rejects_duplicate_identifier() -> None:
    first = create_implementation()
    duplicate = create_implementation(
        implementation_version="2.0.0",
    )

    with pytest.raises(
        ValidationError,
        match="duplicate identifiers",
    ):
        ToolImplementationCatalog(
            implementations=(
                first,
                duplicate,
            )
        )


def test_implementation_catalog_preserves_order() -> None:
    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        implementation_version="2.0.0",
    )
    third = create_implementation(
        implementation_id=THIRD_IMPLEMENTATION_ID,
        implementation_version="3.0.0",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
            third,
        )
    )

    assert catalog.implementations == (
        first,
        second,
        third,
    )
    assert catalog.identifiers == (
        FIRST_IMPLEMENTATION_ID,
        SECOND_IMPLEMENTATION_ID,
        THIRD_IMPLEMENTATION_ID,
    )


def test_implementation_catalog_is_immutable() -> None:
    catalog = ToolImplementationCatalog(
        implementations=(create_implementation(),),
    )

    with pytest.raises(ValidationError):
        catalog.implementations = ()


def test_implementation_catalog_round_trips_through_json() -> None:
    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        implementation_version="2.0.0",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            first,
            second,
        )
    )

    restored = ToolImplementationCatalog.model_validate_json(
        catalog.model_dump_json(),
    )

    assert restored == catalog
