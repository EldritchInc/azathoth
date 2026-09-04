"""Command-line application for Azathoth."""

import json
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
    Namespace,
)
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth import __version__
from azathoth.cli.models import (
    authorize_model,
    deauthorize_model,
    list_models,
    list_portfolio_models,
    show_model,
)
from azathoth.cli.workflows import (
    import_workflow,
    invoke_workflow,
    list_workflows,
    optimize_workflow,
    promote_workflow,
    run_workflow,
    show_workflow,
)

COMMAND_ATTRIBUTE = "command"

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

MODEL_COMMAND = "model"
MODEL_ACTION_ATTRIBUTE = "model_action"
MODEL_AUTHORIZE_ACTION = "authorize"
MODEL_DEAUTHORIZE_ACTION = "deauthorize"
MODEL_LIST_ACTION = "list"
MODEL_PORTFOLIO_ACTION = "portfolio"
MODEL_SHOW_ACTION = "show"
MODEL_IDENTIFIER_ATTRIBUTE = "model_identifier"


def _json_value(
    value: str,
) -> JsonValue:
    """Parse one JSON-compatible command-line value."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ArgumentTypeError(f"Expected value must be valid JSON: {exc.msg}") from exc

    return cast(
        JsonValue,
        parsed,
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
        type=_json_value,
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
        type=_json_value,
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

    model_parser = commands.add_parser(
        MODEL_COMMAND,
        help="Inspect and operate provider models.",
    )

    model_actions = model_parser.add_subparsers(
        dest=MODEL_ACTION_ATTRIBUTE,
    )

    model_authorize_parser = model_actions.add_parser(
        MODEL_AUTHORIZE_ACTION,
        help="Authorize one currently available provider model.",
    )

    model_authorize_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to authorize.",
    )

    model_deauthorize_parser = model_actions.add_parser(
        MODEL_DEAUTHORIZE_ACTION,
        help="Remove one model from organizational authorization.",
    )

    model_deauthorize_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to deauthorize.",
    )

    model_actions.add_parser(
        MODEL_LIST_ACTION,
        help="List currently available provider models.",
    )

    model_actions.add_parser(
        MODEL_PORTFOLIO_ACTION,
        help="List models authorized for organizational selection.",
    )

    model_show_parser = model_actions.add_parser(
        MODEL_SHOW_ACTION,
        help="Show one currently available provider model.",
    )

    model_show_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to inspect.",
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

    if command == WORKFLOW_COMMAND:
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

        if action == WORKFLOW_INVOKE_ACTION:
            return invoke_workflow(
                workflow_id=cast(
                    UUID,
                    getattr(
                        arguments,
                        WORKFLOW_ID_ATTRIBUTE,
                    ),
                ),
                payload=cast(
                    JsonValue,
                    getattr(
                        arguments,
                        WORKFLOW_INPUT_ATTRIBUTE,
                    ),
                ),
            )

        if action == WORKFLOW_PROMOTE_ACTION:
            workflow_id = cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            )

            return promote_workflow(
                workflow_id,
            )

        if action == WORKFLOW_OPTIMIZE_ACTION:
            return optimize_workflow(
                workflow_id=cast(
                    UUID,
                    getattr(
                        arguments,
                        WORKFLOW_ID_ATTRIBUTE,
                    ),
                ),
                expected_value=cast(
                    JsonValue,
                    getattr(
                        arguments,
                        EXPECTED_VALUE_ATTRIBUTE,
                    ),
                ),
                target_latency_seconds=cast(
                    float,
                    getattr(
                        arguments,
                        TARGET_LATENCY_ATTRIBUTE,
                    ),
                ),
                target_cost_usd=cast(
                    float,
                    getattr(
                        arguments,
                        TARGET_COST_ATTRIBUTE,
                    ),
                ),
                generations=cast(
                    int,
                    getattr(
                        arguments,
                        GENERATIONS_ATTRIBUTE,
                    ),
                ),
            )

        return None

    if command == MODEL_COMMAND:
        action = cast(
            str | None,
            getattr(
                arguments,
                MODEL_ACTION_ATTRIBUTE,
                None,
            ),
        )

        if action == MODEL_AUTHORIZE_ACTION:
            model_identifier = cast(
                str,
                getattr(
                    arguments,
                    MODEL_IDENTIFIER_ATTRIBUTE,
                ),
            )

            return authorize_model(model_identifier)

        if action == MODEL_DEAUTHORIZE_ACTION:
            model_identifier = cast(
                str,
                getattr(
                    arguments,
                    MODEL_IDENTIFIER_ATTRIBUTE,
                ),
            )

            return deauthorize_model(model_identifier)

        if action == MODEL_LIST_ACTION:
            return list_models()

        if action == MODEL_PORTFOLIO_ACTION:
            return list_portfolio_models()

        if action == MODEL_SHOW_ACTION:
            model_identifier = cast(
                str,
                getattr(
                    arguments,
                    MODEL_IDENTIFIER_ATTRIBUTE,
                ),
            )

            return show_model(model_identifier)

        return None

    return None
