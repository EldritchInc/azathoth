"""Tests for immutable tool catalogs."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_input_schema() -> ToolInputSchema:
    """Create a deterministic tool input schema."""

    return ToolInputSchema(
        json_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                },
            },
            "required": ["text"],
        },
    )


def create_output_schema() -> ToolOutputSchema:
    """Create a deterministic tool output schema."""

    return ToolOutputSchema(
        json_schema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                },
            },
            "required": ["count"],
        },
    )


def create_tool_definition(
    *,
    tool_id: UUID = TOOL_ID,
    name: str = "word_count",
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"Tool definition for {name}.",
        version=version,
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )


def test_tool_catalog_defaults_to_empty() -> None:
    catalog = ToolCatalog()

    assert catalog.definitions == ()
    assert catalog.references == ()


def test_tool_catalog_records_definitions() -> None:
    definition = create_tool_definition()
    catalog = ToolCatalog(definitions=(definition,))

    assert catalog.definitions == (definition,)
    assert catalog.references == ((TOOL_ID, "1.0.0"),)


def test_tool_catalog_gets_exact_definition() -> None:
    first = create_tool_definition(version="1.0.0")
    second = create_tool_definition(version="2.0.0")
    catalog = ToolCatalog(definitions=(first, second))

    assert catalog.get(TOOL_ID, "1.0.0") == first
    assert catalog.get(TOOL_ID, "2.0.0") == second


def test_tool_catalog_returns_none_for_unknown_definition() -> None:
    definition = create_tool_definition()
    catalog = ToolCatalog(definitions=(definition,))

    assert catalog.get(SECOND_TOOL_ID, "1.0.0") is None
    assert catalog.get(TOOL_ID, "2.0.0") is None


def test_tool_catalog_allows_multiple_versions_of_same_tool() -> None:
    first = create_tool_definition(version="1.0.0")
    second = create_tool_definition(version="2.0.0")

    catalog = ToolCatalog(definitions=(first, second))

    assert catalog.definitions_for(TOOL_ID) == (first, second)
    assert catalog.versions_for(TOOL_ID) == ("1.0.0", "2.0.0")


def test_tool_catalog_rejects_duplicate_tool_reference() -> None:
    definition = create_tool_definition()
    duplicate = create_tool_definition()

    with pytest.raises(
        ValidationError,
        match="duplicate tool references",
    ):
        ToolCatalog(definitions=(definition, duplicate))


def test_tool_catalog_allows_same_version_for_different_tools() -> None:
    first = create_tool_definition(
        tool_id=TOOL_ID,
        name="word_count",
    )
    second = create_tool_definition(
        tool_id=SECOND_TOOL_ID,
        name="sentence_count",
    )

    catalog = ToolCatalog(definitions=(first, second))

    assert catalog.get(TOOL_ID, "1.0.0") == first
    assert catalog.get(SECOND_TOOL_ID, "1.0.0") == second


def test_tool_catalog_finds_definitions_by_name() -> None:
    first = create_tool_definition(version="1.0.0")
    second = create_tool_definition(version="2.0.0")
    other = create_tool_definition(
        tool_id=SECOND_TOOL_ID,
        name="sentence_count",
    )
    catalog = ToolCatalog(
        definitions=(
            first,
            second,
            other,
        )
    )

    assert catalog.definitions_named("word_count") == (first, second)
    assert catalog.definitions_named("sentence_count") == (other,)


def test_tool_catalog_returns_empty_results_for_unknown_tool() -> None:
    catalog = ToolCatalog(definitions=(create_tool_definition(),))

    assert catalog.definitions_for(SECOND_TOOL_ID) == ()
    assert catalog.versions_for(SECOND_TOOL_ID) == ()
    assert catalog.definitions_named("unknown") == ()


def test_tool_catalog_preserves_definition_order() -> None:
    first = create_tool_definition(
        tool_id=TOOL_ID,
        name="word_count",
    )
    second = create_tool_definition(
        tool_id=SECOND_TOOL_ID,
        name="sentence_count",
    )
    catalog = ToolCatalog(definitions=(first, second))

    assert catalog.definitions == (first, second)
    assert catalog.references == (
        (TOOL_ID, "1.0.0"),
        (SECOND_TOOL_ID, "1.0.0"),
    )


def test_tool_catalog_is_immutable() -> None:
    catalog = ToolCatalog(definitions=(create_tool_definition(),))

    with pytest.raises(ValidationError):
        catalog.definitions = ()


def test_tool_catalog_round_trips_through_json() -> None:
    first = create_tool_definition(version="1.0.0")
    second = create_tool_definition(version="2.0.0")
    catalog = ToolCatalog(definitions=(first, second))

    restored = ToolCatalog.model_validate_json(catalog.model_dump_json())

    assert restored == catalog
