"""Production deployment and invocation inspection commands for the Azathoth CLI."""

import sys
from collections.abc import Callable, Mapping
from uuid import UUID

from pydantic import JsonValue

from azathoth.citations import (
    VERIFIED_STATUSES,
    LinkResolutionError,
    SourceAnchor,
    default_link_resolvers,
    link_expiry_seconds,
    resolve_link,
)
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering import (
    RecordedCitations,
    render_production_invocation,
    render_production_invocation_summaries,
    render_workflow_production,
    render_workflow_revision_summaries,
)
from azathoth.cli.rendering.sensitivity import warn_if_restricted
from azathoth.context import context_sensitivity
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import CitationCheckError, stored_citation_checks
from azathoth.workflows import (
    ProductionInvocationResult,
    active_production_revision,
    journal_resumes,
    journaled_citations,
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
    *,
    links: bool = False,
) -> int:
    """Show one production invocation with its input, outcome, and run.

    An incomplete invocation names the run its journal records, and an
    invocation whose run was resumed names how often (ADR 0105). Every check
    a cited step of the run kept is read from the content store and shown
    (ADR 0116). With `links`, each verified check is followed by a link to
    its place in its document, made by the resolver of its origin's scheme;
    an `s3://` link is presigned, and valid for `AZATHOTH_LINK_EXPIRY_SECONDS`
    (ADR 0117).
    """

    configuration = CliRuntimeConfiguration.from_environment()

    invocation_repository = repositories(configuration).invocations

    invocation = invocation_repository.get(invocation_id)

    if invocation is None:
        print(
            f"Invocation {invocation_id} was not found.",
            file=sys.stderr,
        )

        return 1

    stored = repositories(configuration)
    association = stored.invocation_runs.get(invocation_id)
    journal = stored.run_journal

    #
    # A run that never finished is not associated yet, but its journal
    # names it (ADR 0105).
    #
    run_id = (
        association.run_id if association is not None else journal.invocation_run_id(invocation_id)
    )

    try:
        citations = [] if run_id is None else _recorded_citations(stored, run_id)
    except CitationCheckError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    try:
        rendered = render_production_invocation(
            invocation,
            result=invocation_repository.result(invocation_id),
            run_id=run_id,
            resumes=0 if run_id is None else journal_resumes(journal.entries(run_id)),
            citations=citations,
            link=_check_link() if links else None,
        )
    except LinkResolutionError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(rendered)

    warn_if_restricted(
        context_sensitivity(invocation.initial_context), f"Invocation {invocation_id}"
    )

    return 0


def _check_link() -> Callable[[Mapping[str, JsonValue]], str | None]:
    """Return what links a kept check to its place, by its origin's resolver (ADR 0117).

    Only a verified check is anchored, so only one is linked.

    Raises:
        LinkResolutionError: `AZATHOTH_LINK_EXPIRY_SECONDS` is not valid.
    """

    resolvers = default_link_resolvers(expires_in=link_expiry_seconds())
    verified = frozenset(status.value for status in VERIFIED_STATUSES)

    def link(
        check: Mapping[str, JsonValue],
    ) -> str | None:
        anchor = check.get("anchor")

        if check.get("status") not in verified or not isinstance(anchor, dict):
            return None

        return resolve_link(SourceAnchor.model_validate(anchor), resolvers)

    return link


def _recorded_citations(
    stored: Repositories,
    run_id: UUID,
) -> list[RecordedCitations]:
    """Return every citations record a run's cited steps kept, with the checks it holds.

    The content store is opened only for a run that kept one.

    Raises:
        CitationCheckError: A record's content is not a record of checks.
    """

    return [
        RecordedCitations(
            step_id=step_id,
            record=digest,
            checks=stored_citation_checks(stored.content, digest),
        )
        for step_id, digest in journaled_citations(stored.run_journal, run_id)
    ]


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
