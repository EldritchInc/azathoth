"""Tool command-line parser construction."""

from __future__ import annotations

from argparse import (
    ArgumentParser,
    _SubParsersAction,
)
from uuid import UUID

TOOL_COMMAND = "tool"

TOOL_ACTION_ATTRIBUTE = "tool_action"

TOOL_LIST_ACTION = "list"
TOOL_SHOW_ACTION = "show"
TOOL_VERSIONS_ACTION = "versions"

TOOL_ID_ATTRIBUTE = "tool_id"
TOOL_VERSION_ATTRIBUTE = "tool_version"


def add_tool_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add tool commands to the Azathoth parser."""

    tool_parser = commands.add_parser(
        TOOL_COMMAND,
        help="Inspect and operate durable tools.",
    )

    tool_actions = tool_parser.add_subparsers(
        dest=TOOL_ACTION_ATTRIBUTE,
    )

    tool_actions.add_parser(
        TOOL_LIST_ACTION,
        help="List durable tool definition versions.",
    )

    tool_show_parser = tool_actions.add_parser(
        TOOL_SHOW_ACTION,
        help="Show one exact durable tool definition version.",
    )

    tool_show_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to inspect.",
    )

    tool_show_parser.add_argument(
        "--version",
        dest=TOOL_VERSION_ATTRIBUTE,
        required=True,
        metavar="VERSION",
        help="Exact durable tool definition version.",
    )

    tool_versions_parser = tool_actions.add_parser(
        TOOL_VERSIONS_ACTION,
        help="List durable versions for one tool identity.",
    )

    tool_versions_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to inspect.",
    )
