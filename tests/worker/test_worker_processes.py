"""Real worker processes sharing one queue: stopped, killed and resumed (ADR 0105, ADR 0107).

Each worker is a real `azathoth worker run` process over a directory queue
that stands in for SQS, running a job that maps the probe child over a list
(ADR 0106). A worker is stopped as ECS stops it, with SIGTERM, or killed
outright, and another picks its message up. Every probe item tallies each
execution, so an item that ran twice cannot go unnoticed.
"""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.jobs import JobResult, JobStatus
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import journal_resumes
from tests.cli.test_resume_map import parent_run_id, tallies
from tests.examples.test_word_count_benchmark_examples import run_cli
from tests.standard.test_map_workflow import (
    CHILD_WORKFLOW_ID,
    MAP_STEP_ID,
    PARENT_WORKFLOW_ID,
    deploy_probe,
    echoed,
    import_document,
    overlap,
    parent_workflow,
    settings,
)
from tests.worker.directory_queue import DirectoryQueue
from tests.worker.directory_worker import QUEUE_DIRECTORY_VARIABLE

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Workers are stopped with signals, which only POSIX delivers this way.",
)

PROJECT_ROOT = Path(__file__).parents[2]

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-jobs"

RESULTS_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-results"

DEADLINE_SECONDS = 120


@dataclass
class WorkerProcess:
    """One running worker, whose output goes to files."""

    process: subprocess.Popen[bytes]
    stdout: Path
    stderr: Path

    @property
    def pid(self) -> int:
        """Return the worker's process ID."""

        return self.process.pid

    def lines(self) -> list[dict[str, object]]:
        """Return every settled message the worker has logged so far."""

        return [
            json.loads(line)
            for line in self.stdout.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def stop(
        self,
        sent: signal.Signals = signal.SIGTERM,
    ) -> int:
        """Signal the worker, wait for it, and return its exit status."""

        self.process.send_signal(sent)

        return self.process.wait(timeout=60)

    def errors(self) -> str:
        """Return what the worker wrote on stderr."""

        return self.stderr.read_text(encoding="utf-8")


@dataclass
class Deployment:
    """The deployed mapping parent, its database, and the queue workers share."""

    database: Path
    queue: DirectoryQueue
    tmp_path: Path
    workers: list[WorkerProcess]

    def start(
        self,
        *options: str,
    ) -> WorkerProcess:
        """Start one more worker over the queue."""

        name = f"worker-{len(self.workers)}"
        stdout = self.tmp_path / f"{name}.out"
        stderr = self.tmp_path / f"{name}.err"

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.worker.directory_worker",
                "worker",
                "run",
                "--queue-url",
                QUEUE_URL,
                "--result-queue-url",
                RESULTS_URL,
                "--wait-seconds",
                "1",
                *options,
            ],
            cwd=self.tmp_path,
            stdout=stdout.open("wb"),
            stderr=stderr.open("wb"),
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [str(PROJECT_ROOT), os.environ.get("PYTHONPATH")])
                ),
                QUEUE_DIRECTORY_VARIABLE: str(self.queue.root),
            },
        )

        worker = WorkerProcess(process, stdout, stderr)
        self.workers.append(worker)

        return worker

    def finished_items(self) -> int:
        """Return how many of the map's items have their result."""

        repositories = open_repositories(self.database)

        return sum(
            1
            for invocation in repositories.invocations.invocations_for_workflow(
                UUID(CHILD_WORKFLOW_ID)
            )
            if repositories.invocations.result(invocation.id) is not None
        )


@pytest.fixture
def deployment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Iterator[Deployment]:
    """Deploy a parent mapping the probe two at a time, and an empty queue."""

    database = deploy_probe(monkeypatch, tmp_path, capsys)

    import_document(capsys, tmp_path, "workflow", parent_workflow(settings(max_concurrency=2)))
    run_cli(capsys, "workflow", "promote", PARENT_WORKFLOW_ID)

    deployed = Deployment(database, DirectoryQueue(tmp_path / "queue"), tmp_path, [])

    yield deployed

    for worker in deployed.workers:
        if worker.process.poll() is None:
            worker.process.kill()
            worker.process.wait()


