"""Tests for a worker that reads `s3://` inputs from allow-listed locations (ADR 0108).

The worker runs for real against a deployed workflow in SQLite, over an
in-memory queue, with its S3 client answered by botocore's `Stubber`. It is
stopped with a signal, so the tests that serve run only where POSIX delivers
signals this way.
"""

import importlib
import io
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import azathoth.cli.worker as cli_worker
from azathoth.cli import main
from azathoth.cli.worker import MAX_WORKER_INPUT_BYTES, worker_input_policy
from azathoth.inputs import (
    MISSING_S3_EXTRA_MESSAGE,
    S3_SCHEME,
    S3InputLocation,
    SQLiteContentStore,
    content_bytes_digest,
    s3_client,
)
from azathoth.jobs import JobErrorCode, JobStatus
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
)
from tests.cli.test_job_commands import KEY
from tests.cli.test_worker_command import (
    QUEUE_URL,
    RESULTS_URL,
    Deployment,
    body,
    deploy,
    posix_only,
    serve,
)
from tests.worker.queues import results_of

BUCKET = "azathoth-inputs"

URI = f"s3://{BUCKET}/requests/review.json"

REQUEST = json.dumps({"request": "review the rename"}).encode()

ALLOWED = ("--allow-input-bucket", f"{BUCKET}/requests/")


@pytest.fixture
def deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Deployment:
    """Deploy the job workflow, and give the worker in-memory queues."""

    return deploy(tmp_path, monkeypatch)


@pytest.fixture
def s3(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Any]:
    """Give the worker a real S3 client whose every call the Stubber answers."""

    pytest.importorskip("boto3")

    client = (
        importlib.import_module("boto3")
        .session.Session()
        .client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
    )
    made: list[int] = []

    def open_s3_client() -> Any:
        made.append(1)

        return client

    monkeypatch.setattr(cli_worker, "open_s3_client", open_s3_client)

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(client) as stubber:
        stubber.made = made
        yield stubber
        stubber.assert_no_pending_responses()


def expect_get(
    stubber: Any,
    content: bytes,
    *,
    max_bytes: int = 10 * 1024 * 1024,
) -> None:
    """Expect one ranged read of the request object."""

    streaming = importlib.import_module("botocore.response").StreamingBody

    stubber.add_response(
        "get_object",
        {"Body": streaming(io.BytesIO(content), len(content)), "ContentLength": len(content)},
        {"Bucket": BUCKET, "Key": "requests/review.json", "Range": f"bytes=0-{max_bytes}"},
    )


def referencing(
    uri: str = URI,
) -> bytes:
    """Return a message body whose request's input is an `s3://` reference."""

    return body(input={"uri": uri, "media_type": "application/json"})


@dataclass
class Outcome:
    """What one served message came to."""

    status: int
    lines: list[dict[str, object]]
    err: str


def serve_one(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
    message: bytes,
    *options: str,
) -> Outcome:
    """Serve one message until it is deleted, then stop the worker."""

    deployment.queue.put("m-1", message)
    deployment.queue.done = lambda: deployment.queue.find("m-1").deleted

    status, lines, err = serve(capsys, "--result-queue-url", RESULTS_URL, *options)

    return Outcome(status, lines, err)


# The policy


def test_a_worker_allowed_no_location_accepts_no_scheme() -> None:
    policy = worker_input_policy((), max_bytes=1024, client=None)

    assert policy.accepted_schemes == ()
    assert policy.max_bytes == 1024


def test_a_worker_allowed_locations_accepts_s3_only() -> None:
    allowed = (S3InputLocation.parse(f"{BUCKET}/requests/"),)

    policy = worker_input_policy(allowed, max_bytes=2048, client=object())

    assert policy.accepted_schemes == (S3_SCHEME,)
    assert policy.max_bytes == 2048


# Options


def test_an_allowed_location_that_is_not_a_bucket_is_refused_before_anything_opens(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        ("worker", "run", "--queue-url", QUEUE_URL, "--allow-input-bucket", "Not_A_Bucket")
    )
    captured = capsys.readouterr()

    assert status == 1
    assert captured.err == (
        "--allow-input-bucket: 'Not_A_Bucket' is not an S3 bucket, or a bucket and a key "
        "prefix: a bucket name is 3 to 63 lowercase letters, digits, dots and hyphens.\n"
    )
    assert deployment.opened == []


@pytest.mark.parametrize("cap", ["0", str(MAX_WORKER_INPUT_BYTES + 1)])
def test_a_cap_outside_one_byte_to_100_mib_is_refused(
    deployment: Deployment,
    capsys: pytest.CaptureFixture[str],
    cap: str,
) -> None:
    status = main(("worker", "run", "--queue-url", QUEUE_URL, "--max-input-bytes", cap))

    assert status == 1
    assert capsys.readouterr().err == (
        "--max-input-bytes: Input should be from 1 to 104857600 bytes.\n"
    )
    assert MAX_WORKER_INPUT_BYTES == 100 * 1024 * 1024
    assert deployment.opened == []


