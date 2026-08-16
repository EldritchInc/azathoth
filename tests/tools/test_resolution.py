"""Tests for deterministic tool requirement resolution."""

from uuid import UUID

from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolRequirements,
    ToolResolver,
)

WORD_COUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
SENTENCE_COUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
TRANSLATION_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_input_schema() -> ToolInputSchema:
    """Create a deterministic input schema."""

    return ToolInputSchema(
        json_schema={
            "type": "object",
        },
    )


def create_output_schema() -> ToolOutputSchema:
    """Create a deterministic output schema."""

    return ToolOutputSchema(
        json_schema={
            "type": "object",
        },
    )


def create_definition(
    *,
    tool_id: UUID = WORD_COUNT_ID,
    name: str = "word_count",
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"{name} tool.",
        version=version,
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )


def create_catalog() -> ToolCatalog:
    """Create a deterministic tool catalog."""

    return ToolCatalog(
        definitions=(
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="2.0.0",
            ),
            create_definition(
                tool_id=SENTENCE_COUNT_ID,
                name="sentence_count",
            ),
            create_definition(
                tool_id=TRANSLATION_ID,
                name="translation",
            ),
        )
    )


def test_tool_resolver_resolves_requirement_by_name() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
        )
    )

    assert len(matches) == 2
    assert tuple(definition.version for definition in matches) == (
        "1.0.0",
        "2.0.0",
    )


def test_tool_resolver_resolves_requirement_by_name_and_version() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
            version="2.0.0",
        )
    )

    assert len(matches) == 1
    assert matches[0].id == WORD_COUNT_ID
    assert matches[0].name == "word_count"
    assert matches[0].version == "2.0.0"


def test_tool_resolver_returns_empty_for_unknown_requirement() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="unknown",
        )
    )

    assert matches == ()


def test_tool_resolver_returns_empty_for_unknown_version() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
            version="9.0.0",
        )
    )

    assert matches == ()


def test_tool_resolver_preserves_catalog_order() -> None:
    catalog = ToolCatalog(
        definitions=(
            create_definition(
                version="3.0.0",
            ),
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="2.0.0",
            ),
        )
    )
    resolver = ToolResolver(catalog)

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
        )
    )

    assert tuple(definition.version for definition in matches) == (
        "3.0.0",
        "1.0.0",
        "2.0.0",
    )


def test_tool_resolver_resolves_multiple_requirements() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve_all(
        ToolRequirements(
            requirements=(
                ToolRequirement(
                    name="word_count",
                ),
                ToolRequirement(
                    name="sentence_count",
                ),
                ToolRequirement(
                    name="translation",
                ),
            ),
        )
    )

    assert len(matches) == 3

    assert tuple(definition.version for definition in matches[0]) == (
        "1.0.0",
        "2.0.0",
    )
    assert tuple(definition.name for definition in matches[1]) == ("sentence_count",)
    assert tuple(definition.name for definition in matches[2]) == ("translation",)


def test_tool_resolver_preserves_requirement_order() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve_all(
        ToolRequirements(
            requirements=(
                ToolRequirement(
                    name="translation",
                ),
                ToolRequirement(
                    name="word_count",
                    version="2.0.0",
                ),
                ToolRequirement(
                    name="sentence_count",
                ),
            ),
        )
    )

    assert tuple(definition.name for definition in matches[0]) == ("translation",)
    assert tuple(definition.version for definition in matches[1]) == ("2.0.0",)
    assert tuple(definition.name for definition in matches[2]) == ("sentence_count",)


def test_tool_resolver_handles_empty_requirements() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve_all(
        ToolRequirements(),
    )

    assert matches == ()
