"""A person's judgment of a kept run, through the service API (ADRs 0068 and 0129).

A judgment is immutable: judging a run again records a new one, and the
newest is the run's disposition. A bad judgment needs a reason, and a
corrected output contradicts a good one, so it is accepted only with bad,
as `azathoth run feedback` decides.
"""

from collections.abc import Iterable
from typing import Final
from uuid import UUID

from pydantic import JsonValue, ValidationError

from azathoth.api.errors import InvalidArgumentError, NotFoundError
from azathoth.api.models import FeedbackDisposition, RunFeedback
from azathoth.persistence.repositories import Repositories
from azathoth.workflows import WorkflowRunFeedback, WorkflowRunFeedbackDisposition

CORRECTED_OUTPUT_MESSAGE: Final = "A corrected output can only accompany bad feedback."
"""Why a good judgment with a corrected output is refused."""

DISPOSITIONS: Final = tuple(disposition.value for disposition in WorkflowRunFeedbackDisposition)
"""Every disposition a judgment may have, as the API names them."""


def record_feedback(
    repositories: Repositories,
    run_id: UUID,
    disposition: str,
    *,
    reason: str | None,
    corrected_output: JsonValue,
) -> RunFeedback:
    """Record one judgment of a kept run, and return it.

    Nothing is saved when any check fails.

    Raises:
        InvalidArgumentError: The disposition is neither good nor bad, a bad
            judgment has no reason, or a good one has a corrected output.
        NotFoundError: No kept run has this ID.
    """

    if disposition not in DISPOSITIONS:
        raise InvalidArgumentError(f"disposition must be good or bad, not {disposition!r}.")

    _kept(repositories, run_id)

    judged = WorkflowRunFeedbackDisposition(disposition)

    if judged is WorkflowRunFeedbackDisposition.GOOD and corrected_output is not None:
        raise InvalidArgumentError(CORRECTED_OUTPUT_MESSAGE)

    stripped = reason.strip() if reason is not None else None

    try:
        feedback = WorkflowRunFeedback(
            run_id=run_id,
            disposition=judged,
            reason=stripped or None,
            corrected_output=corrected_output,
        )
    except ValidationError as exc:
        raise InvalidArgumentError(
            " ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())
        ) from None

    repositories.feedback.save(feedback)

    return _view(feedback)


def run_feedback(
    repositories: Repositories,
    run_id: UUID,
) -> tuple[RunFeedback, ...]:
    """Return every judgment of a kept run, newest first; of two at once, the later recorded.

    Raises:
        NotFoundError: No kept run has this ID.
    """

    _kept(repositories, run_id)

    records = repositories.feedback.feedback_for_run(run_id)

    return tuple(_view(feedback) for feedback in _newest_first(records))


def latest_dispositions(
    records: Iterable[WorkflowRunFeedback],
) -> dict[UUID, FeedbackDisposition]:
    """Return each judged run's latest disposition, as `azathoth run list` shows it."""

    latest: dict[UUID, WorkflowRunFeedback] = {}

    for record in records:
        current = latest.get(record.run_id)

        if current is None or record.created_at >= current.created_at:
            latest[record.run_id] = record

    return {run_id: _disposition(record) for run_id, record in latest.items()}


def _newest_first(
    records: tuple[WorkflowRunFeedback, ...],
) -> list[WorkflowRunFeedback]:
    """Return judgments newest first, a later-recorded one first of two made at once."""

    return sorted(reversed(records), key=lambda record: record.created_at, reverse=True)


def _kept(
    repositories: Repositories,
    run_id: UUID,
) -> None:
    """Refuse a run that was never kept.

    Raises:
        NotFoundError: No kept run has this ID.
    """

    if repositories.runs.get(run_id) is None:
        raise NotFoundError(f"Run {run_id} was not found.")


def _disposition(
    feedback: WorkflowRunFeedback,
) -> FeedbackDisposition:
    """Return a judgment's disposition, as the API names it."""

    return "good" if feedback.disposition is WorkflowRunFeedbackDisposition.GOOD else "bad"


def _view(
    feedback: WorkflowRunFeedback,
) -> RunFeedback:
    """Return the API's view of one judgment."""

    return RunFeedback(
        feedback_id=feedback.id,
        run_id=feedback.run_id,
        disposition=_disposition(feedback),
        reason=feedback.reason,
        corrected_output=feedback.corrected_output,
        created_at=feedback.created_at,
        command=f"azathoth run show {feedback.run_id}",
    )


__all__ = [
    "CORRECTED_OUTPUT_MESSAGE",
    "DISPOSITIONS",
    "latest_dispositions",
    "record_feedback",
    "run_feedback",
]