def test_every_problem_with_the_options_is_reported_at_once(
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
            "--allow-input-bucket",
            "ab",
            "--max-input-bytes",
            "0",
        )
    )

    assert status == 1
    assert capsys.readouterr().err.splitlines() == [
        "--wait-seconds: Input should be less than or equal to 20.",
        "--allow-input-bucket: 'ab' is not an S3 bucket, or a bucket and a key prefix: "
        "a bucket name is 3 to 63 lowercase letters, digits, dots and hyphens.",
        "--max-input-bytes: Input should be from 1 to 104857600 bytes.",
    ]


def test_without_boto3_a_worker_allowed_s3_stops_before_it_receives(
    deployment: Deployment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_worker, "open_s3_client", s3_client)
    monkeypatch.setitem(sys.modules, "boto3", None)

    status, lines, err = serve(capsys, *ALLOWED)

    assert (status, lines) == (1, [])
    assert err == f"{MISSING_S3_EXTRA_MESSAGE}\n"
    assert deployment.queue.calls == []


# Serving


@posix_only
def test_an_allowed_s3_input_is_read_resolved_and_recorded(
    deployment: Deployment,
    s3: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expect_get(s3, REQUEST)

    outcome = serve_one(deployment, capsys, referencing(), *ALLOWED)

    (result,) = results_of(deployment.results)
    (invocation,) = deployment.environment.invocations()
    store = SQLiteContentStore(deployment.environment.database)

    assert outcome.status == 0
    assert s3.made == [1]
    assert result.status is JobStatus.SUCCEEDED
    events = {event.event_type: event.payload for event in invocation.initial_context.events}

    assert events[WORKFLOW_INPUT_EVENT_TYPE] == {"input": {"request": "review the rename"}}
    assert events[WORKFLOW_INPUT_RESOLVED_EVENT_TYPE] == {
        "uri": URI,
        "media_type": "application/json",
        "size_bytes": len(REQUEST),
        "digest": content_bytes_digest(REQUEST),
    }
    assert store.get(content_bytes_digest(REQUEST)) == REQUEST


@posix_only
def test_the_cap_is_the_workers_own(
    deployment: Deployment,
    s3: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expect_get(s3, REQUEST, max_bytes=8)

    outcome = serve_one(deployment, capsys, referencing(), *ALLOWED, "--max-input-bytes", "8")

    (result,) = results_of(deployment.results)

    assert outcome.status == 0
    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert result.error.message == f"Input {URI} is larger than the limit of 8 bytes."
    assert deployment.environment.invocations() == ()


@posix_only
@pytest.mark.parametrize(
    "uri",
    [
        f"s3://{BUCKET}/secrets/key.json",
        "s3://azathoth-other/requests/review.json",
    ],
)
def test_an_input_outside_the_allowed_locations_is_rejected_unread(
    deployment: Deployment,
    s3: Any,
    capsys: pytest.CaptureFixture[str],
    uri: str,
) -> None:
    outcome = serve_one(deployment, capsys, referencing(uri), *ALLOWED)

    (result,) = results_of(deployment.results)

    assert outcome.status == 0
    assert outcome.lines[0]["settled"] == "deleted"
    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert result.error.message == (
        f"Input {uri} is not in an allowed location; allowed: {BUCKET}/requests/."
    )


@posix_only
def test_a_worker_allowed_s3_still_refuses_files(
    deployment: Deployment,
    s3: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcome = serve_one(deployment, capsys, referencing("file:///etc/hostname"), *ALLOWED)

    (result,) = results_of(deployment.results)

    assert outcome.status == 0
    assert result.error is not None
    assert result.error.message == (
        "Input file:///etc/hostname uses the 'file' scheme, which is not accepted here; "
        "accepted schemes: s3."
    )


@posix_only
def test_a_missing_object_is_rejected(
    deployment: Deployment,
    s3: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    s3.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    outcome = serve_one(deployment, capsys, referencing(), *ALLOWED)

    (result,) = results_of(deployment.results)

    assert outcome.status == 0
    assert result.error is not None
    assert result.error.message == f"Input {URI} does not exist."


def test_s3_that_cannot_be_reached_stops_the_worker_and_leaves_its_message(
    deployment: Deployment,
    s3: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    botocore_exceptions = importlib.import_module("botocore.exceptions")
    client = cli_worker.open_s3_client()

    def unreachable(
        **_: object,
    ) -> None:
        raise botocore_exceptions.NoCredentialsError()

    monkeypatch.setattr(client, "get_object", unreachable)
    deployment.queue.put("m-1", referencing())

    status, lines, err = serve(capsys, *ALLOWED)

    reason = f"Unable to reach S3 for input {URI}: NoCredentialsError: Unable to locate credentials"

    assert status == 1
    assert lines == [
        {
            "message_id": "m-1",
            "idempotency_key": KEY,
            "status": None,
            "invocation_id": None,
            "settled": "left",
        }
    ]
    assert err == f"Message m-1 stays on the queue; running it failed: {reason}\n{reason}\n"
    assert not deployment.queue.find("m-1").deleted
    assert deployment.environment.invocations() == ()
