"""Workflow run inspection commands for the Azathoth CLI."""

import sys
from collections.abc import Iterable
from uuid import UUID

from pydantic import JsonValue, ValidationError

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    WorkflowRunSource,
    render_workflow_run,
    render_workflow_run_feedback,
    render_workflow_run_summaries,
)
from azathoth.workflows import (
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowExperimentRepository,
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

    run_sources = _run_sources(
        configuration,
        workflow_id,
    )

    latest_dispositions = _latest_dispositions(
        SQLiteWorkflowRunFeedbackRepository(
            configuration.database,
        ).feedback(),
    )

    print(
        render_workflow_run_summaries(
            newest_first,
            run_sources=run_sources,
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


def record_run_feedback(
    run_id: UUID,
    *,
    disposition: WorkflowRunFeedbackDisposition,
    reason: str | None = None,
    corrected_output: JsonValue = None,
) -> int:
    """Record one immutable judgment about a persisted workflow run.

    Only existing runs can be judged. A corrected output contradicts a good
    disposition, so it is accepted only with bad feedback. Blank reasons are
    treated as absent, and domain validation decides whether the remaining
    judgment is acceptable. Nothing is saved when any check fails.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    if (
        SQLiteWorkflowRunRepository(
            configuration.database,
        ).get(run_id)
        is None
    ):
        print(
            f"Run {run_id} was not found.",
            file=sys.stderr,
        )

        return 1

    if disposition is WorkflowRunFeedbackDisposition.GOOD and corrected_output is not None:
        print(
            "A corrected output can only accompany bad feedback.",
            file=sys.stderr,
        )

        return 1

    normalized_reason = reason.strip() if reason is not None else None

    try:
        feedback = WorkflowRunFeedback(
            run_id=run_id,
            disposition=disposition,
            reason=normalized_reason or None,
            corrected_output=corrected_output,
        )
    except ValidationError as exc:
        for error in exc.errors():
            print(
                _validation_message(error["msg"]),
                file=sys.stderr,
            )

        return 1

    SQLiteWorkflowRunFeedbackRepository(
        configuration.database,
    ).save(feedback)

    print(f"Recorded {disposition.value} feedback {feedback.id} for run {run_id}.")

    return 0


def _run_sources(
    configuration: CliRuntimeConfiguration,
    workflow_id: UUID,
) -> dict[UUID, WorkflowRunSource]:
    """Return the known source of each run that did not come from configured execution.

    Runs observed by an experiment came from optimization. Runs associated with
    a production invocation came from production and take precedence.
    """

    sources: dict[UUID, WorkflowRunSource] = {
        observation.run_id: WorkflowRunSource.EXPERIMENT
        for experiment in SQLiteWorkflowExperimentRepository(
            configuration.database,
        ).experiments_for_workflow(workflow_id)
        for observation in experiment.observations
    }

    for association in SQLiteProductionInvocationRunRepository(
        configuration.database,
    ).associations():
        sources[association.run_id] = WorkflowRunSource.PRODUCTION

    return sources


def _validation_message(
    message: str,
) -> str:
    """Remove pydantic's value-error prefix from one domain validation message."""

    return message.removeprefix("Value error, ")


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