def body(
    key: str,
    items: list[dict[str, object]],
) -> bytes:
    """Return a message carrying a job request that maps the probe over the items."""

    return json.dumps(
        {
            "kind": "invoke",
            "version": 1,
            "idempotency_key": key,
            "workflow_id": PARENT_WORKFLOW_ID,
            "input": {"value": items},
        }
    ).encode()


def wait_until(
    condition: Callable[[], bool],
    *workers: WorkerProcess,
    what: str,
) -> None:
    """Wait for a condition, failing at once if a worker exits first."""

    deadline = time.monotonic() + DEADLINE_SECONDS

    while not condition():
        for worker in workers:
            assert worker.process.poll() is None, (what, worker.errors())

        assert time.monotonic() < deadline, f"never: {what}"
        time.sleep(0.05)


def results(
    queue: DirectoryQueue,
) -> list[JobResult]:
    """Return every result the workers sent, in order."""

    return [JobResult.model_validate_json(sent) for sent, _ in queue.results()]


def assert_every_item_ran_once(
    deployment: Deployment,
    run_id: UUID,
    count: int,
) -> None:
    """Check the map's children: one invocation and one run per item, under its key."""

    repositories = open_repositories(deployment.database)
    invocations = repositories.invocations.invocations_for_workflow(UUID(CHILD_WORKFLOW_ID))

    assert sorted(
        invocation.idempotency.key for invocation in invocations if invocation.idempotency
    ) == sorted(f"azathoth:{run_id}:{MAP_STEP_ID}:1:{index}" for index in range(count))
    assert len(invocations) == count
    assert len(repositories.runs.runs_for_workflow(UUID(CHILD_WORKFLOW_ID))) == count
    assert len(repositories.run_children.children_of(run_id)) == count
    assert journal_resumes(repositories.run_journal.entries(run_id)) == 1


def mapped(
    count: int,
) -> object:
    """Return the job result of a map over `count` probe items valued by their index."""

    return {"result": echoed(*range(count))}


def test_a_worker_runs_a_request_and_replays_it_when_it_comes_again(
    deployment: Deployment,
) -> None:
    items: list[dict[str, object]] = [{"value": index} for index in range(2)]
    deployment.queue.put("m-1", body("order-1", items))

    worker = deployment.start()

    wait_until(lambda: deployment.queue.deleted() == ["m-1"], worker, what="m-1 deleted")

    deployment.queue.put("m-2", body("order-1", items))

    wait_until(lambda: len(deployment.queue.deleted()) == 2, worker, what="m-2 deleted")

    assert worker.stop() == 0
    assert worker.errors() == "Stopping.\nStopped.\n"

    first, second = results(deployment.queue)

    assert first.status is JobStatus.SUCCEEDED
    assert first.result == mapped(2)
    assert (first.replayed, second.replayed) == (False, True)
    assert first.invocation_id == second.invocation_id
    assert [line["settled"] for line in worker.lines()] == ["deleted", "deleted"]
    assert deployment.finished_items() == 2


