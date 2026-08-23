"""Command-line application for Azathoth."""

from argparse import (
    ArgumentParser,
    Namespace,
)
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

from azathoth import __version__
from azathoth.cli.workflows import (
    import_workflow,
    list_workflows,
    run_workflow,
    show_workflow,
)

COMMAND_ATTRIBUTE = "command"
WORKFLOW_COMMAND = "workflow"

WORKFLOW_ACTION_ATTRIBUTE = "workflow_action"
WORKFLOW_IMPORT_ACTION = "import"
WORKFLOW_LIST_ACTION = "list"
WORKFLOW_RUN_ACTION = "run"
WORKFLOW_SHOW_ACTION = "show"

WORKFLOW_DOCUMENT_ATTRIBUTE = "workflow_document"
WORKFLOW_ID_ATTRIBUTE = "workflow_id"


def build_parser() -> ArgumentParser:
    """Build the Azathoth command-line parser."""

    parser = ArgumentParser(
        prog="azathoth",
        description=("Empirical optimization for context-aware AI workflows."),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(
        dest=COMMAND_ATTRIBUTE,
    )

    workflow_parser = commands.add_parser(
        WORKFLOW_COMMAND,
        help="Inspect and operate configured workflows.",
    )

    workflow_actions = workflow_parser.add_subparsers(
        dest=WORKFLOW_ACTION_ATTRIBUTE,
    )

    workflow_actions.add_parser(
        WORKFLOW_LIST_ACTION,
        help="List configured workflows.",
    )

    show_parser = workflow_actions.add_parser(
        WORKFLOW_SHOW_ACTION,
        help="Show one configured workflow.",
    )

    show_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to inspect.",
    )

    import_parser = workflow_actions.add_parser(
        WORKFLOW_IMPORT_ACTION,
        help="Import a workflow JSON document.",
    )

    import_parser.add_argument(
        WORKFLOW_DOCUMENT_ATTRIBUTE,
        type=Path,
        metavar="FILE",
        help="JSON workflow document to import.",
    )

    run_parser = workflow_actions.add_parser(
        WORKFLOW_RUN_ACTION,
        help="Execute one configured workflow.",
    )

    run_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to execute.",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the Azathoth command-line application."""

    parser = build_parser()

    arguments = parser.parse_args(argv)

    result = _dispatch(arguments)

    if result is not None:
        return result

    parser.print_help()

    return 0


def _dispatch(
    arguments: Namespace,
) -> int | None:
    """Dispatch parsed CLI arguments to a command handler."""

    command = cast(
        str | None,
        getattr(
            arguments,
            COMMAND_ATTRIBUTE,
            None,
        ),
    )

    if command != WORKFLOW_COMMAND:
        return None

    action = cast(
        str | None,
        getattr(
            arguments,
            WORKFLOW_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == WORKFLOW_LIST_ACTION:
        return list_workflows()

    if action == WORKFLOW_SHOW_ACTION:
        workflow_id = cast(
            UUID,
            getattr(
                arguments,
                WORKFLOW_ID_ATTRIBUTE,
            ),
        )

        return show_workflow(workflow_id)

    if action == WORKFLOW_IMPORT_ACTION:
        workflow_document = cast(
            Path,
            getattr(
                arguments,
                WORKFLOW_DOCUMENT_ATTRIBUTE,
            ),
        )

        return import_workflow(workflow_document)

    if action == WORKFLOW_RUN_ACTION:
        workflow_id = cast(
            UUID,
            getattr(
                arguments,
                WORKFLOW_ID_ATTRIBUTE,
            ),
        )

        return run_workflow(workflow_id)

    return None
