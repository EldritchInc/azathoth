"""Tests for SQLite-backed durable tool persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRepository,
    ToolTestCase,
    require_tool_repository,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")
IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_CASE_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_TEST_CASE_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_definition(
    *,
    tool_id: UUID = TOOL_ID,
    name: str = "word_count",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
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


def create_implementation(
    *,
    implementation_id: UUID = IMPLEMENTATION_ID,
    tool_id: UUID = TOOL_ID,
) -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=implementation_id,
        tool_id=tool_id,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
    )


def create_test_case(
    *,
    test_case_id: UUID = TEST_CASE_ID,
    tool_id: UUID = TOOL_ID,
) -> ToolTestCase:
    """Create a deterministic tool test case."""

    return ToolTestCase(
        id=test_case_id,
        tool_id=tool_id,
        name="counts two words",
        description="Verify that two words are counted.",
        inputs={
            "text": "hello world",
        },
        expected_output={
            "word_count": 2,
        },
    )


def create_repository(
    tmp_path: Path,
) -> SQLiteToolRepository:
    """Create a repository backed by a temporary SQLite database."""

    return SQLiteToolRepository(
        tmp_path / "tools.db",
    )


def test_sqlite_repository_satisfies_repository_protocol(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    resolved: ToolRepository = require_tool_repository(repository)

    assert resolved is repository


def test_sqlite_repository_starts_empty(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    assert repository.definitions() == ()
    assert repository.implementations() == ()
    assert repository.test_cases() == ()


def test_sqlite_repository_creates_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tools.db"

    SQLiteToolRepository(database)

    assert database.exists()


def test_sqlite_repository_round_trips_definition(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    definition = create_definition()

    repository.save_definition(definition)

    restored = repository.get_definition(definition.id)

    assert restored == definition


def test_sqlite_repository_returns_none_for_unknown_definition(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    assert repository.get_definition(TOOL_ID) is None


def test_sqlite_repository_preserves_definition_insertion_order(
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

    assert repository.definitions() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_duplicate_definition(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    definition = create_definition()

    repository.save_definition(definition)

    with pytest.raises(
        ValueError,
        match="Tool definition .* already exists",
    ):
        repository.save_definition(definition)


def test_sqlite_repository_round_trips_implementation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    implementation = create_implementation()

    repository.save_implementation(implementation)

    restored = repository.get_implementation(
        implementation.id,
    )

    assert restored == implementation


def test_sqlite_repository_returns_none_for_unknown_implementation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    assert repository.get_implementation(IMPLEMENTATION_ID) is None


def test_sqlite_repository_preserves_implementation_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_implementation()
    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
    )

    repository.save_implementation(first)
    repository.save_implementation(second)

    assert repository.implementations() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_duplicate_implementation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    implementation = create_implementation()

    repository.save_implementation(implementation)

    with pytest.raises(
        ValueError,
        match="Tool implementation .* already exists",
    ):
        repository.save_implementation(implementation)


def test_sqlite_repository_round_trips_test_case(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    test_case = create_test_case()

    repository.save_test_case(test_case)

    restored = repository.get_test_case(test_case.id)

    assert restored == test_case


def test_sqlite_repository_returns_none_for_unknown_test_case(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    assert repository.get_test_case(TEST_CASE_ID) is None


def test_sqlite_repository_preserves_test_case_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_test_case()
    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
    )

    repository.save_test_case(first)
    repository.save_test_case(second)

    assert repository.test_cases() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_duplicate_test_case(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    test_case = create_test_case()

    repository.save_test_case(test_case)

    with pytest.raises(
        ValueError,
        match="Tool test case .* already exists",
    ):
        repository.save_test_case(test_case)


def test_sqlite_repository_persists_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tools.db"

    first_repository = SQLiteToolRepository(database)

    definition = create_definition()
    implementation = create_implementation()
    test_case = create_test_case()

    first_repository.save_definition(definition)
    first_repository.save_implementation(implementation)
    first_repository.save_test_case(test_case)

    second_repository = SQLiteToolRepository(database)

    assert second_repository.definitions() == (definition,)
    assert second_repository.implementations() == (implementation,)
    assert second_repository.test_cases() == (test_case,)


def test_sqlite_repository_preserves_artifact_json_fidelity(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    definition = create_definition()
    implementation = create_implementation()
    test_case = create_test_case()

    repository.save_definition(definition)
    repository.save_implementation(implementation)
    repository.save_test_case(test_case)

    restored_definition = repository.get_definition(definition.id)
    restored_implementation = repository.get_implementation(
        implementation.id,
    )
    restored_test_case = repository.get_test_case(test_case.id)

    assert restored_definition is not None
    assert restored_implementation is not None
    assert restored_test_case is not None

    assert restored_definition.model_dump_json() == (definition.model_dump_json())
    assert restored_implementation.model_dump_json() == (implementation.model_dump_json())
    assert restored_test_case.model_dump_json() == (test_case.model_dump_json())


def test_sqlite_repository_keeps_artifact_types_independent(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    definition = create_definition()
    implementation = create_implementation()
    test_case = create_test_case()

    repository.save_definition(definition)
    repository.save_implementation(implementation)
    repository.save_test_case(test_case)

    assert repository.definitions() == (definition,)
    assert repository.implementations() == (implementation,)
    assert repository.test_cases() == (test_case,)
