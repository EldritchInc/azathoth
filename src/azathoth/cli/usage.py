"""Resource usage discovery commands for the Azathoth CLI."""

import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_model_usage_report,
    render_tool_usage_report,
)
from azathoth.tools import SQLiteToolRepository
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunRepository,
    model_usage_report,
    tool_usage_report,
)


def model_usage(
    identifier: str,
) -> int:
    """Show where one exact model is configured, active, and executed.

    Model identity belongs to providers rather than durable configuration, so a
    model no longer offered by any provider can still be inspected. An unused
    model reports zero workflows rather than failing.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    report = model_usage_report(
        identifier,
        specifications=SQLiteWorkflowRepository(
            configuration.database,
        ).specifications(),
        production_states=SQLiteWorkflowProductionStateRepository(
            configuration.database,
        ).states(),
        runs=SQLiteWorkflowRunRepository(
            configuration.database,
        ).runs(),
    )

    print(render_model_usage_report(report))

    return 0


def tool_usage(
    tool_id: UUID,
) -> int:
    """Show where one durable tool identity is configured, active, and executed.

    A tool identity is known when any definition version exists or when run
    history recorded its execution. Unknown identities fail so mistyped
    identifiers are not mistaken for unused tools.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    report = tool_usage_report(
        tool_id,
        definitions=SQLiteToolRepository(
            configuration.database,
        ).definitions(),
        specifications=SQLiteWorkflowRepository(
            configuration.database,
        ).specifications(),
        production_states=SQLiteWorkflowProductionStateRepository(
            configuration.database,
        ).states(),
        runs=SQLiteWorkflowRunRepository(
            configuration.database,
        ).runs(),
    )

    if not report.tool_names and not report.used:
        print(
            f"Tool {tool_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    print(render_tool_usage_report(report))

    return 0
