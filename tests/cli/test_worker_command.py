"""Tests for `azathoth worker run` and `azathoth worker health` (ADR 0107).

The worker runs for real against a deployed workflow in SQLite, over an
in-memory queue. It is stopped as ECS stops it, with a signal, so these tests
run only where POSIX delivers signals this way.
"""

import json
import os
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import azathoth.cli.application as application
import azathoth.cli.bootstrap as cli_bootstrap
import azathoth.cli.tracing as cli_tracing
import azathoth.cli.worker as cli_worker
from azathoth.cli import build_parser, main
from azathoth.cli.rendering import render_job_result
from azathoth.cli.worker import WORKER_INPUT_POLICY, settings_problems
from azathoth.jobs import JobErrorCode, JobStatus
from azathoth.runtime import AzathothRuntime
from azathoth.telemetry import ATTRIBUTE_KEYS
from azathoth.worker import (
    MISSING_WORKER_EXTRA_MESSAGE,
    QueueError,
    QueueMessage,
    WorkerSettings,
)
from tests.cli.test_job_commands import KEY, Environment, request_data
from tests.telemetry.fakes import RecordingTelemetry
from tests.worker.queues import MemoryQueue, MemoryResults, results_of

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-jobs"

RESULTS_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-results"

FAST = (
    "--wait-seconds",
    "0",
    "--visibility-timeout-seconds",
    "60",
)

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The worker is stopped with signals, which only POSIX delivers this way.",
)


@dataclass
class SignallingQueue(MemoryQueue):
    """An in-memory queue that signals the worker once it is done.

    Once `done()` holds, an empty receive sends each of `signals` to this
    process, a moment apart, as ECS stops a task.
    """

    done: Callable[[], bool] = lambda: True
    signals: tuple[signal.Signals, ...] = (signal.SIGTERM,)
    sent: list[signal.Signals] = field(default_factory=list)

    def receive(
        self,
        *,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Receive as the in-memory queue does, then signal when done."""

        message = super().receive(
            wait_seconds=wait_seconds,
            visibility_timeout_seconds=visibility_timeout_seconds,
        )

        if message is None and not self.sent and self.done():
            for sent in self.signals:
                self.sent.append(sent)
                os.kill(os.getpid(), sent)
                time.sleep(0.1)

        return message


@dataclass
class Deployment:
    """A deployed workflow, the worker's queues, and how often the runtime loaded."""

    environment: Environment
    queue: SignallingQueue
    results: MemoryResults
    opened: list[str]
    runtime_loads: list[int]


@pytest.fixture
def deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Deployment:
    """Deploy the job workflow, and give the worker in-memory queues."""

    environment = Environment(tmp_path, monkeypatch)
    queue = SignallingQueue()
    results = MemoryResults(queue)
    opened: list[str] = []
    loads: list[int] = []

    def open_job_queue(
        url: str,
    ) -> SignallingQueue:
        opened.append(url)

        return queue

    def open_result_queue(
        url: str,
    ) -> MemoryResults:
        opened.append(url)

        return results

    real_load_runtime = cli_bootstrap.load_runtime

    def counted_load_runtime(
        configuration: Any,
    ) -> AzathothRuntime:
        loads.append(1)

        return real_load_runtime(configuration)

    monkeypatch.setattr(cli_worker, "open_job_queue", open_job_queue)
    monkeypatch.setattr(cli_worker, "open_result_queue", open_result_queue)
    monkeypatch.setattr(cli_worker, "load_runtime", counted_load_runtime)

    return Deployment(environment, queue, results, opened, loads)


def body(
    **changes: Any,
) -> bytes:
    """Return a message body carrying the job request, with changes."""

    return json.dumps(request_data(**changes)).encode()


def serve(
    capsys: pytest.CaptureFixture[str],
    *options: str,
) -> tuple[int, list[dict[str, object]], str]:
    """Run the worker until its queue signals it; return status, log lines and stderr."""

    status = main(("worker", "run", "--queue-url", QUEUE_URL, *FAST, *options))
    captured = capsys.readouterr()

    return status, [json.loads(line) for line in captured.out.splitlines()], captured.err


# Parsing and dispatch


def test_worker_run_requires_a_queue_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(("worker", "run"))

    assert raised.value.code == 2
    assert "--queue-url" in capsys.readouterr().err


def test_worker_run_defaults_to_a_long_poll_and_two_minutes_of_visibility() -> None:
    arguments = build_parser().parse_args(("worker", "run", "--queue-url", QUEUE_URL))

    assert arguments.worker_action == "run"
    assert arguments.worker_queue_url == QUEUE_URL
    assert arguments.worker_result_queue_url is None
    assert arguments.worker_wait_seconds == 20
    assert arguments.worker_visibility_timeout_seconds == 120
    assert arguments.worker_extend_every_seconds == 30
    assert arguments.worker_heartbeat_file is None


def test_worker_health_defaults_to_ninety_seconds() -> None:
    arguments = build_parser().parse_args(
        ("worker", "health", "--heartbeat-file", "/tmp/azathoth-heartbeat")
    )

    assert arguments.worker_action == "health"
    assert arguments.worker_heartbeat_file == Path("/tmp/azathoth-heartbeat")
    assert arguments.worker_max_age_seconds == 90


def test_the_cli_dispatches_worker_run_with_every_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run_worker(
        *arguments: object,
        **options: object,
    ) -> int:
        calls.append((arguments, options))

        return 71

    monkeypatch.setattr(application, "run_worker", fake_run_worker)

    status = main(
        (
            "worker",
            "run",
            "--queue-url",
            QUEUE_URL,
            "--result-queue-url",
            RESULTS_URL,
            "--wait-seconds",
            "5",
            "--visibility-timeout-seconds",
            "300",
            "--extend-every-seconds",
            "45",
            "--heartbeat-file",
            "/tmp/azathoth-heartbeat",
        )
    )

    assert status == 71
    assert calls == [
        (
            (QUEUE_URL,),
            {
                "result_queue_url": RESULTS_URL,
                "wait_seconds": 5,
                "visibility_timeout_seconds": 300,
                "extend_every_seconds": 45.0,
                "heartbeat_file": Path("/tmp/azathoth-heartbeat"),
            },
        )
    ]


def test_the_cli_dispatches_worker_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, float]] = []

    def fake_check(
        heartbeat_file: Path,
        *,
        max_age_seconds: float,
    ) -> int:
        calls.append((heartbeat_file, max_age_seconds))

        return 1

    monkeypatch.setattr(application, "check_worker_health", fake_check)

    assert main(("worker", "health", "--heartbeat-file", "beat", "--max-age-seconds", "15")) == 1
    assert calls == [(Path("beat"), 15.0)]


