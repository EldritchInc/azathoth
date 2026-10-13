"""Human-readable production invocation history rendering."""

from collections.abc import Iterable, Mapping
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.rendering._json import render_json_value
from azathoth.workflows import (
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
) -> str:
    """Render the full recorded history of one production invocation."""

    lines = [
        f"Invocation ID: {invocation.id}",
        f"Workflow ID: {invocation.workflow_id}",
        f"Created At: {invocation.created_at.isoformat()}",
        f"Outcome: {production_invocation_outcome(result)}",
        f"Run ID: {run_id if run_id is not None else NO_RUN_MARKER}",
    ]

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
