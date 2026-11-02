"""Tests for the queue worker's loop: receive, run, settle, extend, drain (ADR 0107)."""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.cli.rendering.jobs import render_job_result
from azathoth.jobs import (
    JobError,
    JobErrorCode,
    JobResult,
    JobStatus,
    incomplete_job_result,
    rejected_job_result,
)
from azathoth.worker import (
    DEFAULT_EXTEND_EVERY_SECONDS,
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    DEFAULT_WAIT_SECONDS,
    MAX_WAIT_SECONDS,
    QueueMessage,
    Settlement,
    Worker,
    WorkerSettings,
    encode_job_result,
)
from tests.worker.queues import MemoryQueue, MemoryResults, results_of

INVOCATION_ID = UUID("e7000000-0000-4000-8000-000000000001")

README = Path(__file__).parents[2] / "src" / "azathoth" / "worker" / "README.md"

FAST = WorkerSettings(
    wait_seconds=0,
    visibility_timeout_seconds=5,
    extend_every_seconds=0.05,
)


def request(
    key: str,
) -> bytes:
    """Return the body of a message carrying one job request under a key."""

    return json.dumps(
        {
            "kind": "invoke",
            "version": 1,
            "idempotency_key": key,
            "workflow_id": "e7000000-0000-4000-8000-000000000010",
            "input": {"value": {}},
        }
    ).encode()


def succeeded(
    key: str,
) -> JobResult:
    """Return a succeeded result under a key."""

    return JobResult(
        idempotency_key=key,
        status=JobStatus.SUCCEEDED,
        invocation_id=INVOCATION_ID,
        result={"answer": 42},
        error=None,
    )


def failed(
    key: str,
) -> JobResult:
    """Return a failed result under a key."""

    return JobResult(
        idempotency_key=key,
        status=JobStatus.FAILED,
        invocation_id=INVOCATION_ID,
        error=JobError(
            code=JobErrorCode.WORKFLOW_EXECUTION_FAILED,
            message="The workflow failed.",
        ),
    )


def rejected() -> JobResult:
    """Return the result of a body that is not a job request."""

    return rejected_job_result(
        JobError(
            code=JobErrorCode.INVALID_REQUEST,
            message="A job request must be JSON: Expecting value at line 1, column 1.",
        ),
        idempotency_key=None,
    )


@dataclass
class Handler:
    """A job handler answering each body with a prepared result.

    It records every body it ran, how many ran at once, and every run that
    was cancelled, as a real run releases its lease when it is.
    """

    answers: dict[bytes, JobResult] = field(default_factory=dict)
    delay: float = 0.0
    error: Exception | None = None
    ran: list[bytes] = field(default_factory=list)
    cancelled: list[bytes] = field(default_factory=list)
    running: int = 0
    most_at_once: int = 0
    started: asyncio.Event = field(default_factory=asyncio.Event)

    async def __call__(
        self,
        body: bytes,
    ) -> JobResult:
        """Run one body, after the delay."""

        self.ran.append(body)
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        self.started.set()

        try:
            await asyncio.sleep(self.delay)

            if self.error is not None:
                raise self.error

            return self.answers[body]
        except asyncio.CancelledError:
            self.cancelled.append(body)
            raise
        finally:
            self.running -= 1


@dataclass
class Harness:
    """A worker over an in-memory queue, with everything it writes captured."""

    queue: MemoryQueue
    handler: Handler
    results: MemoryResults | None
    worker: Worker
    lines: list[str]
    reports: list[str]
    heartbeats: list[int]

    def settled(self) -> list[dict[str, object]]:
        """Return every log line the worker wrote, decoded."""

        return [json.loads(line) for line in self.lines]


def harness(
    handler: Handler,
    *,
    settings: WorkerSettings = FAST,
    with_results: bool = True,
) -> Harness:
    """Build a worker over an empty in-memory queue."""

    queue = MemoryQueue()
    results = MemoryResults(queue) if with_results else None
    lines: list[str] = []
    reports: list[str] = []
    heartbeats: list[int] = []

    worker = Worker(
        queue,
        handler,
        settings=settings,
        results=results,
        log=lines.append,
        report=reports.append,
        heartbeat=lambda: heartbeats.append(len(queue.calls)),
    )

    return Harness(queue, handler, results, worker, lines, reports, heartbeats)


