"""Tool command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from uuid import UUID

TOOL_COMMAND = "tool"

TOOL_ACTION_ATTRIBUTE = "tool_action"

TOOL_IMPLEMENTATIONS_ACTION = "implementations"
TOOL_IMPLEMENTATION_SHOW_ACTION = "implementation-show"
TOOL_IMPORT_ACTION = "import"
TOOL_LIST_ACTION = "list"
TOOL_SHOW_ACTION = "show"
TOOL_TEST_CASES_ACTION = "test-cases"
TOOL_TEST_CASE_SHOW_ACTION = "test-case-show"
TOOL_VERSIONS_ACTION = "versions"

TOOL_DOCUMENT_ATTRIBUTE = "tool_document"
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
