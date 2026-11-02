"""How often a run was resumed, and how to resume one that never finished (ADR 0105)."""

from collections.abc import Sequence
from uuid import UUID

from azathoth.workflows import RunJournalEntry


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


__all__ = [
    "render_resume_lines",
    "render_unfinished_run",
]
