"""Workflow command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.parsing import (
    EXPECTED_VALUE_ATTRIBUTE,
    GENERATIONS_ATTRIBUTE,
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ACTION_ATTRIBUTE,
    WORKFLOW_DOCUMENT_ATTRIBUTE,
    WORKFLOW_EXPERIMENT_LIMIT_ATTRIBUTE,
    WORKFLOW_EXPERIMENTS_ACTION,
    WORKFLOW_ID_ATTRIBUTE,
    WORKFLOW_IMPORT_ACTION,
    WORKFLOW_INPUT_ATTRIBUTE,
    WORKFLOW_INVOKE_ACTION,
    WORKFLOW_LIST_ACTION,
    WORKFLOW_OPTIMIZE_ACTION,
    WORKFLOW_PROMOTE_ACTION,
    WORKFLOW_RUN_ACTION,
    WORKFLOW_RUN_LIMIT_ATTRIBUTE,
    WORKFLOW_RUNS_ACTION,
    WORKFLOW_SHOW_ACTION,
)

WorkflowIdentifierHandler = Callable[[UUID], int]
WorkflowImportHandler = Callable[[Path], int]
WorkflowListHandler = Callable[[], int]
WorkflowInvokeHandler = Callable[..., int]
WorkflowOptimizeHandler = Callable[..., int]
WorkflowHistoryHandler = Callable[..., int]


def dispatch_workflow_command(
    arguments: Namespace,
    *,
    import_workflow: WorkflowImportHandler,
    invoke_workflow: WorkflowInvokeHandler,
    list_workflow_experiments: WorkflowHistoryHandler,
    list_workflow_runs: WorkflowHistoryHandler,
    list_workflows: WorkflowListHandler,
    optimize_workflow: WorkflowOptimizeHandler,
    promote_workflow: WorkflowIdentifierHandler,
    run_workflow: WorkflowIdentifierHandler,
    show_workflow: WorkflowIdentifierHandler,
) -> int | None:
    """Dispatch one parsed workflow command."""

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

    if action == WORKFLOW_RUNS_ACTION:
        return list_workflow_runs(
            cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            ),
            limit=cast(
                int | None,
                getattr(
                    arguments,
                    WORKFLOW_RUN_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
        )

    if action == WORKFLOW_EXPERIMENTS_ACTION:
        return list_workflow_experiments(
            cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            ),
            limit=cast(
                int | None,
                getattr(
                    arguments,
                    WORKFLOW_EXPERIMENT_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
        )

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
