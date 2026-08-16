"""End-to-end tests for deterministic tool requirement resolution."""

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
                "value": {},
            },
            "required": ["value"],
        },
    )


def create_definition(
    *,
    tool_id: UUID,
    name: str,
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"Deterministic {name} capability.",
        version=version,
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )


def create_catalog() -> ToolCatalog:
    """Create a deterministic multi-capability tool catalog."""

    return ToolCatalog(
        definitions=(
            create_definition(
                tool_id=WORD_COUNT_ID,
                name="word_count",
                version="1.0.0",
            ),
            create_definition(
                tool_id=WORD_COUNT_ID,
                name="word_count",
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


def test_requirement_resolves_capability_from_catalog() -> None:
    catalog = create_catalog()
    resolver = ToolResolver(catalog)

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
        )
    )

    assert tuple(
        (definition.id, definition.name, definition.version) for definition in matches
    ) == (
        (
            WORD_COUNT_ID,
            "word_count",
            "1.0.0",
        ),
        (
            WORD_COUNT_ID,
            "word_count",
            "2.0.0",
        ),
    )


def test_version_requirement_resolves_exact_capability_version() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
            version="2.0.0",
        )
    )

    assert len(matches) == 1

    definition = matches[0]

    assert definition.id == WORD_COUNT_ID
    assert definition.name == "word_count"
    assert definition.version == "2.0.0"


def test_multiple_requirements_resolve_in_declaration_order() -> None:
    resolver = ToolResolver(create_catalog())
    requirements = ToolRequirements(
        requirements=(
            ToolRequirement(
                name="translation",
            ),
            ToolRequirement(
                name="word_count",
                version="1.0.0",
            ),
            ToolRequirement(
                name="sentence_count",
            ),
        )
    )

    matches = resolver.resolve_all(requirements)

    assert len(matches) == 3

    assert tuple(definition.name for definition in matches[0]) == ("translation",)
    assert tuple(definition.version for definition in matches[1]) == ("1.0.0",)
    assert tuple(definition.name for definition in matches[2]) == ("sentence_count",)


def test_unavailable_requirement_resolves_to_empty_matches() -> None:
    resolver = ToolResolver(create_catalog())

    matches = resolver.resolve(
        ToolRequirement(
            name="summarization",
        )
    )

    assert matches == ()


def test_catalog_round_trip_preserves_resolution() -> None:
    catalog = create_catalog()

    restored_catalog = ToolCatalog.model_validate_json(
        catalog.model_dump_json(),
    )

    resolver = ToolResolver(restored_catalog)

    matches = resolver.resolve(
        ToolRequirement(
            name="word_count",
            version="2.0.0",
        )
    )

    assert restored_catalog == catalog
    assert len(matches) == 1
    assert matches[0].id == WORD_COUNT_ID
    assert matches[0].version == "2.0.0"


def test_requirement_round_trip_preserves_resolution() -> None:
    requirement = ToolRequirement(
        name="word_count",
        version="1.0.0",
    )

    restored_requirement = ToolRequirement.model_validate_json(
        requirement.model_dump_json(),
    )

    resolver = ToolResolver(create_catalog())
    matches = resolver.resolve(restored_requirement)

    assert restored_requirement == requirement
    assert len(matches) == 1
    assert matches[0].id == WORD_COUNT_ID
    assert matches[0].version == "1.0.0"


def test_requirements_round_trip_preserves_resolution_order() -> None:
    requirements = ToolRequirements(
        requirements=(
            ToolRequirement(
                name="translation",
            ),
            ToolRequirement(
                name="sentence_count",
            ),
            ToolRequirement(
                name="word_count",
                version="2.0.0",
            ),
        )
    )

    restored_requirements = ToolRequirements.model_validate_json(
        requirements.model_dump_json(),
    )

    resolver = ToolResolver(create_catalog())
    matches = resolver.resolve_all(restored_requirements)

    assert restored_requirements == requirements
    assert tuple(definition.name for definition in matches[0]) == ("translation",)
    assert tuple(definition.name for definition in matches[1]) == ("sentence_count",)
    assert tuple(definition.version for definition in matches[2]) == ("2.0.0",)


def test_complete_requirement_resolution_lifecycle_round_trips() -> None:
    catalog = create_catalog()
    requirements = ToolRequirements(
        requirements=(
            ToolRequirement(
                name="word_count",
                version="2.0.0",
            ),
            ToolRequirement(
                name="translation",
            ),
            ToolRequirement(
                name="unknown",
            ),
        )
    )

    restored_catalog = ToolCatalog.model_validate_json(
        catalog.model_dump_json(),
    )
    restored_requirements = ToolRequirements.model_validate_json(
        requirements.model_dump_json(),
    )

    resolver = ToolResolver(restored_catalog)
    matches = resolver.resolve_all(restored_requirements)

    assert restored_catalog == catalog
    assert restored_requirements == requirements

    assert len(matches) == 3

    assert tuple((definition.name, definition.version) for definition in matches[0]) == (
        (
            "word_count",
            "2.0.0",
        ),
    )
    assert tuple((definition.name, definition.version) for definition in matches[1]) == (
        (
            "translation",
            "1.0.0",
        ),
    )
    assert matches[2] == ()
