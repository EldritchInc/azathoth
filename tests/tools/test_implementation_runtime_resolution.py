"""Tests for runtime-aware tool implementation resolution."""

from uuid import UUID

from azathoth.tools import (
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)

WORD_COUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")
THIRD_IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_definition(
    *,
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=WORD_COUNT_ID,
        name="word_count",
        description="Count words in text.",
        version=version,
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
            },
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
            },
        ),
    )


def create_implementation(
    *,
    implementation_id: UUID,
    runtime: str,
    tool_version: str = "1.0.0",
) -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=implementation_id,
        tool_id=WORD_COUNT_ID,
        tool_version=tool_version,
        version="1.0.0",
        runtime=runtime,
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_catalog() -> ToolImplementationCatalog:
    """Create a deterministic multi-runtime implementation catalog."""

    return ToolImplementationCatalog(
        implementations=(
            create_implementation(
                implementation_id=FIRST_IMPLEMENTATION_ID,
                runtime="python",
            ),
            create_implementation(
                implementation_id=SECOND_IMPLEMENTATION_ID,
                runtime="javascript",
            ),
            create_implementation(
                implementation_id=THIRD_IMPLEMENTATION_ID,
                runtime="python",
                tool_version="2.0.0",
            ),
        )
    )


def test_runtime_requirement_resolves_matching_implementation() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition()
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert tuple(implementation.id for implementation in implementations) == (
        FIRST_IMPLEMENTATION_ID,
    )


def test_runtime_requirement_rejects_other_runtime() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition()
    requirement = ToolRequirement(
        name="word_count",
        runtime="javascript",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert tuple(implementation.id for implementation in implementations) == (
        SECOND_IMPLEMENTATION_ID,
    )


def test_unknown_runtime_returns_no_implementations() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition()
    requirement = ToolRequirement(
        name="word_count",
        runtime="wasm",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert implementations == ()


def test_requirement_without_runtime_preserves_all_implementations() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition()
    requirement = ToolRequirement(
        name="word_count",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert tuple(implementation.id for implementation in implementations) == (
        FIRST_IMPLEMENTATION_ID,
        SECOND_IMPLEMENTATION_ID,
    )


def test_runtime_resolution_preserves_catalog_order() -> None:
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        runtime="python",
    )
    first = create_implementation(
        implementation_id=FIRST_IMPLEMENTATION_ID,
        runtime="python",
    )
    catalog = ToolImplementationCatalog(
        implementations=(
            second,
            first,
        )
    )
    resolver = ToolImplementationResolver(catalog)
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    implementations = resolver.resolve_for_requirement(
        create_definition(),
        requirement,
    )

    assert implementations == (
        second,
        first,
    )


def test_runtime_requirement_remains_scoped_to_definition_version() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition(
        version="2.0.0",
    )
    requirement = ToolRequirement(
        name="word_count",
        version="2.0.0",
        runtime="python",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert tuple(implementation.id for implementation in implementations) == (
        THIRD_IMPLEMENTATION_ID,
    )


def test_runtime_resolution_does_not_cross_definition_version() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    definition = create_definition()
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    implementations = resolver.resolve_for_requirement(
        definition,
        requirement,
    )

    assert THIRD_IMPLEMENTATION_ID not in tuple(
        implementation.id for implementation in implementations
    )


def test_runtime_requirement_filters_multiple_definitions() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )
    definitions = (
        create_definition(
            version="1.0.0",
        ),
        create_definition(
            version="2.0.0",
        ),
    )

    implementations = resolver.resolve_all_for_requirement(
        definitions,
        requirement,
    )

    assert tuple(implementation.id for implementation in implementations[0]) == (
        FIRST_IMPLEMENTATION_ID,
    )
    assert tuple(implementation.id for implementation in implementations[1]) == (
        THIRD_IMPLEMENTATION_ID,
    )


def test_runtime_requirement_handles_empty_definitions() -> None:
    resolver = ToolImplementationResolver(create_catalog())
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    implementations = resolver.resolve_all_for_requirement(
        (),
        requirement,
    )

    assert implementations == ()
