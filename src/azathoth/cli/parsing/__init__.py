"""Command-line parser construction for Azathoth."""

from argparse import ArgumentParser

from azathoth import __version__
from azathoth.cli.parsing.common import COMMAND_ATTRIBUTE
from azathoth.cli.parsing.models import (
    MODEL_ACTION_ATTRIBUTE,
    MODEL_AUTHORIZE_ACTION,
    MODEL_COMMAND,
    MODEL_DEAUTHORIZE_ACTION,
    MODEL_IDENTIFIER_ATTRIBUTE,
    MODEL_LIST_ACTION,
    MODEL_PORTFOLIO_ACTION,
    MODEL_SHOW_ACTION,
    add_model_parser,
)
from azathoth.cli.parsing.tools import (
    TOOL_ACTION_ATTRIBUTE,
    TOOL_COMMAND,
    TOOL_DOCUMENT_ATTRIBUTE,
    TOOL_ID_ATTRIBUTE,
    TOOL_IMPLEMENTATION_ID_ATTRIBUTE,
    TOOL_IMPLEMENTATION_SHOW_ACTION,
    TOOL_IMPLEMENTATIONS_ACTION,
    TOOL_IMPORT_ACTION,
    TOOL_LIST_ACTION,
    TOOL_SHOW_ACTION,
    TOOL_TEST_CASE_ID_ATTRIBUTE,
    TOOL_TEST_CASE_SHOW_ACTION,
    TOOL_TEST_CASES_ACTION,
    TOOL_VERIFY_ACTION,
    TOOL_VERSION_ATTRIBUTE,
    TOOL_VERSIONS_ACTION,
    add_tool_parser,
)
from azathoth.cli.parsing.workflows import (
    EXPECTED_VALUE_ATTRIBUTE,
    GENERATIONS_ATTRIBUTE,
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ACTION_ATTRIBUTE,
    WORKFLOW_COMMAND,
    WORKFLOW_DOCUMENT_ATTRIBUTE,
    WORKFLOW_ID_ATTRIBUTE,
    WORKFLOW_IMPORT_ACTION,
    WORKFLOW_INPUT_ATTRIBUTE,
    WORKFLOW_INVOKE_ACTION,
    WORKFLOW_LIST_ACTION,
    WORKFLOW_OPTIMIZE_ACTION,
    WORKFLOW_PROMOTE_ACTION,
    WORKFLOW_RUN_ACTION,
    WORKFLOW_SHOW_ACTION,
    add_workflow_parser,
)


def build_parser() -> ArgumentParser:
    """Build the Azathoth command-line parser."""

    parser = ArgumentParser(
        prog="azathoth",
        description="Empirical optimization for context-aware AI workflows.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(
        dest=COMMAND_ATTRIBUTE,
    )

    add_workflow_parser(commands)

    add_model_parser(commands)

    add_tool_parser(commands)

    return parser


__all__ = [
    "COMMAND_ATTRIBUTE",
    "EXPECTED_VALUE_ATTRIBUTE",
    "GENERATIONS_ATTRIBUTE",
    "MODEL_ACTION_ATTRIBUTE",
    "MODEL_AUTHORIZE_ACTION",
    "MODEL_COMMAND",
    "MODEL_DEAUTHORIZE_ACTION",
    "MODEL_IDENTIFIER_ATTRIBUTE",
    "MODEL_LIST_ACTION",
    "MODEL_PORTFOLIO_ACTION",
    "MODEL_SHOW_ACTION",
    "TARGET_COST_ATTRIBUTE",
    "TARGET_LATENCY_ATTRIBUTE",
    "TOOL_ACTION_ATTRIBUTE",
    "TOOL_COMMAND",
    "TOOL_DOCUMENT_ATTRIBUTE",
    "TOOL_ID_ATTRIBUTE",
    "TOOL_IMPLEMENTATION_ID_ATTRIBUTE",
    "TOOL_IMPLEMENTATIONS_ACTION",
    "TOOL_IMPLEMENTATION_SHOW_ACTION",
    "TOOL_IMPORT_ACTION",
    "TOOL_LIST_ACTION",
    "TOOL_SHOW_ACTION",
    "TOOL_TEST_CASES_ACTION",
    "TOOL_TEST_CASE_ID_ATTRIBUTE",
    "TOOL_TEST_CASE_SHOW_ACTION",
    "TOOL_VERIFY_ACTION",
    "TOOL_VERSION_ATTRIBUTE",
    "TOOL_VERSIONS_ACTION",
    "WORKFLOW_ACTION_ATTRIBUTE",
    "WORKFLOW_COMMAND",
    "WORKFLOW_DOCUMENT_ATTRIBUTE",
    "WORKFLOW_ID_ATTRIBUTE",
    "WORKFLOW_IMPORT_ACTION",
    "WORKFLOW_INPUT_ATTRIBUTE",
    "WORKFLOW_INVOKE_ACTION",
    "WORKFLOW_LIST_ACTION",
    "WORKFLOW_OPTIMIZE_ACTION",
    "WORKFLOW_PROMOTE_ACTION",
    "WORKFLOW_RUN_ACTION",
    "WORKFLOW_SHOW_ACTION",
    "build_parser",
]
