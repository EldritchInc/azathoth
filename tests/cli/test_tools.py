"""Tests for durable tool inspection commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_tool_implementations,
    list_tool_test_cases,
    list_tool_versions,
    list_tools,
    show_tool,
    show_tool_implementation,
    show_tool_test_case,
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

SECOND_TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")

THIRD_IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")

FIRST_TEST_CASE_ID = UUID("66666666-6666-6666-6666-666666666666")

SECOND_TEST_CASE_ID = UUID("77777777-7777-7777-7777-777777777777")

THIRD_TEST_CASE_ID = UUID("88888888-8888-8888-8888-888888888888")


def create_definition(
    *,
    tool_id: UUID = TOOL_ID,
    name: str = "word_count",
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create one durable tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"{name} capability.",
        version=version,
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


def create_test_case(
    *,
    test_case_id: UUID = FIRST_TEST_CASE_ID,
    tool_id: UUID = TOOL_ID,
    name: str = "counts two words",
    text: str = "hello world",
    expected_count: int = 2,
) -> ToolTestCase:
    """Create one durable tool verification case."""

    return ToolTestCase(
        id=test_case_id,
        tool_id=tool_id,
        name=name,
        description=f"Verify {name}.",
        inputs={
            "text": text,
        },
        expected_output={
            "count": expected_count,
        },
    )


def create_implementation(
    *,
    implementation_id: UUID = FIRST_IMPLEMENTATION_ID,
    tool_id: UUID = TOOL_ID,
    tool_version: str = "1.0.0",
    implementation_version: str = "1.0.0",
    runtime: str = "python",
    entrypoint: str = "run",
) -> ToolImplementation:
    """Create one durable tool implementation."""

    return ToolImplementation(
        id=implementation_id,
        tool_id=tool_id,
        tool_version=tool_version,
        version=implementation_version,
        runtime=runtime,
        entrypoint=entrypoint,
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def configure_repository(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    definitions: tuple[ToolDefinition, ...] = (),
    implementations: tuple[ToolImplementation, ...] = (),
    test_cases: tuple[ToolTestCase, ...] = (),
) -> None:
    """Persist tool artifacts and configure the CLI database."""

    repository = SQLiteToolRepository(database)

    for definition in definitions:
        repository.save_definition(definition)

    for implementation in implementations:
        repository.save_implementation(implementation)

    for test_case in test_cases:
        repository.save_test_case(test_case)

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_tool_list_prints_all_definition_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="2.0.0",
            ),
            create_definition(
                tool_id=SECOND_TOOL_ID,
                name="sentence_count",
            ),
        ),
    )

    result = list_tools()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{TOOL_ID}  1.0.0  word_count\n"
        f"{TOOL_ID}  2.0.0  word_count\n"
        f"{SECOND_TOOL_ID}  1.0.0  sentence_count\n"
    )

    assert captured.err == ""


def test_tool_list_prints_nothing_when_repository_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(),
    )

    assert list_tools() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_tool_show_prints_exact_definition_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    first = create_definition(
        version="1.0.0",
    )

    second = create_definition(
        version="2.0.0",
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            first,
            second,
        ),
    )

    result = show_tool(
        TOOL_ID,
        version="2.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {TOOL_ID}\n" in captured.out
    assert "Name: word_count\n" in captured.out
    assert "Version: 2.0.0\n" in captured.out
    assert "Description: word_count capability.\n" in captured.out

    assert "Input Schema:\n" in captured.out
    assert '"text": {' in captured.out

    assert "Output Schema:\n" in captured.out
    assert '"count": {' in captured.out


def test_tool_show_rejects_unknown_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(create_definition(),),
    )

    result = show_tool(
        TOOL_ID,
        version="9.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID}@9.0.0 is not configured.\n")


def test_tool_versions_lists_versions_in_durable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(
                version="2.0.0",
            ),
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="3.0.0",
            ),
            create_definition(
                tool_id=SECOND_TOOL_ID,
                name="sentence_count",
            ),
        ),
    )

    result = list_tool_versions(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ("2.0.0\n1.0.0\n3.0.0\n")
    assert captured.err == ""


def test_tool_versions_rejects_unknown_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(),
    )

    result = list_tool_versions(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID} is not configured.\n")


def test_tool_implementations_lists_exact_definition_implementations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    first = create_implementation(
        implementation_id=FIRST_IMPLEMENTATION_ID,
        tool_version="1.0.0",
        implementation_version="1.0.0",
        runtime="python",
    )

    second = create_implementation(
        implementation_id=SECOND_IMPLEMENTATION_ID,
        tool_version="1.0.0",
        implementation_version="1.1.0",
        runtime="javascript",
    )

    other_version = create_implementation(
        implementation_id=THIRD_IMPLEMENTATION_ID,
        tool_version="2.0.0",
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="2.0.0",
            ),
        ),
        implementations=(
            first,
            second,
            other_version,
        ),
    )

    result = list_tool_implementations(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{FIRST_IMPLEMENTATION_ID}  1.0.0  python\n{SECOND_IMPLEMENTATION_ID}  1.1.0  javascript\n"
    )

    assert captured.err == ""


def test_tool_implementations_allows_definition_without_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(create_definition(),),
    )

    result = list_tool_implementations(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_tool_implementations_rejects_unknown_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = list_tool_implementations(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID}@1.0.0 is not configured.\n")


def test_tool_implementation_show_prints_executable_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    implementation = create_implementation(
        implementation_version="1.2.3",
        runtime="python",
        entrypoint="run",
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        implementations=(implementation,),
    )

    result = show_tool_implementation(
        implementation.id,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {implementation.id}\n" in captured.out
    assert f"Tool ID: {TOOL_ID}\n" in captured.out
    assert "Tool Version: 1.0.0\n" in captured.out
    assert "Implementation Version: 1.2.3\n" in captured.out
    assert "Runtime: python\n" in captured.out
    assert "Entrypoint: run\n" in captured.out
    assert "Source:\n" in captured.out
    assert "def run(text: str)" in captured.out


def test_tool_implementation_show_rejects_unknown_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = show_tool_implementation(
        FIRST_IMPLEMENTATION_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool implementation {FIRST_IMPLEMENTATION_ID} is not configured.\n")


def test_tool_test_cases_lists_cases_for_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    first = create_test_case(
        test_case_id=FIRST_TEST_CASE_ID,
        name="counts two words",
    )

    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
        name="counts empty input",
        text="",
        expected_count=0,
    )

    other = create_test_case(
        test_case_id=THIRD_TEST_CASE_ID,
        tool_id=SECOND_TOOL_ID,
        name="counts sentences",
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(),
            create_definition(
                tool_id=SECOND_TOOL_ID,
                name="sentence_count",
            ),
        ),
        test_cases=(
            first,
            second,
            other,
        ),
    )

    result = list_tool_test_cases(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{FIRST_TEST_CASE_ID}  counts two words\n{SECOND_TEST_CASE_ID}  counts empty input\n"
    )

    assert captured.err == ""


def test_tool_test_cases_allows_tool_without_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(create_definition(),),
    )

    result = list_tool_test_cases(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_tool_test_cases_rejects_unknown_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = list_tool_test_cases(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID} is not configured.\n")


def test_tool_test_case_show_prints_verification_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    test_case = create_test_case()

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        test_cases=(test_case,),
    )

    result = show_tool_test_case(
        test_case.id,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {FIRST_TEST_CASE_ID}\n" in captured.out
    assert f"Tool ID: {TOOL_ID}\n" in captured.out
    assert "Name: counts two words\n" in captured.out
    assert "Description: Verify counts two words.\n" in captured.out

    assert "Inputs:\n" in captured.out
    assert '"text": "hello world"' in captured.out

    assert "Expected Output:\n" in captured.out
    assert '"count": 2' in captured.out


def test_tool_test_case_show_rejects_unknown_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = show_tool_test_case(
        FIRST_TEST_CASE_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool test case {FIRST_TEST_CASE_ID} is not configured.\n")
