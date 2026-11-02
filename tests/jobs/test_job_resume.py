"""Tests that a retried job resumes its incomplete invocation once nothing runs it (ADR 0105)."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import pytest

from azathoth.jobs import JobResult, JobStatus, run_job
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationResult,
    ProductionInvocationResumeError,
    ProductionInvocationSuccess,
    RunFinishedError,
    RunLease,
    RunLeaseHeldError,
    RunResumeError,
    create_production_invocation,
)
from tests.jobs.test_service import (
    FILE_POLICY,
    KEY,
    WORKFLOW_ID,
    Harness,
    digest_of,
    request_data,
)

Race = Literal["completed", "finished", "finished-and-recorded", "stateless", "mismatched"]
"""How the process still running an invocation got there first, or what else went wrong.

- `completed`: it recorded the result before the resume looked;
- `finished`: it finished the run, and had not yet recorded the result;
- `finished-and-recorded`: it finished the run and recorded the result;
- `stateless`: nothing raced; the invocation cannot be resumed at all;
- `mismatched`: nothing raced; the run's journal does not match.
"""


class RecordingResumer:
    """Resume as the production service would, recording the result; or find it still held."""

    def __init__(
        self,
        harness: Harness,
        *,
        held: bool = False,
        race: Race | None = None,
    ) -> None:
        self.harness = harness
        self.held = held
        self.race = race
        self.calls: list[UUID] = []

    async def __call__(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationResult:
        self.calls.append(invocation_id)

        if self.held:
            now = datetime.now(UTC)

            raise RunLeaseHeldError(
                RunLease(
                    run_id=UUID(int=1),
                    holder="still-running",
                    acquired_at=now,
                    expires_at=now + timedelta(seconds=60),
                )
            )

        result = ProductionInvocationSuccess(invocation_id=invocation_id, result={"resumed": True})

        if self.race in ("completed", "finished-and-recorded"):
            self.harness.repository.save_result(
                ProductionInvocationSuccess(invocation_id=invocation_id, result={"raced": True})
            )

        if self.race == "completed":
            raise ProductionInvocationResumeError.completed(invocation_id)

        if self.race in ("finished", "finished-and-recorded"):
            raise RunFinishedError(UUID(int=2))

        if self.race == "stateless":
            raise ProductionInvocationResumeError(invocation_id, "No state to resume from.")

        if self.race == "mismatched":
            raise RunResumeError(UUID(int=2), "The journal does not match.")

        self.harness.repository.save_result(result)

        return result


def run(
    harness: Harness,
    resumer: RecordingResumer | None,
) -> JobResult:
    """Run the test request with the harness and an optional resumer."""

    return asyncio.run(
        run_job(
            request_data(),
            policy=FILE_POLICY,
            store=harness.store,
            invocation_repository=harness.repository,
            invoke=harness.invoker,
            resume=resumer,
        )
    )


def interrupted(
    harness: Harness,
) -> UUID:
    """Record an invocation under the test key with no result, as an interrupted run leaves."""

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"change": "rename"},
        idempotency=InvocationIdempotency(key=KEY, request_digest=digest_of(request_data())),
    )

    harness.repository.save(invocation)

    return invocation.id


def test_an_incomplete_invocation_nothing_runs_is_resumed_and_reported_as_just_run() -> None:
    harness = Harness()
    invocation_id = interrupted(harness)
    resumer = RecordingResumer(harness)

    result = run(harness, resumer)

    assert resumer.calls == [invocation_id]
    assert harness.invoker.calls == []
    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is False
    assert result.invocation_id == invocation_id


def test_an_incomplete_invocation_still_running_is_reported_incomplete() -> None:
    harness = Harness()
    invocation_id = interrupted(harness)
    resumer = RecordingResumer(harness, held=True)

    result = run(harness, resumer)

    assert resumer.calls == [invocation_id]
    assert result.status is JobStatus.INCOMPLETE
    assert result.replayed is True


def test_without_a_resumer_an_incomplete_invocation_stays_incomplete() -> None:
    harness = Harness()
    interrupted(harness)

    result = run(harness, None)

    assert result.status is JobStatus.INCOMPLETE


def test_a_finished_invocation_is_replayed_and_never_resumed() -> None:
    harness = Harness()
    resumer = RecordingResumer(harness)

    run(harness, resumer)
    result = run(harness, resumer)

    assert resumer.calls == []
    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is True


# Racing the process that still ran it


def test_an_invocation_completed_after_its_key_was_looked_up_is_replayed() -> None:
    harness = Harness()
    invocation_id = interrupted(harness)
    resumer = RecordingResumer(harness, race="completed")

    result = run(harness, resumer)

    assert resumer.calls == [invocation_id]
    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is True
    assert result.result == {"raced": True}
    assert result.invocation_id == invocation_id


def test_a_run_finished_after_its_key_was_looked_up_replays_its_recorded_result() -> None:
    harness = Harness()
    interrupted(harness)

    result = run(harness, RecordingResumer(harness, race="finished-and-recorded"))

    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is True
    assert result.result == {"raced": True}


def test_a_run_finished_whose_result_has_not_landed_yet_is_incomplete() -> None:
    harness = Harness()
    invocation_id = interrupted(harness)

    result = run(harness, RecordingResumer(harness, race="finished"))

    assert result.status is JobStatus.INCOMPLETE
    assert result.replayed is True
    assert result.invocation_id == invocation_id


@pytest.mark.parametrize(
    ("race", "error"),
    [("stateless", ProductionInvocationResumeError), ("mismatched", RunResumeError)],
)
def test_an_invocation_that_cannot_be_resumed_still_says_why(
    race: Race,
    error: type[Exception],
) -> None:
    harness = Harness()
    interrupted(harness)

    with pytest.raises(error):
        run(harness, RecordingResumer(harness, race=race))


def test_a_finished_run_is_a_run_resume_error() -> None:
    error = RunFinishedError(UUID(int=2))

    assert isinstance(error, RunResumeError)
    assert error.run_id == UUID(int=2)
    assert str(error) == f"Run {UUID(int=2)} has already finished."
