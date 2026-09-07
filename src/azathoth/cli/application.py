"""Command-line application for Azathoth."""

from argparse import Namespace
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.models import (
    authorize_model,
    deauthorize_model,
    list_models,
    list_portfolio_models,
    show_model,
)
from azathoth.cli.parsing import (
    COMMAND_ATTRIBUTE,
    EXPECTED_VALUE_ATTRIBUTE,
    GENERATIONS_ATTRIBUTE,
    MODEL_ACTION_ATTRIBUTE,
    MODEL_AUTHORIZE_ACTION,
    MODEL_COMMAND,
    MODEL_DEAUTHORIZE_ACTION,
    MODEL_IDENTIFIER_ATTRIBUTE,
    MODEL_LIST_ACTION,
    MODEL_PORTFOLIO_ACTION,
    MODEL_SHOW_ACTION,
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
    build_parser,
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