async def run_until(
    worker: Worker,
    done: Callable[[], bool],
    *,
    stop: asyncio.Event | None = None,
    timeout: float = 10.0,
) -> None:
    """Run the worker until a condition holds, then stop it and wait for it."""

    stop = stop if stop is not None else asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while not done():
        if task.done():
            break

        assert loop.time() < deadline, "the worker never reached the condition"
        await asyncio.sleep(0.01)

    stop.set()
    await asyncio.wait_for(task, timeout)


def assert_documented(
    message: str,
    replacements: dict[str, str],
) -> None:
    """Check the worker's README quotes one real message, with placeholders."""

    for value, placeholder in replacements.items():
        message = message.replace(value, placeholder)

    assert f"\n{message}\n" in README.read_text(encoding="utf-8"), message


def settled_line(
    message_id: str,
    key: str | None,
    status: str | None,
    settled: str,
    *,
    invocation: UUID | None = INVOCATION_ID,
) -> dict[str, object]:
    """Return the log line the worker writes for one settled message."""

    return {
        "message_id": message_id,
        "idempotency_key": key,
        "status": status,
        "invocation_id": str(invocation) if invocation is not None else None,
        "settled": settled,
    }


# Settings


def test_the_settings_default_to_a_long_poll_and_two_minutes_extended_every_thirty_seconds() -> (
    None
):
    settings = WorkerSettings()

    assert (DEFAULT_WAIT_SECONDS, DEFAULT_VISIBILITY_TIMEOUT_SECONDS) == (20, 120)
    assert DEFAULT_EXTEND_EVERY_SECONDS == 30
    assert MAX_WAIT_SECONDS == 20
    assert settings.wait_seconds == 20
    assert settings.visibility_timeout_seconds == 120
    assert settings.extend_every_seconds == 30


def test_a_wait_beyond_twenty_seconds_is_refused() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 20"):
        WorkerSettings(wait_seconds=21)


def test_a_visibility_timeout_beyond_twelve_hours_is_refused() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 43200"):
        WorkerSettings(visibility_timeout_seconds=43201)


def test_visibility_must_be_extended_before_it_runs_out() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            r"A worker must extend a message's visibility more often than its "
            r"visibility timeout of 30 seconds\."
        ),
    ):
        WorkerSettings(visibility_timeout_seconds=30, extend_every_seconds=30)


def test_the_readme_quotes_the_real_extension_refusal() -> None:
    with pytest.raises(ValidationError) as raised:
        WorkerSettings(visibility_timeout_seconds=30, extend_every_seconds=30)

    message = str(raised.value.errors()[0]["msg"]).removeprefix("Value error, ")

    assert_documented(message, {"30": "<SECONDS>"})


# Settling


