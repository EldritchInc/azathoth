"""Production deployment and invocation inspection commands for the Azathoth CLI."""

import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering import (
    render_production_invocation,
    render_production_invocation_summaries,
    render_workflow_production,
    render_workflow_revision_summaries,
)
from azathoth.workflows import (
    ProductionInvocationResult,
    active_production_revision,
)


def show_workflow_production(
    workflow_id: UUID,
) -> int:
    """Show the active production configuration of one workflow.

    The active state is execution authority, so it is shown even when the
    workflow has since been removed from configuration. The matching revision
    supplies deployment identity and time when one was recorded.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    state = repositories(configuration).production_states.get(workflow_id)

    if state is None:
        if _is_configured(configuration, workflow_id):
            print(
                f"Workflow {workflow_id} is not in production.",
                file=sys.stderr,
            )
        else:
            _report_unconfigured(workflow_id)

        return 1

    revisions = repositories(configuration).production_revisions.revisions_for_workflow(workflow_id)

    print(
        render_workflow_production(
            state,
            active_revision=active_production_revision(
                state,
                revisions,
            ),
        )
    )

    return 0


def list_workflow_revisions(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List production revisions of one workflow, newest first.

    Revisions are listed for workflows that are configured or that have
    revision history. An identifier with neither fails so mistyped identifiers
    are not mistaken for workflows never promoted.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    revisions = repositories(configuration).production_revisions.revisions_for_workflow(workflow_id)

    if not revisions and not _is_configured(configuration, workflow_id):
        _report_unconfigured(workflow_id)

        return 1

    newest_first = sorted(
        revisions,
        key=lambda revision: revision.created_at,
        reverse=True,
    )

    if limit is not None:
        newest_first = newest_first[:limit]

    if not newest_first:
        return 0

    state = repositories(configuration).production_states.get(workflow_id)

    active = (
        active_production_revision(
            state,
            revisions,
        )
        if state is not None
        else None
    )

    print(
        render_workflow_revision_summaries(
            newest_first,
            active_revision_id=active.id if active is not None else None,
        )
    )

    return 0


def list_workflow_invocations(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List production invocations of one workflow, newest first.

    Invocations are listed for workflows that are configured or that have
    invocation history. An identifier with neither fails so mistyped
    identifiers are not mistaken for workflows never invoked.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    invocation_repository = repositories(configuration).invocations

    invocations = invocation_repository.invocations_for_workflow(workflow_id)

    if not invocations and not _is_configured(configuration, workflow_id):
        _report_unconfigured(workflow_id)

        return 1

    newest_first = sorted(
        invocations,
        key=lambda invocation: invocation.created_at,
        reverse=True,
    )

    if limit is not None:
        newest_first = newest_first[:limit]

    if not newest_first:
        return 0

    run_repository = repositories(configuration).invocation_runs

    results: dict[UUID, ProductionInvocationResult] = {}
    run_ids: dict[UUID, UUID] = {}

    for invocation in newest_first:
        result = invocation_repository.result(invocation.id)

        if result is not None:
            results[invocation.id] = result

        association = run_repository.get(invocation.id)

        if association is not None:
            run_ids[invocation.id] = association.run_id

    print(
        render_production_invocation_summaries(
            newest_first,
            results=results,
            run_ids=run_ids,
        )
    )

    return 0


def show_invocation(
    invocation_id: UUID,
) -> int:
    """Show one production invocation with its input, outcome, and run."""

    configuration = CliRuntimeConfiguration.from_environment()

    invocation_repository = repositories(configuration).invocations

    invocation = invocation_repository.get(invocation_id)

    if invocation is None:
        print(
            f"Invocation {invocation_id} was not found.",
            file=sys.stderr,
        )

        return 1

    association = repositories(configuration).invocation_runs.get(invocation_id)

    print(
        render_production_invocation(
            invocation,
            result=invocation_repository.result(invocation_id),
            run_id=association.run_id if association is not None else None,
        )
    )

    return 0


def _is_configured(
    configuration: CliRuntimeConfiguration,
    workflow_id: UUID,
) -> bool:
    """Return whether one workflow is present in configuration."""

    return repositories(configuration).workflows.get(workflow_id) is not None


def _report_unconfigured(
    workflow_id: UUID,
) -> None:
    """Report an identifier that is neither configured nor in history."""

    print(
        f"Workflow {workflow_id} is not configured.",
        file=sys.stderr,
    )
