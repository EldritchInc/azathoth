"""Durable tool inspection commands for the Azathoth CLI."""

import json
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolDocumentError,
    ToolDocumentRevision,
    ToolImplementation,
    ToolTestCase,
    decode_tool_document,
    earliest_identical_tool_revision,
    encode_tool_document,
    supported_tool_runtimes,
    unsupported_runtime_message,
)


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


def list_tool_history(
    tool_id: UUID,
    *,
    version: str | None = None,
    limit: int | None = None,
) -> int:
    """List the imported revisions of one tool, newest first.

    Each line contains the tool version, revision number, import time, the
    first twelve characters of the content digest, and the document's
    implementation and test case counts. A revision with the same content as
    an earlier revision of its version names the earliest such revision.
    Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    history = SQLiteToolRepository(
        configuration.database,
    ).document_revisions(tool_id)

    selected = tuple(
        revision for revision in history if version is None or revision.tool_version == version
    )

    if not selected:
        reference = f"{tool_id}@{version}" if version is not None else str(tool_id)

        print(
            f"Tool {reference} is not configured.",
            file=sys.stderr,
        )

        return 1

    newest_first = tuple(reversed(selected))

    if limit is not None:
        newest_first = newest_first[:limit]

    for revision in newest_first:
        identical = earliest_identical_tool_revision(
            history,
            revision,
        )

        note = f"  identical to revision {identical.number}" if identical is not None else ""

        print(
            f"{revision.tool_version}  {revision.number}  {_render_imported_at(revision)}  "
            f"{revision.content_digest[:12]}  "
            f"{len(revision.document.implementations)} implementations  "
            f"{len(revision.document.test_cases)} test cases{note}"
        )

    return 0


def export_tool(
    tool_id: UUID,
    *,
    version: str,
    revision: int | None = None,
) -> int:
    """Print one imported tool revision as an importable JSON document.

    The latest revision of the exact version is exported unless another is
    named. Importing the output again appends a revision with identical
    content. Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    latest = repository.latest_document_revision(
        tool_id,
        version,
    )

    if latest is None:
        print(
            f"Tool {tool_id}@{version} is not configured.",
            file=sys.stderr,
        )

        return 1

    selected = (
        latest
        if revision is None
        else repository.document_revision(
            tool_id,
            version,
            revision,
        )
    )

    if selected is None:
        print(
            f"Tool {tool_id}@{version} has no revision {revision}.",
            file=sys.stderr,
        )

        return 1

    print(encode_tool_document(selected.document))

    return 0


def _render_imported_at(
    revision: ToolDocumentRevision,
) -> str:
    """Render when one revision was imported, or that it is unknown."""

    if revision.imported_at is None:
        return "unknown"

    return revision.imported_at.isoformat()


def import_tool(
    document_path: Path,
) -> int:
    """Import one portable durable tool document.

    Importing never replaces history: each import appends the next revision
    of the document's exact tool version and makes its artifacts current.
    Re-importing earlier content is reported as identical to the earliest
    revision with the same content. A document whose artifact IDs belong to
    another tool, whose implementation IDs belong to another version, or
    whose implementations use a runtime Azathoth cannot execute, is rejected
    before anything is saved.
    """

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

    runtimes = supported_tool_runtimes()

    for implementation in document.implementations:
        if implementation.runtime not in runtimes:
            print(
                unsupported_runtime_message(implementation),
                file=sys.stderr,
            )

            return 1

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    try:
        revision = repository.save_document(document)
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    identical = earliest_identical_tool_revision(
        repository.document_revisions(revision.tool_id),
        revision,
    )

    note = f" (identical to revision {identical.number})" if identical is not None else ""

    print(f"Imported tool {revision.reference} revision {revision.number}{note}.")

    return 0


__all__ = [
    "export_tool",
    "import_tool",
    "list_tool_history",
    "list_tool_implementations",
    "list_tool_test_cases",
    "list_tool_versions",
    "list_tools",
    "show_tool",
    "show_tool_implementation",
    "show_tool_test_case",
]
