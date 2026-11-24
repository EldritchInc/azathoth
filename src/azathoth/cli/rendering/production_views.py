"""Human-readable production and invocations, as the service API returns them (ADR 0140).

`workflow production`, `workflow revisions`, `workflow promote`, `workflow
rollback`, `workflow invocations` and `invocation show` given `--remote`
read the service API, and print each line the command prints here.
"""

from collections.abc import Callable, Mapping, Sequence

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.rendering.citations import RecordedCitations, render_citation_lines
from azathoth.cli.rendering.invocation_history import (
    _OUTCOME_WIDTH,
    NO_RUN_MARKER,
    PENDING_OUTCOME,
    SUCCEEDED_OUTCOME,
)
from azathoth.cli.rendering.production import ACTIVE_REVISION_MARKER, INACTIVE_REVISION_MARKER
from azathoth.cli.rendering.resumes import render_resume_lines
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines


def author_text(
    author: api.Author,
) -> str:
    """Return an author as a revision names one: `Name <email>`, or `Name` without an email."""

    return author.name if author.email is None else f"{author.name} <{author.email}>"


def _model_lines(
    steps: Sequence[api.ProductionStepModels],
) -> list[str]:
    """Return the lines naming each prompt step's primary model and its substitutes."""

    lines: list[str] = []

    for step in steps:
        lines.extend(("", f"Prompt Step: {step.step_id}", f"Primary Model: {step.primary}"))

        if step.substitutes:
            lines.append("Substitute Models: " + ", ".join(step.substitutes))

    return lines


def render_production_state(
    state: api.ProductionState,
) -> str:
    """Render what a workflow's production runs now, as `workflow production` does."""

    revision = state.revision

    lines = [
        f"Workflow: {state.workflow_name}",
        f"Workflow ID: {state.workflow_id}",
        "Revision ID: " + (str(revision.revision_id) if revision is not None else "unrecorded"),
        (
            f"Author: {author_text(revision.author)}"
            if revision is not None and revision.author is not None
            else "Author: unknown"
        ),
    ]

    if revision is not None and revision.restores is not None:
        lines.append(f"Restores: {revision.restores}")

    lines.append(
        "Deployed At: " + (revision.created_at.isoformat() if revision is not None else "unknown")
    )

    for label, schema in (
        ("Input Schema", state.input_schema),
        ("Output Schema", state.output_schema),
    ):
        if schema is not None:
            lines.extend((f"{label}:", render_json_value(schema)))

    lines.extend(_model_lines(state.steps))

    if state.emissions:
        lines.append("")
        lines.extend(
            f"Emission: {emission.name} <- {emission.source}" for emission in state.emissions
        )

    return "\n".join(lines)


def render_revision_summaries(
    revisions: Sequence[api.ProductionRevisionSummary],
) -> str:
    """Render one line per production revision in the order given, as `workflow revisions` does."""

    lines = []

    for revision in revisions:
        marker = ACTIVE_REVISION_MARKER if revision.active else INACTIVE_REVISION_MARKER
        models = ", ".join(step.primary for step in revision.steps)
        line = (
            f"{revision.revision_id}  {revision.created_at.isoformat()}  {marker:<6}  "
            f"{models or 'no prompt steps'}"
        )

        if revision.author is not None:
            line += f"  by {author_text(revision.author)}"

        if revision.restores is not None:
            line += f"  restores {revision.restores}"

        lines.append(line)

    return "\n".join(lines)


def render_deployment(
    revision: api.ProductionRevisionSummary,
    *,
    workflow_name: str,
    status: str,
) -> str:
    """Render a new production revision, as `workflow promote` and `workflow rollback` do."""

    lines = [
        f"Workflow: {workflow_name}",
        f"Workflow ID: {revision.workflow_id}",
        f"Revision ID: {revision.revision_id}",
        f"Status: {status}",
    ]

    if revision.restores is not None:
        lines.append(f"Restores: {revision.restores}")

    lines.extend(
        (
            (
                f"Author: {author_text(revision.author)}"
                if revision.author is not None
                else "Author: unknown"
            ),
            f"Created At: {revision.created_at.isoformat()}",
        )
    )
    lines.extend(_model_lines(revision.steps))

    return "\n".join(lines)


def _outcome(
    status: str,
    error_code: str | None,
) -> str:
    """Return an invocation's outcome label: succeeded, pending, or its error's code."""

    if status == "succeeded":
        return SUCCEEDED_OUTCOME

    if status == "incomplete" or error_code is None:
        return PENDING_OUTCOME

    return error_code


def render_invocation_summaries(
    invocations: Sequence[api.InvocationSummary],
) -> str:
    """Render one line per invocation in the order given, as `workflow invocations` does."""

    return "\n".join(
        f"{invocation.invocation_id}  {invocation.created_at.isoformat()}  "
        f"{_outcome(invocation.status, invocation.error_code):<{_OUTCOME_WIDTH}}  "
        f"{invocation.run_id if invocation.run_id is not None else NO_RUN_MARKER}"
        for invocation in invocations
    )


def render_invocation_detail(
    invocation: api.InvocationDetail,
    *,
    link: Callable[[Mapping[str, JsonValue]], str | None] | None = None,
) -> str:
    """Render one invocation's recorded history, as `invocation show` does."""

    run = invocation.run
    error = invocation.error

    lines = [
        f"Invocation ID: {invocation.invocation_id}",
        *render_sensitivity_lines(invocation.sensitivity),
        f"Workflow ID: {invocation.workflow_id}",
        f"Created At: {invocation.created_at.isoformat()}",
        f"Outcome: {_outcome(invocation.status, error.code if error is not None else None)}",
        f"Run ID: {run.run_id if run is not None else NO_RUN_MARKER}",
        *render_resume_lines(run.resumes if run is not None else 0),
    ]

    if invocation.idempotency_key is not None and invocation.request_digest is not None:
        lines.extend(
            (
                f"Idempotency Key: {invocation.idempotency_key}",
                f"Request Digest: {invocation.request_digest}",
            )
        )

    lineage = invocation.lineage

    if lineage is not None:
        lines.extend(
            (
                f"Depth: {lineage.depth}",
                f"Parent Workflow ID: {lineage.parent_workflow_id}",
                f"Parent Run ID: {lineage.parent_run_id}",
                f"Parent Step ID: {lineage.parent_step_id} (attempt {lineage.parent_attempt})",
                f"Root Workflow ID: {lineage.root_workflow_id}",
                f"Root Run ID: {lineage.root_run_id}",
            )
        )

    if invocation.caller_metadata:
        lines.extend(("Caller Metadata:", render_json_value(invocation.caller_metadata)))

    lines.extend(("Input:", render_json_value(invocation.input)))

    if invocation.input_provenance is not None:
        lines.extend(("Input Provenance:", render_json_value(invocation.input_provenance)))

    if invocation.status == "succeeded":
        lines.extend(("Result:", render_json_value(invocation.result)))

    if invocation.status == "failed" and error is not None:
        lines.append(f"Message: {error.message}")

        if error.metadata:
            lines.extend(("Metadata:", render_json_value(error.metadata)))

    lines.extend(
        render_citation_lines(
            [
                RecordedCitations(step_id=cited.step_id, record=cited.record, checks=cited.checks)
                for cited in invocation.citations
            ],
            link=link,
        )
    )

    return "\n".join(lines)


__all__ = [
    "author_text",
    "render_deployment",
    "render_invocation_detail",
    "render_invocation_summaries",
    "render_production_state",
    "render_revision_summaries",
]
