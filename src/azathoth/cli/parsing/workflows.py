"""Workflow command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from uuid import UUID

from azathoth.cli.parsing.common import json_value

WORKFLOW_COMMAND = "workflow"

WORKFLOW_ACTION_ATTRIBUTE = "workflow_action"

WORKFLOW_IMPORT_ACTION = "import"
WORKFLOW_INVOKE_ACTION = "invoke"
WORKFLOW_LIST_ACTION = "list"
WORKFLOW_OPTIMIZE_ACTION = "optimize"
WORKFLOW_PROMOTE_ACTION = "promote"
WORKFLOW_RUN_ACTION = "run"
WORKFLOW_SHOW_ACTION = "show"

WORKFLOW_DOCUMENT_ATTRIBUTE = "workflow_document"
WORKFLOW_ID_ATTRIBUTE = "workflow_id"
WORKFLOW_INPUT_ATTRIBUTE = "workflow_input"

EXPECTED_VALUE_ATTRIBUTE = "expected_value"
TARGET_LATENCY_ATTRIBUTE = "target_latency_seconds"
TARGET_COST_ATTRIBUTE = "target_cost_usd"
GENERATIONS_ATTRIBUTE = "generations"


def add_workflow_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add workflow commands to the Azathoth parser."""

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

    workflow_show_parser = workflow_actions.add_parser(
        WORKFLOW_SHOW_ACTION,
        help="Show one configured workflow.",
    )

    workflow_show_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to inspect.",
    )

    workflow_import_parser = workflow_actions.add_parser(
        WORKFLOW_IMPORT_ACTION,
        help="Import a workflow JSON document.",
    )

    workflow_import_parser.add_argument(
        WORKFLOW_DOCUMENT_ATTRIBUTE,
        type=Path,
        metavar="FILE",
        help="JSON workflow document to import.",
    )

    workflow_run_parser = workflow_actions.add_parser(
        WORKFLOW_RUN_ACTION,
        help="Execute one configured workflow.",
    )

    workflow_run_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to execute.",
    )

    workflow_invoke_parser = workflow_actions.add_parser(
        WORKFLOW_INVOKE_ACTION,
        help="Invoke one active production workflow.",
    )

    workflow_invoke_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Production workflow UUID to invoke.",
    )

    workflow_invoke_parser.add_argument(
        "--input",
        dest=WORKFLOW_INPUT_ATTRIBUTE,
        required=True,
        type=json_value,
        metavar="JSON",
        help="Production workflow input as JSON.",
    )

    workflow_optimize_parser = workflow_actions.add_parser(
        WORKFLOW_OPTIMIZE_ACTION,
        help="Empirically optimize one configured workflow.",
    )

    workflow_optimize_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to optimize.",
    )

    workflow_optimize_parser.add_argument(
        "--expected",
        dest=EXPECTED_VALUE_ATTRIBUTE,
        required=True,
        type=json_value,
        metavar="JSON",
        help="Expected workflow output as JSON.",
    )

    workflow_optimize_parser.add_argument(
        "--target-latency",
        dest=TARGET_LATENCY_ATTRIBUTE,
        required=True,
        type=float,
        metavar="SECONDS",
        help="Target workflow latency in seconds.",
    )

    workflow_optimize_parser.add_argument(
        "--target-cost",
        dest=TARGET_COST_ATTRIBUTE,
        required=True,
        type=float,
        metavar="USD",
        help="Target workflow execution cost in USD.",
    )

    workflow_optimize_parser.add_argument(
        "--generations",
        dest=GENERATIONS_ATTRIBUTE,
        type=int,
        default=1,
        metavar="COUNT",
        help="Number of empirical optimization generations.",
    )

    workflow_promote_parser = workflow_actions.add_parser(
        WORKFLOW_PROMOTE_ACTION,
        help="Promote one configured workflow to active production.",
    )

    workflow_promote_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to promote.",
    )
