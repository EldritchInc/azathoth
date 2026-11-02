"""Tests that a retried job resumes its incomplete invocation once nothing runs it (ADR 0105)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from azathoth.jobs import JobResult, JobStatus, run_job
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    RunLease,
    RunLeaseHeldError,
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


class RecordingResumer:
    """Resume as the production service would, recording the result; or find it still held."""

    def __init__(
        self,
        harness: Harness,
        *,
        held: bool = False,
    ) -> None:
        self.harness = harness
        self.held = held
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
