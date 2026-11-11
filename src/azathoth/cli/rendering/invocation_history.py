"""Human-readable production invocation history rendering."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.rendering.citations import RecordedCitations, render_citation_lines
from azathoth.cli.rendering.lineage import render_lineage_lines
from azathoth.cli.rendering.resumes import render_resume_lines
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines
from azathoth.context import context_sensitivity
from azathoth.workflows import (
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
)
from azathoth.workflows.production_invocation import (
    PRODUCTION_INVOCATION_EVENT_TYPE,
)

SUCCEEDED_OUTCOME = "succeeded"
PENDING_OUTCOME = "pending"
NO_RUN_MARKER = "no run"

_OUTCOME_WIDTH = max(
    len(outcome)
    for outcome in (
        SUCCEEDED_OUTCOME,
        PENDING_OUTCOME,
        *(code.value for code in ProductionInvocationErrorCode),
    )
)


def render_production_invocation_summaries(
    invocations: Iterable[ProductionInvocation],
    *,
    results: Mapping[UUID, ProductionInvocationResult],
    run_ids: Mapping[UUID, UUID],
) -> str:
    """Render one line per production invocation in the order given.

    Each line contains the invocation ID, creation time, outcome, and the
    associated run ID when one was recorded.
    """

    return "\n".join(
        _render_invocation_summary(
            invocation,
            result=results.get(invocation.id),
            run_id=run_ids.get(invocation.id),
        )
        for invocation in invocations
    )


def render_production_invocation(
    invocation: ProductionInvocation,
    *,
    result: ProductionInvocationResult | None,
    run_id: UUID | None,
    resumes: int = 0,
    citations: Sequence[RecordedCitations] = (),
    link: Callable[[Mapping[str, JsonValue]], str | None] | None = None,
) -> str:
    """Render the full recorded history of one production invocation.

    An input that has provenance, a reference or an inline input that is
    binary or names an origin, is followed by it (ADR 0112). An invocation
    started through a job envelope names its idempotency key
    and request digest (ADR 0097). An invocation started by a step of another
    run names its depth, the parent step and the root run (ADR 0104). One
    whose run was resumed names how often, after its run (ADR 0105). One
    whose run had cited steps ends with every check they kept (ADR 0116),
    each with its link when `link` gives one (ADR 0117). One whose label is
    not internal names it right after its ID (ADR 0123).
    """

    lines = [
        f"Invocation ID: {invocation.id}",
        *render_sensitivity_lines(context_sensitivity(invocation.initial_context)),
        f"Workflow ID: {invocation.workflow_id}",
        f"Created At: {invocation.created_at.isoformat()}",
        f"Outcome: {production_invocation_outcome(result)}",
        f"Run ID: {run_id if run_id is not None else NO_RUN_MARKER}",
        *render_resume_lines(resumes),
    ]

    if invocation.idempotency is not None:
        lines.extend(
            (
                f"Idempotency Key: {invocation.idempotency.key}",
                f"Request Digest: {invocation.idempotency.request_digest}",
            )
        )

    lines.extend(render_lineage_lines(invocation.initial_context))

    if invocation.caller_metadata:
        lines.extend(
            (
                "Caller Metadata:",
                render_json_value(invocation.caller_metadata),
            )
        )

    lines.extend(
        (
            "Input:",
            render_json_value(production_invocation_input(invocation)),
        )
    )

    provenance = production_invocation_input_provenance(invocation)

    if provenance is not None:
        lines.extend(
            (
                "Input Provenance:",
                render_json_value(provenance),
            )
        )

    if isinstance(
        result,
        ProductionInvocationSuccess,
    ):
        lines.extend(
            (
                "Result:",
                render_json_value(result.result),
            )
        )

    if isinstance(
        result,
        ProductionInvocationFailure,
    ):
        lines.append(f"Message: {result.message}")

        if result.metadata:
            lines.extend(
                (
                    "Metadata:",
                    render_json_value(result.metadata),
                )
            )

    lines.extend(render_citation_lines(citations, link=link))

    return "\n".join(lines)


def production_invocation_outcome(
    result: ProductionInvocationResult | None,
) -> str:
    """Return the stable outcome label of one production invocation."""

    if result is None:
        return PENDING_OUTCOME

    if isinstance(
        result,
        ProductionInvocationSuccess,
    ):
        return SUCCEEDED_OUTCOME

    return result.error_code.value


def production_invocation_input(
    invocation: ProductionInvocation,
) -> JsonValue:
    """Return the caller-supplied input recorded on one invocation."""

    for event in invocation.initial_context.events:
        if event.event_type == PRODUCTION_INVOCATION_EVENT_TYPE:
            return event.payload.get("input")

    return None


def production_invocation_input_provenance(
    invocation: ProductionInvocation,
) -> JsonValue:
    """Return the input provenance recorded on one invocation, or None (ADR 0112)."""

    for event in invocation.initial_context.events:
        if event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE:
            return dict(event.payload)

    return None


def _render_invocation_summary(
    invocation: ProductionInvocation,
    *,
    result: ProductionInvocationResult | None,
    run_id: UUID | None,
) -> str:
    """Render one aligned production invocation summary line."""

    outcome = production_invocation_outcome(result)

    return (
        f"{invocation.id}  {invocation.created_at.isoformat()}  "
        f"{outcome:<{_OUTCOME_WIDTH}}  "
        f"{run_id if run_id is not None else NO_RUN_MARKER}"
    )
