"""Tool command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from uuid import UUID

from azathoth.cli.parsing.common import positive_integer

TOOL_COMMAND = "tool"

TOOL_ACTION_ATTRIBUTE = "tool_action"

TOOL_EXPORT_ACTION = "export"
TOOL_FROM_MCP_ACTION = "from-mcp"
TOOL_HISTORY_ACTION = "history"
TOOL_IMPLEMENTATIONS_ACTION = "implementations"
TOOL_IMPLEMENTATION_SHOW_ACTION = "implementation-show"
TOOL_IMPORT_ACTION = "import"
TOOL_INSTALL_STANDARD_ACTION = "install-standard"
TOOL_LIST_ACTION = "list"
TOOL_SHOW_ACTION = "show"
TOOL_TEST_CASES_ACTION = "test-cases"
TOOL_TEST_CASE_SHOW_ACTION = "test-case-show"
TOOL_USAGE_ACTION = "usage"
TOOL_VERIFY_ACTION = "verify"
TOOL_VERSIONS_ACTION = "versions"

TOOL_DOCUMENT_ATTRIBUTE = "tool_document"
TOOL_MCP_AUTHORIZATION_ATTRIBUTE = "tool_mcp_authorization"
TOOL_MCP_COMMAND_ATTRIBUTE = "tool_mcp_command"
TOOL_MCP_GRANTS_ATTRIBUTE = "tool_mcp_grants"
TOOL_MCP_TIMEOUT_ATTRIBUTE = "tool_mcp_timeout_seconds"
TOOL_MCP_TOOL_ATTRIBUTE = "tool_mcp_tool"
TOOL_MCP_URL_ATTRIBUTE = "tool_mcp_url"
TOOL_HISTORY_LIMIT_ATTRIBUTE = "tool_history_limit"
TOOL_HISTORY_VERSION_ATTRIBUTE = "tool_history_version"
TOOL_REVISION_ATTRIBUTE = "tool_revision"
TOOL_ID_ATTRIBUTE = "tool_id"
TOOL_IMPLEMENTATION_ID_ATTRIBUTE = "tool_implementation_id"
TOOL_TEST_CASE_ID_ATTRIBUTE = "tool_test_case_id"
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

    tool_import_parser = tool_actions.add_parser(
        TOOL_IMPORT_ACTION,
        help="Import one portable durable tool document.",
    )

    tool_import_parser.add_argument(
        TOOL_DOCUMENT_ATTRIBUTE,
        type=Path,
        metavar="FILE",
        help="Portable tool JSON document to import.",
    )

    tool_actions.add_parser(
        TOOL_INSTALL_STANDARD_ACTION,
        help="Install the standard tool library that ships with Azathoth.",
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

    tool_history_parser = tool_actions.add_parser(
        TOOL_HISTORY_ACTION,
        help="List imported revisions of one tool, newest first.",
    )

    tool_history_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID whose imported revisions to list.",
    )

    tool_history_parser.add_argument(
        "--version",
        dest=TOOL_HISTORY_VERSION_ATTRIBUTE,
        default=None,
        metavar="VERSION",
        help="Only list revisions of this exact tool version.",
    )

    tool_history_parser.add_argument(
        "--limit",
        dest=TOOL_HISTORY_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent revisions to list.",
    )

    tool_export_parser = tool_actions.add_parser(
        TOOL_EXPORT_ACTION,
        help="Print one imported tool revision as an importable JSON document.",
    )

    tool_export_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to export.",
    )

    tool_export_parser.add_argument(
        "--version",
        dest=TOOL_VERSION_ATTRIBUTE,
        required=True,
        metavar="VERSION",
        help="Exact tool version to export.",
    )

    tool_export_parser.add_argument(
        "--revision",
        dest=TOOL_REVISION_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="NUMBER",
        help="Imported revision to export. Defaults to the latest.",
    )

    tool_from_mcp_parser = tool_actions.add_parser(
        TOOL_FROM_MCP_ACTION,
        help="Print the tool document of a tool an MCP server serves, pinned to its schemas.",
    )

    tool_from_mcp_parser.add_argument(
        "--tool",
        dest=TOOL_MCP_TOOL_ATTRIBUTE,
        required=True,
        metavar="NAME",
        help="The name the server lists the tool under.",
    )

    tool_from_mcp_parser.add_argument(
        "--url",
        dest=TOOL_MCP_URL_ATTRIBUTE,
        default=None,
        metavar="URL",
        help="The URL of a server reached over streamable HTTP.",
    )

    tool_from_mcp_parser.add_argument(
        "--authorization",
        dest=TOOL_MCP_AUTHORIZATION_ATTRIBUTE,
        default=None,
        metavar="VARIABLE",
        help="The variable holding an HTTP server's bearer token.",
    )

    tool_from_mcp_parser.add_argument(
        "--grant",
        dest=TOOL_MCP_GRANTS_ATTRIBUTE,
        action="append",
        default=[],
        metavar="VARIABLE",
        help="A variable a stdio server is given, or a prefix ending in '*'. Repeatable.",
    )

    tool_from_mcp_parser.add_argument(
        "--timeout-seconds",
        dest=TOOL_MCP_TIMEOUT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="SECONDS",
        help="How long each call may take, and listing the tools now. Listing defaults to 30.",
    )

    tool_from_mcp_parser.add_argument(
        TOOL_MCP_COMMAND_ATTRIBUTE,
        nargs="*",
        metavar="COMMAND",
        help="After --, the command that starts a stdio server.",
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

    tool_implementations_parser = tool_actions.add_parser(
        TOOL_IMPLEMENTATIONS_ACTION,
        help="List implementations for one exact tool definition version.",
    )

    tool_implementations_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to inspect.",
    )

    tool_implementations_parser.add_argument(
        "--version",
        dest=TOOL_VERSION_ATTRIBUTE,
        required=True,
        metavar="VERSION",
        help="Exact durable tool definition version.",
    )

    tool_implementation_show_parser = tool_actions.add_parser(
        TOOL_IMPLEMENTATION_SHOW_ACTION,
        help="Show one durable tool implementation.",
    )

    tool_implementation_show_parser.add_argument(
        TOOL_IMPLEMENTATION_ID_ATTRIBUTE,
        type=UUID,
        metavar="IMPLEMENTATION_ID",
        help="Tool implementation UUID to inspect.",
    )

    tool_test_cases_parser = tool_actions.add_parser(
        TOOL_TEST_CASES_ACTION,
        help="List durable verification cases for one tool identity.",
    )

    tool_test_cases_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to inspect.",
    )

    tool_test_case_show_parser = tool_actions.add_parser(
        TOOL_TEST_CASE_SHOW_ACTION,
        help="Show one durable tool verification case.",
    )

    tool_test_case_show_parser.add_argument(
        TOOL_TEST_CASE_ID_ATTRIBUTE,
        type=UUID,
        metavar="TEST_CASE_ID",
        help="Tool test case UUID to inspect.",
    )

    tool_verify_parser = tool_actions.add_parser(
        TOOL_VERIFY_ACTION,
        help="Verify every implementation for one exact tool definition version.",
    )

    tool_verify_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to verify.",
    )

    tool_verify_parser.add_argument(
        "--version",
        dest=TOOL_VERSION_ATTRIBUTE,
        required=True,
        metavar="VERSION",
        help="Exact durable tool definition version.",
    )

    tool_usage_parser = tool_actions.add_parser(
        TOOL_USAGE_ACTION,
        help="Show where one tool is configured, in production, and executed.",
    )

    tool_usage_parser.add_argument(
        TOOL_ID_ATTRIBUTE,
        type=UUID,
        metavar="TOOL_ID",
        help="Tool capability UUID to trace.",
    )
