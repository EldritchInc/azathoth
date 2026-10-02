"""Workflow run inspection commands for the Azathoth CLI."""

import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_workflow_run,
    render_workflow_run_feedback,
    render_workflow_run_summaries,
)
from azathoth.workflows import (
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
)


def list_workflow_runs(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List persisted runs of one workflow, newest first.

    Runs are listed for workflows that are configured or that have run history,
    so runs of a workflow since removed from configuration remain inspectable.
    An identifier with neither fails so mistyped identifiers are not mistaken
    for workflows that never ran.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    runs = SQLiteWorkflowRunRepository(
        configuration.database,
    ).runs_for_workflow(workflow_id)

    if (
        not runs
        and SQLiteWorkflowRepository(
            configuration.database,
        ).get(workflow_id)
        is None
    ):
        print(
            f"Workflow {workflow_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    newest_first = sorted(
        runs,
        key=lambda run: run.started_at,
        reverse=True,
    )

    if limit is not None:
        newest_first = newest_first[:limit]

    if not newest_first:
        return 0

    production_run_ids = frozenset(
        association.run_id
        for association in SQLiteProductionInvocationRunRepository(
            configuration.database,
        ).associations()
    )

    print(
        render_workflow_run_summaries(
            newest_first,
            production_run_ids=production_run_ids,
        )
    )

    return 0


def show_run(
    run_id: UUID,
) -> int:
    """Show one persisted workflow run with step evidence, resources, and feedback."""

    configuration = CliRuntimeConfiguration.from_environment()

    run = SQLiteWorkflowRunRepository(
        configuration.database,
    ).get(run_id)

    if run is None:
        print(
            f"Run {run_id} was not found.",
            file=sys.stderr,
        )

        return 1

    feedback = SQLiteWorkflowRunFeedbackRepository(
        configuration.database,
    ).feedback_for_run(run_id)

    print(
        "\n\n".join(
            (
                render_workflow_run(run),
                render_workflow_run_feedback(feedback),
            )
        )
    )

    return 0
