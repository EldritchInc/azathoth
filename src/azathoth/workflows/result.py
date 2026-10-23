"""Resolution of the declared result of one workflow run."""

from collections.abc import Sequence

from pydantic import JsonValue

from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.references import (
    WorkflowOutputDeclaringStep,
    reference_producer_step_ids,
    resolve_named_value,
)
from azathoth.workflows.value import (
    WorkflowResultReference,
    WorkflowValueReference,
)


class WorkflowResultError(ValueError):
    """Raised when a run did not produce its declared result exactly once."""


def workflow_result(
    run: WorkflowRun,
    reference: WorkflowResultReference,
    *,
    steps: Sequence[WorkflowOutputDeclaringStep],
) -> JsonValue:
    """Return the declared result value produced by one workflow run.

    The steps are the workflow's steps in step order. A name-only reference
    resolves to the first of them, declaring the name, that produced it.

    Raises:
        WorkflowResultError: The run produced the referenced value zero times,
            for example because a condition skipped its producer step, or an
            explicitly referenced producer produced it more than once.
    """

    if not isinstance(
        reference,
        WorkflowValueReference,
    ):
        value = resolve_named_value(
            reference.name,
            producer_step_ids=reference_producer_step_ids(
                reference,
                steps,
            ),
            values=run.values,
        )

        if value is None:
            raise WorkflowResultError(
                f"Workflow result {reference.name!r} was not produced by any workflow step."
            )

        return value.value

    matches = tuple(
        value
        for value in run.values_from(reference.producer_step_id)
        if value.name == reference.name
    )

    if not matches:
        raise WorkflowResultError(
            f"Workflow result {reference.name!r} from step "
            f"{reference.producer_step_id} was not produced."
        )

    if len(matches) > 1:
        raise WorkflowResultError(
            f"Workflow result {reference.name!r} from step "
            f"{reference.producer_step_id} was produced more than once."
        )

    return matches[0].value


def workflow_result_produced(
    run: WorkflowRun,
    reference: WorkflowResultReference,
    *,
    steps: Sequence[WorkflowOutputDeclaringStep],
) -> bool:
    """Return whether any candidate producer of the declared result produced it.

    The steps are the workflow's steps in step order.
    """

    producer_step_ids = set(
        reference_producer_step_ids(
            reference,
            steps,
        )
    )

    return any(
        value.name == reference.name and value.producer_step_id in producer_step_ids
        for value in run.values
    )
