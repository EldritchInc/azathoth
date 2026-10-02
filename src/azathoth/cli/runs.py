"""Workflow run inspection commands for the Azathoth CLI."""

import sys
from collections.abc import Iterable
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
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
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

    latest_dispositions = _latest_dispositions(
        SQLiteWorkflowRunFeedbackRepository(
            configuration.database,
        ).feedback(),
    )

    print(
        render_workflow_run_summaries(
            newest_first,
            production_run_ids=production_run_ids,
            latest_dispositions=latest_dispositions,
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


def _latest_dispositions(
    feedback: Iterable[WorkflowRunFeedback],
) -> dict[UUID, WorkflowRunFeedbackDisposition]:
    """Return each judged run's most recent disposition.

    Feedback is read in insertion order, so a later record wins a timestamp tie.
    """

    latest: dict[UUID, WorkflowRunFeedback] = {}

    for record in feedback:
        current = latest.get(record.run_id)

        if current is None or record.created_at >= current.created_at:
            latest[record.run_id] = record

    return {run_id: record.disposition for run_id, record in latest.items()}
