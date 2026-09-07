"""Durable tool inspection commands for the Azathoth CLI."""

import json
import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
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


__all__ = [
    "list_tool_versions",
    "list_tools",
    "show_tool",
]
