"""Tests for deterministic tool implementation resolution."""

from uuid import UUID

from azathoth.tools import (
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
)

WORD_COUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
SENTENCE_COUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")
THIRD_IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")
FOURTH_IMPLEMENTATION_ID = UUID("66666666-6666-6666-6666-666666666666")


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


def create_catalog() -> ToolImplementationCatalog:
    """Create a deterministic implementation catalog."""

    return ToolImplementationCatalog(
        implementations=(
            create_implementation(
                implementation_id=FIRST_IMPLEMENTATION_ID,
                tool_version="1.0.0",
                runtime="python",
            ),
            create_implementation(
                implementation_id=SECOND_IMPLEMENTATION_ID,
                tool_version="1.0.0",
                implementation_version="1.1.0",
                runtime="javascript",
            ),
            create_implementation(
                implementation_id=THIRD_IMPLEMENTATION_ID,
                tool_version="2.0.0",
                runtime="python",
            ),
            create_implementation(
                implementation_id=FOURTH_IMPLEMENTATION_ID,
                tool_id=SENTENCE_COUNT_ID,
                tool_version="1.0.0",
                runtime="python",
            ),
        )
    )


def test_implementation_resolver_resolves_exact_definition() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        version="1.0.0",
    )

    implementations = resolver.resolve(definition)

    assert tuple(implementation.id for implementation in implementations) == (
        FIRST_IMPLEMENTATION_ID,
        SECOND_IMPLEMENTATION_ID,
    )


def test_implementation_resolver_resolves_definition_version() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        version="2.0.0",
    )

    implementations = resolver.resolve(definition)

    assert len(implementations) == 1
    assert implementations[0].id == THIRD_IMPLEMENTATION_ID
    assert implementations[0].tool_version == "2.0.0"


def test_implementation_resolver_does_not_cross_tool_identity() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        tool_id=SENTENCE_COUNT_ID,
        name="sentence_count",
        version="1.0.0",
    )

    implementations = resolver.resolve(definition)

    assert len(implementations) == 1
    assert implementations[0].id == FOURTH_IMPLEMENTATION_ID
    assert implementations[0].tool_id == SENTENCE_COUNT_ID


def test_implementation_resolver_returns_empty_for_unknown_version() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        version="9.0.0",
    )

    implementations = resolver.resolve(definition)

    assert implementations == ()


def test_implementation_resolver_returns_empty_for_unknown_tool() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        tool_id=UUID("77777777-7777-7777-7777-777777777777"),
        name="translation",
    )

    implementations = resolver.resolve(definition)

    assert implementations == ()


def test_implementation_resolver_preserves_catalog_order() -> None:
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        implementation_version="2.0.0",
    )
    first = create_implementation(
        implementation_id=FIRST_IMPLEMENTATION_ID,
        implementation_version="1.0.0",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            second,
            first,
        )
    )
    resolver = ToolImplementationResolver(catalog)

    implementations = resolver.resolve(
        create_definition(),
    )

    assert implementations == (
        second,
        first,
    )


def test_implementation_resolver_resolves_multiple_definitions() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definitions = (
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
    )

    implementations = resolver.resolve_all(definitions)

    assert len(implementations) == 3

    assert tuple(implementation.id for implementation in implementations[0]) == (
        FIRST_IMPLEMENTATION_ID,
        SECOND_IMPLEMENTATION_ID,
    )
    assert tuple(implementation.id for implementation in implementations[1]) == (
        THIRD_IMPLEMENTATION_ID,
    )
    assert tuple(implementation.id for implementation in implementations[2]) == (
        FOURTH_IMPLEMENTATION_ID,
    )


def test_implementation_resolver_preserves_definition_order() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definitions = (
        create_definition(
            tool_id=SENTENCE_COUNT_ID,
            name="sentence_count",
        ),
        create_definition(
            version="2.0.0",
        ),
        create_definition(
            version="1.0.0",
        ),
    )

    implementations = resolver.resolve_all(definitions)

    assert tuple(implementation.id for implementation in implementations[0]) == (
        FOURTH_IMPLEMENTATION_ID,
    )
    assert tuple(implementation.id for implementation in implementations[1]) == (
        THIRD_IMPLEMENTATION_ID,
    )
    assert tuple(implementation.id for implementation in implementations[2]) == (
        FIRST_IMPLEMENTATION_ID,
        SECOND_IMPLEMENTATION_ID,
    )


def test_implementation_resolver_handles_empty_definitions() -> None:
    resolver = ToolImplementationResolver(create_catalog())

    implementations = resolver.resolve_all(())

    assert implementations == ()
