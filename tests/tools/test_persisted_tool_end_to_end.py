"""End-to-end tests for persisted tool execution and verification."""

import asyncio
from pathlib import Path
from uuid import UUID

from azathoth.tools import (
    PythonToolExecutor,
    SQLiteToolRepository,
    ToolCatalogLoader,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolResolver,
    ToolTestCase,
    ToolVerifier,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")
IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_definition() -> ToolDefinition:
    """Create a durable word-count capability."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count words in supplied text.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                    },
                },
                "required": [
                    "text",
                ],
            }
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "word_count": {
                        "type": "integer",
                    },
                },
                "required": [
                    "word_count",
                ],
            }
        ),
    )


def create_implementation() -> ToolImplementation:
    """Create persisted Python source for word counting."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
    )


def create_test_cases() -> tuple[ToolTestCase, ...]:
    """Create durable verification cases for word counting."""

    return (
        ToolTestCase(
            id=FIRST_TEST_CASE_ID,
            tool_id=TOOL_ID,
            name="counts two words",
            description="Count a simple two-word sentence.",
            inputs={
                "text": "hello world",
            },
            expected_output={
                "word_count": 2,
            },
        ),
        ToolTestCase(
            id=SECOND_TEST_CASE_ID,
            tool_id=TOOL_ID,
            name="counts five words",
            description="Count a longer sentence.",
            inputs={
                "text": "Azathoth learns from empirical evidence",
            },
            expected_output={
                "word_count": 5,
            },
        ),
    )


def seed_repository(
    database: Path,
) -> None:
    """Persist one complete executable and verifiable tool."""

    repository = SQLiteToolRepository(database)

    repository.save_definition(
        create_definition(),
    )
    repository.save_implementation(
        create_implementation(),
    )

    for test_case in create_test_cases():
        repository.save_test_case(test_case)


def test_persisted_tool_resolves_executes_and_verifies(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tools.db"

    seed_repository(database)

    repository = SQLiteToolRepository(database)
    loader = ToolCatalogLoader(repository)

    tool_catalog = loader.load_catalog()
    implementation_catalog = loader.load_implementation_catalog()

    requirement = ToolRequirement(
        name="word_count",
        version="1.0.0",
        runtime="python",
    )

    definitions = ToolResolver(
        tool_catalog,
    ).resolve(requirement)

    assert len(definitions) == 1

    definition = definitions[0]

    assert definition.id == TOOL_ID
    assert definition.name == "word_count"

    implementations = ToolImplementationResolver(
        implementation_catalog,
    ).resolve_for_requirement(
        definition,
        requirement,
    )

    assert len(implementations) == 1

    implementation = implementations[0]

    assert implementation.id == IMPLEMENTATION_ID
    assert implementation.source == (
        "def run(text):\n    return {'word_count': len(text.split())}\n"
    )

    test_cases = loader.load_test_cases(
        definition.id,
    )

    assert len(test_cases) == 2

    verification = asyncio.run(
        ToolVerifier(
            PythonToolExecutor(),
        ).verify(
            implementation,
            test_cases,
        )
    )

    assert verification.implementation_id == IMPLEMENTATION_ID
    assert verification.passed_count == 2
    assert verification.failed_count == 0

    assert tuple(result.actual_output for result in verification.results) == (
        {
            "word_count": 2,
        },
        {
            "word_count": 5,
        },
    )


def test_persisted_tool_survives_repository_recreation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tools.db"

    seed_repository(database)

    reloaded_repository = SQLiteToolRepository(database)
    loader = ToolCatalogLoader(reloaded_repository)

    definitions = ToolResolver(
        loader.load_catalog(),
    ).resolve(
        ToolRequirement(
            name="word_count",
        )
    )

    assert len(definitions) == 1

    definition = definitions[0]

    implementations = ToolImplementationResolver(
        loader.load_implementation_catalog(),
    ).resolve(
        definition,
    )

    assert len(implementations) == 1

    output = asyncio.run(
        PythonToolExecutor().execute(
            implementations[0],
            {
                "text": "one two three four",
            },
        )
    )

    assert output == {
        "word_count": 4,
    }


def test_persisted_tool_source_is_not_application_code(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tools.db"

    seed_repository(database)

    repository = SQLiteToolRepository(database)

    implementation = repository.get_implementation(
        IMPLEMENTATION_ID,
    )

    assert implementation is not None
    assert implementation.runtime == "python"
    assert implementation.entrypoint == "run"
    assert "def run(text):" in implementation.source
    assert "word_count" in implementation.source
