"""Durable tool inspection commands for the Azathoth CLI."""

import json
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolDocument,
    ToolDocumentError,
    ToolImplementation,
    ToolTestCase,
    decode_tool_document,
)


def _tool_document_duplicate_error(
    *,
    repository: SQLiteToolRepository,
    document: ToolDocument,
) -> str | None:
    """Return a duplicate-artifact error before mutating persistence."""

    definition = document.definition

    if (
        repository.get_definition(
            definition.id,
            definition.version,
        )
        is not None
    ):
        return f"Tool definition {definition.id}@{definition.version} already exists."

    existing_implementation_ids = {
        implementation.id for implementation in repository.implementations()
    }

    for implementation in document.implementations:
        if implementation.id in existing_implementation_ids:
            return f"Tool implementation {implementation.id} already exists."

    existing_test_case_ids = {test_case.id for test_case in repository.test_cases()}

    for test_case in document.test_cases:
        if test_case.id in existing_test_case_ids:
            return f"Tool test case {test_case.id} already exists."

    return None


def list_tools() -> int:
    """List all durable tool definition versions."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    for definition in repository.definitions():
        print(f"{definition.id}  {definition.version}  {definition.name}")

    return 0


def show_tool(
    tool_id: UUID,
    *,
    version: str,
) -> int:
    """Show one exact durable tool definition version."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    definition = repository.get_definition(
        tool_id,
        version,
    )

    if definition is None:
        print(
            f"Tool {tool_id}@{version} is not configured.",
            file=sys.stderr,
        )

        return 1

    _print_tool_definition(definition)

    return 0


def list_tool_versions(
    tool_id: UUID,
) -> int:
    """List durable definition versions for one tool identity."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    definitions = tuple(
        definition for definition in repository.definitions() if definition.id == tool_id
    )

    if not definitions:
        print(
            f"Tool {tool_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    for definition in definitions:
        print(definition.version)

    return 0


def list_tool_implementations(
    tool_id: UUID,
    *,
    version: str,
) -> int:
    """List implementations for one exact durable tool definition."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    definition = repository.get_definition(
        tool_id,
        version,
    )

    if definition is None:
        print(
            f"Tool {tool_id}@{version} is not configured.",
            file=sys.stderr,
        )

        return 1

    implementations = tuple(
        implementation
        for implementation in repository.implementations()
        if (implementation.tool_id == tool_id and implementation.tool_version == version)
    )

    for implementation in implementations:
        print(f"{implementation.id}  {implementation.version}  {implementation.runtime}")

    return 0


def show_tool_implementation(
    implementation_id: UUID,
) -> int:
    """Show one durable tool implementation."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    implementation = repository.get_implementation(
        implementation_id,
    )

    if implementation is None:
        print(
            f"Tool implementation {implementation_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    _print_tool_implementation(
        implementation,
    )

    return 0


def list_tool_test_cases(
    tool_id: UUID,
) -> int:
    """List durable verification cases for one tool identity."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    definitions = tuple(
        definition for definition in repository.definitions() if definition.id == tool_id
    )

    if not definitions:
        print(
            f"Tool {tool_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    test_cases = tuple(
        test_case for test_case in repository.test_cases() if test_case.tool_id == tool_id
    )

    for test_case in test_cases:
        print(f"{test_case.id}  {test_case.name}")

    return 0


def show_tool_test_case(
    test_case_id: UUID,
) -> int:
    """Show one durable tool verification case."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    test_case = repository.get_test_case(
        test_case_id,
    )

    if test_case is None:
        print(
            f"Tool test case {test_case_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    _print_tool_test_case(
        test_case,
    )

    return 0


def _print_tool_definition(
    definition: ToolDefinition,
) -> None:
    """Render one exact durable tool capability contract."""

    print(f"ID: {definition.id}")
    print(f"Name: {definition.name}")
    print(f"Version: {definition.version}")
    print(f"Description: {definition.description}")

    print("Input Schema:")
    print(
        json.dumps(
            definition.input_schema.json_schema,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("Output Schema:")
    print(
        json.dumps(
            definition.output_schema.json_schema,
            ensure_ascii=False,
            indent=2,
        )
    )


def _print_tool_implementation(
    implementation: ToolImplementation,
) -> None:
    """Render one durable executable tool implementation."""

    print(f"ID: {implementation.id}")
    print(f"Tool ID: {implementation.tool_id}")
    print(f"Tool Version: {implementation.tool_version}")
    print(f"Implementation Version: {implementation.version}")
    print(f"Runtime: {implementation.runtime}")
    print(f"Entrypoint: {implementation.entrypoint}")
    print("Source:")
    print(implementation.source)


def _print_tool_test_case(
    test_case: ToolTestCase,
) -> None:
    """Render one durable tool verification case."""

    print(f"ID: {test_case.id}")
    print(f"Tool ID: {test_case.tool_id}")
    print(f"Name: {test_case.name}")
    print(f"Description: {test_case.description}")

    print("Inputs:")
    print(
        json.dumps(
            test_case.inputs,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("Expected Output:")
    print(
        json.dumps(
            test_case.expected_output,
            ensure_ascii=False,
            indent=2,
        )
    )


def import_tool(
    document_path: Path,
) -> int:
    """Import one portable durable tool document."""

    try:
        encoded = document_path.read_text(
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Unable to read tool document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    try:
        document = decode_tool_document(
            encoded,
        )
    except ToolDocumentError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    duplicate_error = _tool_document_duplicate_error(
        repository=repository,
        document=document,
    )

    if duplicate_error is not None:
        print(
            duplicate_error,
            file=sys.stderr,
        )

        return 1

    repository.save_definition(
        document.definition,
    )

    for implementation in document.implementations:
        repository.save_implementation(
            implementation,
        )

    for test_case in document.test_cases:
        repository.save_test_case(
            test_case,
        )

    print(f"Imported tool {document.definition.id}@{document.definition.version}.")

    return 0


__all__ = [
    "import_tool",
    "list_tool_implementations",
    "list_tool_test_cases",
    "list_tool_versions",
    "list_tools",
    "show_tool",
    "show_tool_implementation",
    "show_tool_test_case",
]
