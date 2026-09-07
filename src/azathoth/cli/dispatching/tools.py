"""Tool command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    TOOL_ACTION_ATTRIBUTE,
    TOOL_ID_ATTRIBUTE,
    TOOL_LIST_ACTION,
    TOOL_SHOW_ACTION,
    TOOL_VERSION_ATTRIBUTE,
    TOOL_VERSIONS_ACTION,
)

ToolListHandler = Callable[[], int]
ToolShowHandler = Callable[..., int]
ToolVersionsHandler = Callable[[UUID], int]


def dispatch_tool_command(
    arguments: Namespace,
    *,
    list_tools: ToolListHandler,
    list_tool_versions: ToolVersionsHandler,
    show_tool: ToolShowHandler,
) -> int | None:
    """Dispatch one parsed tool command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            TOOL_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == TOOL_LIST_ACTION:
        return list_tools()

    if action == TOOL_SHOW_ACTION:
        return show_tool(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            ),
            version=cast(
                str,
                getattr(
                    arguments,
                    TOOL_VERSION_ATTRIBUTE,
                ),
            ),
        )

    if action == TOOL_VERSIONS_ACTION:
        return list_tool_versions(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            )
        )

    return None
