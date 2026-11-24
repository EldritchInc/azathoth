"""Workflow run inspection commands for the Azathoth CLI."""

import sys
from uuid import UUID

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_interrupted_runs,
    render_run_children,
)
from azathoth.cli.rendering.run_details import (
    render_run_detail,
    render_run_evaluations,
    render_run_feedback,
    render_run_summaries,
)
from azathoth.cli.rendering.sensitivity import warn_if_restricted
from azathoth.cli.service import service_instance
from azathoth.workflows import WorkflowRunFeedbackDisposition


def list_workflow_runs(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List the kept runs of one workflow, newest first, through `runs.list` (ADR 0140).

    Runs are listed for workflows that are configured or that have run history,
    so runs of a workflow since removed from configuration remain inspectable.
    An identifier with neither fails so mistyped identifiers are not mistaken
    for workflows that never ran.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        runs = service_instance(configuration).runs.list(workflow_id, limit=limit)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    if runs:
        print(render_run_summaries(runs))

    return 0


def show_run(
    run_id: UUID,
) -> int:
    """Show one kept run with its evidence and every judgment of it, through `runs.get`.

    Evaluator judgments follow the run evidence and precede human feedback,
    each in the order it was recorded.

    A run that was resumed names how often (ADR 0105). One that journaled
    but never finished is not kept yet, so it is not shown; the command says
    how to resume it instead.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        instance = service_instance(configuration)
        run = instance.runs.get(run_id)
        children = instance.runs.children(run_id)
        feedback = instance.runs.feedback(run_id)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        "\n\n".join(
            (
                render_run_detail(run, children=len(children)),
                render_run_evaluations(run.evaluations),
                render_run_feedback(tuple(reversed(feedback))),
            )
        )
    )

    warn_if_restricted(run.sensitivity, f"Run {run_id}")

    return 0


def list_run_children(
    run_id: UUID,
) -> int:
    """List the runs a run's steps started, oldest first, with each one's status (ADR 0105).

    The children are the service API's (ADR 0129).

    It works for a run that never finished too, because a child is indexed
    as it starts. A run neither recorded nor journaled is not found.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        children = service_instance(configuration).runs.children(run_id)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(render_run_children(run_id, children))

    return 0


def list_interrupted_runs(
    workflow_id: UUID,
) -> int:
    """List a workflow's runs that started and never finished, newest first (ADR 0129).

    Each names the command that resumes it, the run's or its invocation's.
    Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        runs = service_instance(configuration).runs.interrupted(workflow_id)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(render_interrupted_runs(workflow_id, runs))

    return 0


def record_run_feedback(
    run_id: UUID,
    *,
    disposition: WorkflowRunFeedbackDisposition,
    reason: str | None = None,
    corrected_output: JsonValue = None,
) -> int:
    """Record one immutable judgment about a persisted workflow run, through the service API.

    Only existing runs can be judged. A corrected output contradicts a good
    disposition, so it is accepted only with bad feedback. Blank reasons are
    treated as absent, and domain validation decides whether the remaining
    judgment is acceptable. Nothing is saved when any check fails (ADR 0129).
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        feedback = service_instance(configuration).runs.record_feedback(
            run_id,
            disposition.value,
            reason=reason,
            corrected_output=corrected_output,
        )
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Recorded {feedback.disposition} feedback {feedback.feedback_id} for run {run_id}.")

    return 0
