"""Resolution of the declared result of one workflow run."""

from pydantic import JsonValue

from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.value import WorkflowValueReference


class WorkflowResultError(ValueError):
    """Raised when a run did not produce its declared result exactly once."""


def workflow_result(
    run: WorkflowRun,
    reference: WorkflowValueReference,
) -> JsonValue:
    """Return the declared result value produced by one workflow run.

    Raises:
        WorkflowResultError: The run produced the referenced value zero times,
            for example because a condition skipped its producer step, or more
            than once.
    """

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