def test_a_succeeded_job_is_sent_to_the_result_queue_then_deleted() -> None:
    async def scenario() -> None:
        body = request("order-1")
        setup = harness(Handler({body: succeeded("order-1")}))
        setup.queue.put("m-1", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-1").deleted)

        assert setup.handler.ran == [body]
        assert setup.results is not None
        assert results_of(setup.results) == [succeeded("order-1")]
        assert setup.results.sent[0][1] == "order-1"
        assert [call for call in setup.queue.calls if call[0] != "receive"] == [
            ("result", "order-1"),
            ("delete", "m-1"),
        ]
        assert setup.settled() == [settled_line("m-1", "order-1", "succeeded", "deleted")]
        assert setup.reports == []

    asyncio.run(scenario())


def test_a_failed_job_is_final_and_deleted() -> None:
    async def scenario() -> None:
        body = request("order-2")
        setup = harness(Handler({body: failed("order-2")}))
        setup.queue.put("m-2", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-2").deleted)

        assert setup.results is not None
        assert results_of(setup.results) == [failed("order-2")]
        assert setup.settled() == [settled_line("m-2", "order-2", "failed", "deleted")]

    asyncio.run(scenario())


def test_a_rejected_body_is_deleted_rather_than_retried() -> None:
    async def scenario() -> None:
        body = b"not json"
        setup = harness(Handler({body: rejected()}))
        setup.queue.put("m-3", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-3").deleted)

        assert setup.results is not None
        assert results_of(setup.results) == [rejected()]
        assert setup.results.sent[0][1] is None
        assert setup.queue.find("m-3").receives == 1
        assert setup.settled() == [
            settled_line("m-3", None, "rejected", "deleted", invocation=None)
        ]

    asyncio.run(scenario())


def test_an_incomplete_job_is_left_for_its_visibility_timeout_to_bring_back() -> None:
    async def scenario() -> None:
        body = request("order-4")
        setup = harness(
            Handler({body: incomplete_job_result(INVOCATION_ID, idempotency_key="order-4")})
        )
        setup.queue.put("m-4", body)

        await run_until(setup.worker, lambda: len(setup.lines) == 1)

        queued = setup.queue.find("m-4")

        assert not queued.deleted
        assert setup.queue.visibility_changes("m-4") == []
        assert setup.results is not None
        assert setup.results.sent == []
        assert setup.settled() == [settled_line("m-4", "order-4", "incomplete", "left")]

    asyncio.run(scenario())


def test_without_a_result_queue_a_final_job_is_only_deleted() -> None:
    async def scenario() -> None:
        body = request("order-5")
        setup = harness(Handler({body: succeeded("order-5")}), with_results=False)
        setup.queue.put("m-5", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-5").deleted)

        assert [call for call in setup.queue.calls if call[0] != "receive"] == [("delete", "m-5")]

    asyncio.run(scenario())


def test_messages_run_one_at_a_time_in_the_order_received() -> None:
    async def scenario() -> None:
        first, second = request("order-6"), request("order-7")
        setup = harness(
            Handler({first: succeeded("order-6"), second: succeeded("order-7")}, delay=0.05)
        )
        setup.queue.put("m-6", first)
        setup.queue.put("m-7", second)

        await run_until(setup.worker, lambda: setup.queue.find("m-7").deleted)

        assert setup.handler.ran == [first, second]
        assert setup.handler.most_at_once == 1

    asyncio.run(scenario())


def test_a_result_is_sent_as_the_line_job_run_prints() -> None:
    for result in (succeeded("order-8"), failed("order-8"), rejected()):
        assert encode_job_result(result) == render_job_result(result)


# Receiving and visibility


def test_every_receive_uses_the_settings_and_follows_a_heartbeat() -> None:
    async def scenario() -> None:
        settings = WorkerSettings(
            wait_seconds=0, visibility_timeout_seconds=7, extend_every_seconds=3
        )
        setup = harness(Handler(), settings=settings)

        await run_until(setup.worker, lambda: len(setup.queue.received) >= 3)

        assert set(setup.queue.received) == {(0, 7)}

        #
        # A heartbeat comes before every receive: each one is recorded when
        # the queue has seen one call fewer than the receive that follows it.
        #
        receives = [index for index, call in enumerate(setup.queue.calls) if call == ("receive",)]

        assert all(index in setup.heartbeats for index in receives)

    asyncio.run(scenario())


def test_visibility_is_extended_while_a_job_runs() -> None:
    async def scenario() -> None:
        body = request("order-9")
        setup = harness(Handler({body: succeeded("order-9")}, delay=0.4))
        setup.queue.put("m-9", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-9").deleted)

        extensions = setup.queue.visibility_changes("m-9")

        assert len(extensions) >= 3
        assert set(extensions) == {5}

        #
        # Every extension is followed by a heartbeat.
        #
        extended_at = [
            index + 1 for index, call in enumerate(setup.queue.calls) if call[0] == "visibility"
        ]

        assert all(index in setup.heartbeats for index in extended_at)

    asyncio.run(scenario())


def test_visibility_is_not_extended_once_the_job_finishes() -> None:
    async def scenario() -> None:
        body = request("order-10")
        setup = harness(Handler({body: succeeded("order-10")}))
        setup.queue.put("m-10", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-10").deleted)
        await asyncio.sleep(0.2)

        assert setup.queue.visibility_changes("m-10") == []

    asyncio.run(scenario())


def test_a_failed_extension_is_reported_and_the_job_still_settles() -> None:
    async def scenario() -> None:
        body = request("order-11")
        setup = harness(Handler({body: succeeded("order-11")}, delay=0.3))
        setup.queue.fail_visibility = True
        setup.queue.put("m-11", body)

        await run_until(setup.worker, lambda: setup.queue.find("m-11").deleted)

        assert setup.reports == [
            "Could not extend the visibility of message m-11: The receipt handle has expired."
        ]
        assert_documented(
            setup.reports[0],
            {"m-11": "<MESSAGE_ID>", "The receipt handle has expired.": "<REASON>"},
        )
        assert setup.queue.visibility_changes("m-11") == [5]
        assert setup.settled() == [settled_line("m-11", "order-11", "succeeded", "deleted")]

    asyncio.run(scenario())


# Draining


def test_a_stop_cancels_the_running_job_and_hands_its_message_back_at_once() -> None:
    async def scenario() -> None:
        body = request("order-12")
        setup = harness(Handler({body: succeeded("order-12")}, delay=30))
        setup.queue.put("m-12", body)
        stop = asyncio.Event()

        await run_until(setup.worker, lambda: setup.handler.started.is_set(), stop=stop)

        queued = setup.queue.find("m-12")

        assert setup.handler.cancelled == [body]
        assert not queued.deleted
        assert setup.queue.visibility_changes("m-12")[-1] == 0
        assert setup.results is not None
        assert setup.results.sent == []
        assert setup.settled() == [
            settled_line("m-12", "order-12", None, "returned", invocation=None)
        ]

    asyncio.run(scenario())


def test_an_extension_already_sent_finishes_before_the_message_is_handed_back() -> None:
    async def scenario() -> None:
        body = request("order-16")
        setup = harness(Handler({body: succeeded("order-16")}, delay=30))
        setup.queue.extension_delay = 0.3
        setup.queue.put("m-16", body)
        stop = asyncio.Event()

        #
        # The first extension is sent 0.05 seconds in and takes 0.3 to
        # arrive, so a stop 0.15 seconds in lands while it is on its way.
        #
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(setup.worker.run(stop))
        await setup.handler.started.wait()
        began = loop.time()

        while loop.time() - began < 0.15:
            await asyncio.sleep(0.01)

        assert setup.queue.visibility_changes("m-16") == []

        stop.set()
        await asyncio.wait_for(task, 10)

        assert setup.queue.visibility_changes("m-16") == [5, 0]

    asyncio.run(scenario())


def test_a_message_received_as_the_stop_arrives_is_handed_back_without_running() -> None:
    async def scenario() -> None:
        body = request("order-13")
        setup = harness(Handler({body: succeeded("order-13")}))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()

        def stop_while_receiving(
            message: QueueMessage,
        ) -> None:
            """Stop the worker while this receive is still returning."""

            loop.call_soon_threadsafe(stop.set)
            time.sleep(0.2)

        setup.queue.on_receive = stop_while_receiving
        setup.queue.put("m-13", body)

        await asyncio.wait_for(setup.worker.run(stop), 10)

        assert setup.handler.ran == []
        assert setup.queue.visibility_changes("m-13") == [0]
        assert setup.settled() == [
            settled_line("m-13", "order-13", None, "returned", invocation=None)
        ]

    asyncio.run(scenario())


def test_a_message_processed_after_the_stop_is_handed_back_without_running() -> None:
    async def scenario() -> None:
        body = request("order-15")
        setup = harness(Handler({body: succeeded("order-15")}))
        stop = asyncio.Event()
        stop.set()
        setup.queue.put("m-15", body)

        (message,) = (queued.message for queued in setup.queue.messages)

        settled = await setup.worker.process(message, stop)

        assert settled.settled is Settlement.RETURNED
        assert setup.handler.ran == []
        assert setup.queue.visibility_changes("m-15") == [0]

    asyncio.run(scenario())


def test_a_stopped_worker_receives_nothing_more() -> None:
    async def scenario() -> None:
        setup = harness(Handler())
        stop = asyncio.Event()
        stop.set()

        await asyncio.wait_for(setup.worker.run(stop), 10)

        assert setup.queue.calls == []

    asyncio.run(scenario())


# Failures of the worker itself


def test_a_job_that_raises_leaves_its_message_and_stops_the_worker() -> None:
    async def scenario() -> None:
        body = request("order-14")
        setup = harness(Handler(error=RuntimeError("The database is unreachable.")))
        setup.queue.put("m-14", body)

        with pytest.raises(RuntimeError, match="The database is unreachable."):
            await asyncio.wait_for(setup.worker.run(asyncio.Event()), 10)

        queued = setup.queue.find("m-14")

        assert not queued.deleted
        assert setup.queue.visibility_changes("m-14") == []
        assert setup.reports == [
            "Message m-14 stays on the queue; running it failed: The database is unreachable."
        ]
        assert_documented(
            setup.reports[0],
            {"m-14": "<MESSAGE_ID>", "The database is unreachable.": "<REASON>"},
        )
        assert setup.settled() == [settled_line("m-14", "order-14", None, "left", invocation=None)]

    asyncio.run(scenario())
