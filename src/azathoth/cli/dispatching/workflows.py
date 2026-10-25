"""Workflow command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.parsing import (
    GENERATIONS_ATTRIBUTE,
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ACTION_ATTRIBUTE,
    WORKFLOW_BENCHMARK_ID_ATTRIBUTE,
    WORKFLOW_DOCUMENT_ATTRIBUTE,
    WORKFLOW_EXPERIMENT_LIMIT_ATTRIBUTE,
    WORKFLOW_EXPERIMENTS_ACTION,
    WORKFLOW_EXPORT_ACTION,
    WORKFLOW_HISTORY_ACTION,
    WORKFLOW_HISTORY_LIMIT_ATTRIBUTE,
    WORKFLOW_ID_ATTRIBUTE,
    WORKFLOW_IMPORT_ACTION,
    WORKFLOW_INPUT_ATTRIBUTE,
    WORKFLOW_INVOCATION_LIMIT_ATTRIBUTE,
    WORKFLOW_INVOCATIONS_ACTION,
    WORKFLOW_INVOKE_ACTION,
    WORKFLOW_LIST_ACTION,
    WORKFLOW_OPTIMIZE_ACTION,
    WORKFLOW_OUTPUT_ATTRIBUTE,
    WORKFLOW_PRODUCTION_ACTION,
    WORKFLOW_PROMOTE_ACTION,
    WORKFLOW_REVISION_LIMIT_ATTRIBUTE,
    WORKFLOW_REVISIONS_ACTION,
    WORKFLOW_RUN_ACTION,
    WORKFLOW_RUN_LIMIT_ATTRIBUTE,
    WORKFLOW_RUNS_ACTION,
    WORKFLOW_SHOW_ACTION,
    WORKFLOW_SPECIFICATION_REVISION_ATTRIBUTE,
)

WorkflowIdentifierHandler = Callable[[UUID], int]
WorkflowImportHandler = Callable[[Path], int]
WorkflowListHandler = Callable[[], int]
WorkflowInvokeHandler = Callable[..., int]
WorkflowOptimizeHandler = Callable[..., int]
WorkflowHistoryHandler = Callable[..., int]
WorkflowRevisionHandler = Callable[..., int]
WorkflowRunHandler = Callable[..., int]


def dispatch_workflow_command(
    arguments: Namespace,
    *,
    export_workflow: WorkflowRevisionHandler,
    import_workflow: WorkflowImportHandler,
    invoke_workflow: WorkflowInvokeHandler,
    list_workflow_experiments: WorkflowHistoryHandler,
    list_workflow_history: WorkflowHistoryHandler,
    list_workflow_invocations: WorkflowHistoryHandler,
    list_workflow_revisions: WorkflowHistoryHandler,
    list_workflow_runs: WorkflowHistoryHandler,
    list_workflows: WorkflowListHandler,
    optimize_workflow: WorkflowOptimizeHandler,
    promote_workflow: WorkflowIdentifierHandler,
    run_workflow: WorkflowRunHandler,
    show_workflow: WorkflowRevisionHandler,
    show_workflow_production: WorkflowIdentifierHandler,
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

        return show_workflow(
            workflow_id,
            revision=_specification_revision(arguments),
        )

    if action == WORKFLOW_EXPORT_ACTION:
        return export_workflow(
            cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            ),
            revision=_specification_revision(arguments),
        )

    if action == WORKFLOW_HISTORY_ACTION:
        return list_workflow_history(
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
                    WORKFLOW_HISTORY_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
        )

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

        return run_workflow(
            workflow_id,
            output=_output_format(arguments),
        )

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

    if action == WORKFLOW_PRODUCTION_ACTION:
        return show_workflow_production(
            cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            )
        )

    if action == WORKFLOW_REVISIONS_ACTION:
        return list_workflow_revisions(
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
                    WORKFLOW_REVISION_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
        )

    if action == WORKFLOW_INVOCATIONS_ACTION:
        return list_workflow_invocations(
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
                    WORKFLOW_INVOCATION_LIMIT_ATTRIBUTE,
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
            output=_output_format(arguments),
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
            benchmark_id=cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_BENCHMARK_ID_ATTRIBUTE,
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


def _specification_revision(
    arguments: Namespace,
) -> int | None:
    """Return the requested imported revision number, if any."""

    return cast(
        int | None,
        getattr(
            arguments,
            WORKFLOW_SPECIFICATION_REVISION_ATTRIBUTE,
            None,
        ),
    )


def _output_format(
    arguments: Namespace,
) -> WorkflowOutputFormat:
    """Return the requested output format of a workflow execution command."""

    return WorkflowOutputFormat(
        cast(
            str,
            getattr(
                arguments,
                WORKFLOW_OUTPUT_ATTRIBUTE,
            ),
        )
    )
