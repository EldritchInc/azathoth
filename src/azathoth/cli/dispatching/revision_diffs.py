"""Dispatch for `workflow diff`, `tool diff` and `benchmark diff` (ADR 0133)."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.output_format import DiffOutputFormat
from azathoth.cli.parsing import (
    BENCHMARK_ACTION_ATTRIBUTE,
    BENCHMARK_COMMAND,
    BENCHMARK_ID_ATTRIBUTE,
    COMMAND_ATTRIBUTE,
    DIFF_ACTION,
    DIFF_AFTER_ATTRIBUTE,
    DIFF_BEFORE_ATTRIBUTE,
    DIFF_OUTPUT_ATTRIBUTE,
    TOOL_ACTION_ATTRIBUTE,
    TOOL_COMMAND,
    TOOL_ID_ATTRIBUTE,
    TOOL_VERSION_ATTRIBUTE,
    WORKFLOW_ACTION_ATTRIBUTE,
    WORKFLOW_COMMAND,
    WORKFLOW_ID_ATTRIBUTE,
)

DiffHandler = Callable[..., int]

_ACTION_ATTRIBUTES = {
    WORKFLOW_COMMAND: WORKFLOW_ACTION_ATTRIBUTE,
    TOOL_COMMAND: TOOL_ACTION_ATTRIBUTE,
    BENCHMARK_COMMAND: BENCHMARK_ACTION_ATTRIBUTE,
}


def dispatch_diff_command(
    arguments: Namespace,
    *,
    diff_workflow: DiffHandler,
    diff_tool: DiffHandler,
    diff_benchmark: DiffHandler,
) -> int | None:
    """Dispatch one parsed `diff` command, or return `None` when it is another command."""

    command = cast(str | None, getattr(arguments, COMMAND_ATTRIBUTE, None))
    attribute = _ACTION_ATTRIBUTES.get(command or "")

    if attribute is None or getattr(arguments, attribute, None) != DIFF_ACTION:
        return None

    before = cast(int, getattr(arguments, DIFF_BEFORE_ATTRIBUTE))
    after = cast(int, getattr(arguments, DIFF_AFTER_ATTRIBUTE))
    output = DiffOutputFormat(cast(str, getattr(arguments, DIFF_OUTPUT_ATTRIBUTE)))

    if command == WORKFLOW_COMMAND:
        return diff_workflow(
            cast(UUID, getattr(arguments, WORKFLOW_ID_ATTRIBUTE)), before, after, output=output
        )

    if command == TOOL_COMMAND:
        return diff_tool(
            cast(UUID, getattr(arguments, TOOL_ID_ATTRIBUTE)),
            before,
            after,
            version=cast(str, getattr(arguments, TOOL_VERSION_ATTRIBUTE)),
            output=output,
        )

    return diff_benchmark(
        cast(UUID, getattr(arguments, BENCHMARK_ID_ATTRIBUTE)), before, after, output=output
    )


__all__ = [
    "DiffHandler",
    "dispatch_diff_command",
]