def test_cli_help_lists_the_worker_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    assert raised.value.code == 0
    assert ",init,job,worker}" in capsys.readouterr().out


def test_worker_without_an_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(("worker",)) == 0
    assert "usage: azathoth" in capsys.readouterr().out


# Settings


def test_settings_that_are_not_valid_name_their_options_before_anything_opens(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        (
            "worker",
            "run",
            "--queue-url",
            QUEUE_URL,
            "--wait-seconds",
            "21",
            "--extend-every-seconds",
            "0",
        )
    )
    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == (
        "--wait-seconds: Input should be less than or equal to 20.\n"
        "--extend-every-seconds: Input should be greater than 0.\n"
    )
    assert deployment.opened == []


def test_visibility_extended_too_rarely_is_refused_in_the_models_own_words() -> None:
    with pytest.raises(ValidationError) as raised:
        WorkerSettings(visibility_timeout_seconds=30, extend_every_seconds=30)

    assert settings_problems(raised.value) == (
        "A worker must extend a message's visibility more often than its "
        "visibility timeout of 30 seconds.",
    )


# Serving


@posix_only
def test_a_request_from_the_queue_runs_and_its_result_settles_the_message(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment.queue.put("m-1", body())
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, lines, err = serve(capsys, "--result-queue-url", RESULTS_URL)

    (result,) = results_of(deployment.results)
    (invocation,) = deployment.environment.invocations()

    assert (status, err) == (0, "Stopping.\nStopped.\n")
    assert deployment.opened == [QUEUE_URL, RESULTS_URL]
    assert result.status is JobStatus.SUCCEEDED
    assert result.idempotency_key == KEY
    assert result.result == {"verdict": "approve"}
    assert result.invocation_id == invocation.id
    assert deployment.results.sent == [(render_job_result(result), KEY)]
    assert lines == [
        {
            "message_id": "m-1",
            "idempotency_key": KEY,
            "status": "succeeded",
            "invocation_id": str(invocation.id),
            "settled": "deleted",
        }
    ]


@posix_only
def test_a_redelivered_request_replays_without_running_again(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment.queue.put("m-1", body())
    deployment.queue.put("m-2", body())
    deployment.queue.done = lambda: deployment.queue.find("m-2").deleted

    status, lines, _ = serve(capsys, "--result-queue-url", RESULTS_URL)

    first, second = results_of(deployment.results)

    assert status == 0
    assert (first.replayed, second.replayed) == (False, True)
    assert first.invocation_id == second.invocation_id
    assert len(deployment.environment.invocations()) == 1
    assert deployment.runtime_loads == [1]
    assert [line["settled"] for line in lines] == ["deleted", "deleted"]


@posix_only
def test_a_body_that_is_not_a_request_is_rejected_and_deleted(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment.queue.put("m-1", b"not json")
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, lines, _ = serve(capsys, "--result-queue-url", RESULTS_URL)

    (result,) = results_of(deployment.results)

    assert status == 0
    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_REQUEST
    assert deployment.environment.invocations() == ()
    assert deployment.runtime_loads == []
    assert lines[0]["settled"] == "deleted"


@posix_only
@pytest.mark.parametrize(
    "uri",
    ["file:///etc/hostname", "s3://azathoth-inputs/request.json"],
)
def test_the_worker_accepts_no_references(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
    uri: str,
) -> None:
    scheme = uri.split(":", 1)[0]
    deployment.queue.put("m-1", body(input={"uri": uri, "media_type": "application/json"}))
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, _, _ = serve(capsys, "--result-queue-url", RESULTS_URL)

    (result,) = results_of(deployment.results)

    assert status == 0
    assert WORKER_INPUT_POLICY.accepted_schemes == ()
    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert result.error.message == (
        f"Input {uri} uses the {scheme!r} scheme, which is not accepted here; "
        "no schemes are accepted."
    )
    assert deployment.environment.invocations() == ()


@posix_only
def test_without_a_result_queue_only_the_job_queue_is_opened(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment.queue.put("m-1", body())
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, _, _ = serve(capsys)

    assert status == 0
    assert deployment.opened == [QUEUE_URL]
    assert deployment.results.sent == []


@posix_only
@pytest.mark.parametrize(
    ("sent", "status", "message"),
    [
        (signal.SIGTERM, 143, "Terminated."),
        (signal.SIGINT, 130, "Interrupted."),
    ],
)
def test_a_second_signal_stops_the_worker_where_it_is(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
    sent: signal.Signals,
    status: int,
    message: str,
) -> None:
    deployment.queue.signals = (sent, sent)

    assert serve(capsys) == (status, [], f"Stopping.\n{message}\n")


@posix_only
def test_sigint_drains_as_sigterm_does(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment.queue.signals = (signal.SIGINT,)

    assert serve(capsys) == (0, [], "Stopping.\nStopped.\n")


@posix_only
def test_the_handlers_in_place_before_are_restored(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def custom(
        signum: int,
        frame: object,
    ) -> None:
        """A handler of the process's own."""

    before = signal.signal(signal.SIGINT, custom)

    try:
        assert serve(capsys)[0] == 0
        assert signal.getsignal(signal.SIGINT) is custom
    finally:
        signal.signal(signal.SIGINT, before)


# Heartbeat and health


@posix_only
def test_the_worker_beats_while_it_runs(
    deployment: Deployment,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    heartbeat = tmp_path / "heartbeat"

    status, _, _ = serve(capsys, "--heartbeat-file", str(heartbeat))

    assert status == 0
    assert heartbeat.stat().st_mtime > time.time() - 60
    assert main(("worker", "health", "--heartbeat-file", str(heartbeat))) == 0
    assert capsys.readouterr().out.startswith(f"The last heartbeat at {heartbeat} is ")


def test_a_heartbeat_that_cannot_be_written_stops_the_worker_before_it_receives(
    deployment: Deployment,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    heartbeat = tmp_path / "missing" / "heartbeat"

    status, lines, err = serve(capsys, "--heartbeat-file", str(heartbeat))

    assert (status, lines) == (1, [])
    assert err == f"Cannot write the heartbeat file {heartbeat}: No such file or directory.\n"
    assert deployment.queue.calls == []


def test_health_without_a_heartbeat_is_unhealthy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    heartbeat = tmp_path / "heartbeat"

    assert main(("worker", "health", "--heartbeat-file", str(heartbeat))) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        f"No heartbeat at {heartbeat}; the worker has not started, or cannot write it.\n"
    )


def test_health_with_a_stale_heartbeat_is_unhealthy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    heartbeat = tmp_path / "heartbeat"
    heartbeat.touch()
    stale = time.time() - 120
    os.utime(heartbeat, (stale, stale))

    assert main(("worker", "health", "--heartbeat-file", str(heartbeat))) == 1
    assert ", older than 90 seconds.\n" in capsys.readouterr().err


# Failures


def test_without_the_extra_the_worker_says_which_to_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "boto3", None)

    status, lines, err = serve(capsys)

    assert (status, lines) == (1, [])
    assert err == f"{MISSING_WORKER_EXTRA_MESSAGE}\n"


def test_a_queue_that_fails_stops_the_worker_with_its_reason(
    deployment: Deployment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(
        **_: object,
    ) -> None:
        raise QueueError(f"SQS ReceiveMessage failed on {QUEUE_URL}: AccessDenied: Not allowed.")

    monkeypatch.setattr(deployment.queue, "receive", refuse)

    status, lines, err = serve(capsys)

    assert (status, lines) == (1, [])
    assert err == f"SQS ReceiveMessage failed on {QUEUE_URL}: AccessDenied: Not allowed.\n"


# Tracing


@posix_only
def test_each_job_span_names_the_message_it_ran(
    deployment: Deployment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    telemetry = RecordingTelemetry()
    monkeypatch.setattr(cli_tracing, "configure_from_environment", lambda: telemetry)
    deployment.queue.put("m-1", body())
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, _, _ = serve(capsys)

    (job,) = telemetry.named("azathoth.job")

    assert status == 0
    assert job.attributes["azathoth.worker.message_id"] == "m-1"
    assert job.attributes["azathoth.job.status"] == "succeeded"
    assert telemetry.shut_down

    for span in telemetry.spans:
        assert set(span.attributes) <= ATTRIBUTE_KEYS