def test_a_worker_stopped_with_sigterm_hands_its_job_to_the_next_worker(
    deployment: Deployment,
    tmp_path: Path,
) -> None:
    tally = tmp_path / "tally"
    probe = tmp_path / "probe"
    tally.mkdir()
    probe.mkdir()

    items: list[dict[str, object]] = [
        {"value": index, "sleep": 1.0, "tally": str(tally), "probe": str(probe)}
        for index in range(6)
    ]
    deployment.queue.put("m-1", body("order-2", items))

    first = deployment.start()

    wait_until(lambda: deployment.finished_items() >= 2, first, what="two items finished")

    assert first.stop() == 0
    assert first.errors() == "Stopping.\nStopped.\n"
    assert [line["settled"] for line in first.lines()] == ["returned"]

    #
    # The stopped worker released its run, and its message is visible at
    # once, without waiting out its two minutes.
    #
    run_id = parent_run_id(deployment.database)

    assert open_repositories(deployment.database).run_leases.get(run_id) is None
    assert deployment.queue.is_visible("m-1")
    assert deployment.queue.deleted() == []
    assert deployment.finished_items() < 6

    second = deployment.start()

    wait_until(lambda: deployment.queue.deleted() == ["m-1"], second, what="m-1 deleted")

    assert second.stop() == 0

    (result,) = results(deployment.queue)

    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is False
    assert result.result == mapped(6)
    assert [line["settled"] for line in second.lines()] == ["deleted"]
    assert [pid for _, pid in deployment.queue.receives()] == [first.pid, second.pid]
    assert tallies(tally, 6) == [1] * 6
    assert_every_item_ran_once(deployment, run_id, 6)

    #
    # The children the stopped worker left running, and the ones the next
    # worker started, never ran more than two at a time.
    #
    assert overlap(probe, 6) <= 2


def test_a_killed_workers_message_comes_back_and_resumes_once_its_lease_lapses(
    deployment: Deployment,
    tmp_path: Path,
) -> None:
    tally = tmp_path / "tally"
    tally.mkdir()

    items: list[dict[str, object]] = [
        {"value": index, "sleep": 2.0, "tally": str(tally)} for index in range(4)
    ]
    deployment.queue.put("m-1", body("order-3", items))

    fast = ("--visibility-timeout-seconds", "3", "--extend-every-seconds", "1")
    first = deployment.start(*fast)

    wait_until(lambda: deployment.finished_items() >= 1, first, what="an item finished")

    assert first.stop(signal.SIGKILL) == -signal.SIGKILL

    run_id = parent_run_id(deployment.database)

    #
    # The killed worker's message comes back once its last extension runs
    # out, but its run's lease is still live: the next worker leaves it.
    #
    second = deployment.start(*fast)

    wait_until(
        lambda: any(line["settled"] == "left" for line in second.lines()),
        second,
        what="the message left while its lease is live",
    )

    (left, *_) = second.lines()

    assert left["status"] == "incomplete"
    assert deployment.queue.deleted() == []

    #
    # Mark the lease lapsed, as waiting out its minute would. The message
    # comes back again, and is resumed this time.
    #
    with open_repositories(deployment.database).database.transaction() as session:
        session.execute(
            "UPDATE run_leases SET expires_at = ? WHERE run_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), str(run_id)),
        )

    wait_until(lambda: deployment.queue.deleted() == ["m-1"], second, what="m-1 deleted")

    assert second.stop() == 0

    (result,) = (result for result in results(deployment.queue))

    assert result.status is JobStatus.SUCCEEDED
    assert result.result == mapped(4)
    assert second.lines()[-1]["settled"] == "deleted"
    assert {line["settled"] for line in second.lines()[:-1]} == {"left"}
    assert tallies(tally, 4) == [1] * 4
    assert_every_item_ran_once(deployment, run_id, 4)


def test_workers_sharing_a_queue_each_take_a_message_once(
    deployment: Deployment,
) -> None:
    for index in range(4):
        deployment.queue.put(
            f"m-{index}",
            body(f"order-4-{index}", [{"value": 0, "sleep": 0.5}]),
        )

    workers = [deployment.start(), deployment.start()]

    wait_until(lambda: len(deployment.queue.deleted()) == 4, *workers, what="every message deleted")

    assert [worker.stop() for worker in workers] == [0, 0]

    received = [message_id for message_id, _ in deployment.queue.receives()]

    assert sorted(received) == [f"m-{index}" for index in range(4)]
    settled = [str(line["message_id"]) for worker in workers for line in worker.lines()]

    assert sorted(settled) == sorted(received)
    assert {result.status for result in results(deployment.queue)} == {JobStatus.SUCCEEDED}
    assert (
        len(
            open_repositories(deployment.database).invocations.invocations_for_workflow(
                UUID(PARENT_WORKFLOW_ID)
            )
        )
        == 4
    )
