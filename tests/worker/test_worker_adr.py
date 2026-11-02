"""Tests that ADR 0107 states the worker as it really behaves."""

import asyncio
import re
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli.worker import STOPPED_MESSAGE, STOPPING_MESSAGE, WORKER_INPUT_POLICY
from azathoth.inputs import InputResolutionError, ReferenceInput, SQLiteContentStore, resolve_input
from azathoth.jobs import JobError, JobErrorCode, JobResult, JobStatus, incomplete_job_result
from azathoth.telemetry.conventions import WORKER_MESSAGE_ID
from azathoth.worker import (
    DEFAULT_EXTEND_EVERY_SECONDS,
    DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    MAX_WAIT_SECONDS,
    QueueMessage,
    SettledMessage,
    Settlement,
    Worker,
    WorkerSettings,
)
from tests.worker.queues import MemoryQueue

ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0107-run-jobs-from-a-queue.md"

INVOCATION_ID = UUID("e7000000-0000-4000-8000-000000000002")


def text() -> str:
    """Return the ADR."""

    return ADR.read_text(encoding="utf-8")


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(text().split())


def settlement_table() -> dict[str, str]:
    """Return what the ADR's table says happens to a message, by its job's status."""

    decision = text()[text().index("### Settling a message") : text().index("### Visibility")]

    return dict(re.findall(r"^\| `([a-z]+)` \| (.+) \|$", decision, re.MULTILINE))


def result_of(
    status: JobStatus,
) -> JobResult:
    """Return a job result with one status."""

    if status is JobStatus.SUCCEEDED:
        return JobResult(
            idempotency_key="k",
            status=status,
            invocation_id=INVOCATION_ID,
            result={},
            error=None,
        )

    if status is JobStatus.FAILED:
        return JobResult(
            idempotency_key="k",
            status=status,
            invocation_id=INVOCATION_ID,
            error=JobError(code=JobErrorCode.WORKFLOW_EXECUTION_FAILED, message="Failed."),
        )

    if status is JobStatus.REJECTED:
        return JobResult(
            idempotency_key="k",
            status=status,
            invocation_id=None,
            error=JobError(code=JobErrorCode.INVALID_REQUEST, message="Not a request."),
        )

    return incomplete_job_result(INVOCATION_ID, idempotency_key="k")


def settle(
    status: JobStatus,
) -> Settlement:
    """Run one message whose job ends with a status, and return how it was settled."""

    async def handle(
        message: QueueMessage,
    ) -> JobResult:
        return result_of(status)

    queue = MemoryQueue()
    queue.put("m-1", b"{}")
    (message,) = (queued.message for queued in queue.messages)
    worker = Worker(queue, handle, log=lambda line: None, report=lambda line: None)

    return asyncio.run(worker.process(message, asyncio.Event())).settled


def test_the_settlement_table_covers_every_status() -> None:
    assert sorted(settlement_table()) == sorted(status.value for status in JobStatus)


@pytest.mark.parametrize("status", list(JobStatus), ids=lambda status: status.value)
def test_the_settlement_table_says_what_the_worker_does(
    status: JobStatus,
) -> None:
    documented = settlement_table()[status.value]
    expected = Settlement.DELETED if documented.endswith("then deleted.") else Settlement.LEFT

    assert documented.endswith("then deleted.") or documented.startswith("Left,")
    assert settle(status) is expected


def test_the_adr_states_the_shipped_defaults() -> None:
    settings = WorkerSettings()

    assert settings.visibility_timeout_seconds == DEFAULT_VISIBILITY_TIMEOUT_SECONDS
    assert f"`--visibility-timeout-seconds`, {DEFAULT_VISIBILITY_TIMEOUT_SECONDS} by" in prose()
    assert f"`--extend-every-seconds`, {DEFAULT_EXTEND_EVERY_SECONDS:g}," in prose()
    assert f"`--max-age-seconds`, {DEFAULT_MAX_HEARTBEAT_AGE_SECONDS} by default" in prose()
    assert f"one receive wait, {MAX_WAIT_SECONDS} seconds" in prose()


def test_the_adr_names_the_real_stop_messages_and_attribute() -> None:
    assert f"prints `{STOPPING_MESSAGE}`" in prose()
    assert f"prints `{STOPPED_MESSAGE}`" in prose()
    assert f"`{WORKER_MESSAGE_ID}`" in prose()


def test_the_adr_quotes_the_real_reference_refusal(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri="file:///etc/hostname", media_type="text/plain"),
            policy=WORKER_INPUT_POLICY,
            store=SQLiteContentStore(tmp_path / "azathoth.db"),
        )

    assert f"```text\n{raised.value}\n```" in text()


def test_the_adrs_log_line_is_a_settled_message() -> None:
    (line,) = (line for line in text().splitlines() if line.startswith('{"message_id": '))

    assert SettledMessage.model_validate_json(line).settled is Settlement.DELETED
