"""How often a run was resumed, how to resume one that never finished, and its children.

See ADR 0105.
"""

from collections.abc import Sequence
from uuid import UUID

from azathoth.workflows import RunChild, RunJournalEntry, WorkflowRun


def render_resume_lines(
    resumes: int,
) -> tuple[str, ...]:
    """Return the line naming how often a run was resumed, or none for a run never resumed."""

    if resumes <= 0:
        return ()

    return (f"Resumed: {resumes} time{'' if resumes == 1 else 's'}",)


def render_unfinished_run(
    run_id: UUID,
    entries: Sequence[RunJournalEntry],
) -> str:
    """Return what `run show` says of a run that journaled but never finished."""

    invocation_id = entries[0].invocation_id if entries else None

    if invocation_id is not None:
        return (
            f"Run {run_id} has not finished; resume it with "
            f"azathoth invocation resume {invocation_id}."
        )

    return f"Run {run_id} has not finished; resume it with azathoth run resume {run_id}."


CHILD_STATUS_UNFINISHED = "unfinished"
"""The status of a child run that started but is not recorded as finished."""


def render_child_count_lines(
    children: int,
) -> tuple[str, ...]:
    """Return the line naming how many children a run started, or none for a run with none."""

    if children <= 0:
        return ()

    return (f"Children: {children}",)


def render_run_children(
    run_id: UUID,
    children: Sequence[tuple[RunChild, WorkflowRun | None]],
) -> str:
    """Render the runs a run's steps started, oldest first, with each one's status.

    A child not recorded as finished is `unfinished`.
    """

    if not children:
        return f"Run {run_id} started no children."

    blocks = []

    for child, run in children:
        if run is None:
            status = CHILD_STATUS_UNFINISHED
        else:
            status = "succeeded" if run.succeeded else "failed"

        invocation = (
            "no invocation" if child.child_invocation_id is None else str(child.child_invocation_id)
        )

        blocks.append(
            "\n".join(
                (
                    f"Child Run ID: {child.child_run_id}",
                    f"Workflow ID: {child.child_workflow_id}",
                    f"Invocation ID: {invocation}",
                    f"Parent Step ID: {child.parent_step_id} (attempt {child.parent_attempt})",
                    f"Status: {status}",
                )
            )
        )

    return "\n\n".join(blocks)


__all__ = [
    "CHILD_STATUS_UNFINISHED",
    "render_child_count_lines",
    "render_run_children",
    "render_resume_lines",
    "render_unfinished_run",
]
