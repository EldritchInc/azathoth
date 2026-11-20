"""Resource usage discovery commands for the Azathoth CLI.

`model usage` and `tool usage` read through the service API (ADR 0133),
so the command line and every other caller say the same of where a model
or a tool is used. Each prints as it always has.
"""

import sys
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_model_usage_report,
    render_tool_usage_report,
)
from azathoth.cli.service import service_instance


def model_usage(
    identifier: str,
) -> int:
    """Show where one exact model is configured, active, and executed.

    Model identity belongs to providers rather than durable configuration, so a
    model no longer offered by any provider can still be inspected. An unused
    model reports zero workflows rather than failing.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        usage = service_instance(configuration).models.usage(identifier)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(render_model_usage_report(usage))

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

    try:
        usage = service_instance(configuration).tools.usage(tool_id)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(render_tool_usage_report(usage))

    return 0
