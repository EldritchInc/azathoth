"""Tests for deterministic tool verification through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    verify_tool,
)
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolTestCase,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")

SECOND_TEST_CASE_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_definition() -> ToolDefinition:
    """Create one deterministic tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count whitespace-delimited words.",
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
                    "count": {
                        "type": "integer",
                    },
                },
                "required": [
                    "count",
                ],
            }
        ),
    )


def create_implementation(
    *,
    implementation_id: UUID = FIRST_IMPLEMENTATION_ID,
    runtime: str = "python",
    source: str | None = None,
) -> ToolImplementation:
    """Create one deterministic tool implementation."""

    if source is None:
        source = "def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"

    return ToolImplementation(
        id=implementation_id,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime=runtime,
        entrypoint="run",
        source=source,
    )


def create_test_case(
    *,
    test_case_id: UUID = FIRST_TEST_CASE_ID,
    text: str = "hello world",
    expected_count: int = 2,
) -> ToolTestCase:
    """Create one deterministic verification case."""

    return ToolTestCase(
        id=test_case_id,
        tool_id=TOOL_ID,
        name="word count",
        description="Verify deterministic word counting.",
        inputs={
            "text": text,
        },
        expected_output={
            "count": expected_count,
        },
    )


def configure_repository(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    definition: ToolDefinition | None = None,
    implementations: tuple[ToolImplementation, ...] = (),
    test_cases: tuple[ToolTestCase, ...] = (),
) -> None:
    """Persist verification artifacts and configure the CLI."""

    repository = SQLiteToolRepository(
        database,
    )

    if definition is not None:
        repository.save_definition(
            definition,
        )

    for implementation in implementations:
        repository.save_implementation(
            implementation,
        )

    for test_case in test_cases:
        repository.save_test_case(
            test_case,
        )

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_tool_verify_passes_complete_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
        implementations=(create_implementation(),),
        test_cases=(
            create_test_case(),
            create_test_case(
                test_case_id=SECOND_TEST_CASE_ID,
                text="one two three",
                expected_count=3,
            ),
        ),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"Implementation ID: {FIRST_IMPLEMENTATION_ID}" in captured.out
    assert "Implementation Version: 1.0.0" in captured.out
    assert "Runtime: python" in captured.out
    assert "Status: passed" in captured.out
    assert "Tests: 2" in captured.out
    assert "Passed: 2" in captured.out
    assert "Failed: 0" in captured.out
    assert "Pass Rate: 1.000000" in captured.out

    assert f"  Test Case ID: {FIRST_TEST_CASE_ID}" in captured.out
    assert f"  Test Case ID: {SECOND_TEST_CASE_ID}" in captured.out


def test_tool_verify_returns_failure_for_failed_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
        implementations=(create_implementation(),),
        test_cases=(
            create_test_case(
                expected_count=3,
            ),
        ),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == ""

    assert "Status: failed" in captured.out
    assert "Tests: 1" in captured.out
    assert "Passed: 0" in captured.out
    assert "Failed: 1" in captured.out
    assert "Pass Rate: 0.000000" in captured.out

    assert "  Expected: {'count': 3}" in captured.out
    assert "  Actual: {'count': 2}" in captured.out


def test_tool_verify_verifies_every_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    first = create_implementation(
        implementation_id=FIRST_IMPLEMENTATION_ID,
    )

    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
        implementations=(
            first,
            second,
        ),
        test_cases=(create_test_case(),),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0

    assert f"Implementation ID: {FIRST_IMPLEMENTATION_ID}" in captured.out

    assert f"Implementation ID: {SECOND_IMPLEMENTATION_ID}" in captured.out

    assert captured.out.splitlines().count("Status: passed") == 2


def test_tool_verify_continues_after_unsupported_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    unsupported = create_implementation(
        implementation_id=FIRST_IMPLEMENTATION_ID,
        runtime="javascript",
    )

    supported = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
        implementations=(
            unsupported,
            supported,
        ),
        test_cases=(create_test_case(),),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == ""

    assert f"Implementation ID: {FIRST_IMPLEMENTATION_ID}" in captured.out

    assert "Runtime: javascript" in captured.out
    assert "Status: error" in captured.out

    assert "PythonToolExecutor only supports the 'python' runtime." in captured.out

    assert f"Implementation ID: {SECOND_IMPLEMENTATION_ID}" in captured.out

    assert "Runtime: python" in captured.out
    assert "Status: passed" in captured.out


def test_tool_verify_rejects_unknown_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool {TOOL_ID}@1.0.0 is not configured.\n")


def test_tool_verify_rejects_definition_without_implementations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool {TOOL_ID}@1.0.0 has no implementations.\n")


def test_tool_verify_rejects_tool_without_test_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definition=create_definition(),
        implementations=(create_implementation(),),
    )

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool {TOOL_ID} has no test cases.\n")
