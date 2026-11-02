"""Tests for the worker's SQS queues over boto3 (ADR 0107).

They need boto3, so they are skipped where the `worker` extra is not
installed. They never reach AWS: botocore's `Stubber` answers every call.
boto3 ships no types, so it is imported by name.
"""

import importlib
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from azathoth.worker import (
    MISSING_WORKER_EXTRA_MESSAGE,
    JobQueue,
    QueueError,
    QueueMessage,
    ResultQueue,
    SqsJobQueue,
    SqsResultQueue,
    WorkerUnavailableError,
    queue_region,
    sqs_client,
)

PROJECT_ROOT = Path(__file__).parents[2]

BOTO3 = "boto3>=1.39,<2"

URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-jobs"

RESULTS_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-results"

RECEIPT = "AQEB-receipt"


def project() -> dict[str, object]:
    """Return the `[project]` table of pyproject.toml."""

    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    table = data["project"]

    assert isinstance(table, dict)

    return table


def stubbed_client() -> Any:
    """Return a real SQS client with fixed credentials, for the Stubber."""

    pytest.importorskip("boto3")

    return (
        importlib.import_module("boto3")
        .session.Session()
        .client(
            "sqs",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
    )


@pytest.fixture
def client() -> Any:
    """Return an SQS client for one test."""

    return stubbed_client()


@pytest.fixture
def stubber(
    client: Any,
) -> Iterator[Any]:
    """Stub every call the client makes, and require each stubbed call."""

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(client) as active:
        yield active
        active.assert_no_pending_responses()


def message(
    body: str = '{"kind": "invoke"}',
) -> QueueMessage:
    """Return one received message."""

    return QueueMessage(message_id="m-1", receipt_handle=RECEIPT, body=body.encode())


# The extra


def test_the_worker_extra_installs_boto3_and_nothing_else() -> None:
    extras = project()["optional-dependencies"]

    assert isinstance(extras, dict)
    assert extras["worker"] == [BOTO3]
    assert BOTO3 in extras["dev"]


def test_without_boto3_the_worker_says_which_extra_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(WorkerUnavailableError) as raised:
        sqs_client(URL)

    assert str(raised.value) == MISSING_WORKER_EXTRA_MESSAGE
    assert MISSING_WORKER_EXTRA_MESSAGE == (
        "azathoth worker needs boto3, which is not installed; install azathoth-ai[worker]."
    )


# Regions and URLs


@pytest.mark.parametrize(
    ("url", "region"),
    [
        (URL, "us-east-1"),
        ("https://sqs.eu-central-1.amazonaws.com/123456789012/jobs", "eu-central-1"),
        ("https://sqs.cn-north-1.amazonaws.com.cn/123456789012/jobs", "cn-north-1"),
        ("http://localhost:9324/000000000000/jobs", None),
    ],
)
def test_a_queue_url_names_its_region_when_it_is_amazons(
    url: str,
    region: str | None,
) -> None:
    assert queue_region(url) == region


def test_the_client_takes_its_region_from_the_queue_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("boto3")
    isolate_aws(monkeypatch, tmp_path)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    client = sqs_client("https://sqs.ap-southeast-2.amazonaws.com/123456789012/jobs")

    assert client.meta.region_name == "ap-southeast-2"
    assert client.meta.service_model.service_name == "sqs"
    assert client.meta.config.retries["mode"] == "standard"


@pytest.mark.parametrize("variable", ["AWS_REGION", "AWS_DEFAULT_REGION"])
def test_a_queue_on_another_host_takes_the_environments_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    variable: str,
) -> None:
    pytest.importorskip("boto3")
    isolate_aws(monkeypatch, tmp_path)
    monkeypatch.setenv(variable, "eu-west-1")

    assert sqs_client("http://localhost:9324/000000000000/jobs").meta.region_name == "eu-west-1"


def test_a_queue_with_no_region_anywhere_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("boto3")
    isolate_aws(monkeypatch, tmp_path)

    url = "http://localhost:9324/000000000000/jobs"

    with pytest.raises(QueueError) as raised:
        sqs_client(url)

    assert str(raised.value) == f"Cannot tell the AWS region of queue {url}; set AWS_REGION."


@pytest.mark.parametrize("url", ["azathoth-jobs", "file:///tmp/jobs", "https://"])
def test_a_queue_url_must_be_an_http_url(
    url: str,
) -> None:
    with pytest.raises(QueueError) as raised:
        SqsJobQueue(url, client=object())

    assert str(raised.value) == f"Queue URL {url!r} is not an http or https URL."


def test_a_fifo_result_queue_is_refused() -> None:
    url = RESULTS_URL + ".fifo"

    with pytest.raises(QueueError) as raised:
        SqsResultQueue(url, client=object())

    assert str(raised.value) == (
        f"The result queue {url} is a FIFO queue; the worker sends results to standard queues only."
    )


def isolate_aws(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Hide every region and profile the machine running the tests may have."""

    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)

    empty = tmp_path / "aws-config"
    empty.write_text("", encoding="utf-8")

    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty))


# The job queue


def test_the_sqs_queues_are_the_protocols(
    client: Any,
) -> None:
    queue: JobQueue = SqsJobQueue(URL, client=client)
    results: ResultQueue = SqsResultQueue(RESULTS_URL, client=client)

    assert queue.receive is not None
    assert results.send is not None


def test_receive_long_polls_for_one_message_and_hides_it(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "receive_message",
        {
            "Messages": [
                {
                    "MessageId": "m-1",
                    "ReceiptHandle": RECEIPT,
                    "Body": '{"kind": "invoke", "note": "schlüssel"}',
                }
            ]
        },
        {
            "QueueUrl": URL,
            "MaxNumberOfMessages": 1,
            "WaitTimeSeconds": 20,
            "VisibilityTimeout": 120,
        },
    )

    received = SqsJobQueue(URL, client=client).receive(
        wait_seconds=20,
        visibility_timeout_seconds=120,
    )

    assert received == QueueMessage(
        message_id="m-1",
        receipt_handle=RECEIPT,
        body='{"kind": "invoke", "note": "schlüssel"}'.encode(),
    )


def test_an_empty_receive_is_none(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "receive_message",
        {},
        {
            "QueueUrl": URL,
            "MaxNumberOfMessages": 1,
            "WaitTimeSeconds": 0,
            "VisibilityTimeout": 30,
        },
    )

    assert (
        SqsJobQueue(URL, client=client).receive(wait_seconds=0, visibility_timeout_seconds=30)
        is None
    )


def test_delete_removes_the_message_by_its_receipt(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response("delete_message", {}, {"QueueUrl": URL, "ReceiptHandle": RECEIPT})

    SqsJobQueue(URL, client=client).delete(message())


def test_change_visibility_hides_the_message_by_its_receipt(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "change_message_visibility",
        {},
        {"QueueUrl": URL, "ReceiptHandle": RECEIPT, "VisibilityTimeout": 0},
    )

    SqsJobQueue(URL, client=client).change_visibility(message(), timeout_seconds=0)


def test_a_refused_call_names_the_operation_the_queue_and_awss_error(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "delete_message",
        service_error_code="ReceiptHandleIsInvalid",
        service_message="The receipt handle is not valid.",
    )

    with pytest.raises(QueueError) as raised:
        SqsJobQueue(URL, client=client).delete(message())

    assert str(raised.value) == (
        f"SQS DeleteMessage failed on {URL}: ReceiptHandleIsInvalid: "
        "The receipt handle is not valid."
    )


def test_a_call_that_never_reached_aws_names_botocores_error(
    client: Any,
) -> None:
    botocore_exceptions = importlib.import_module("botocore.exceptions")

    def unreachable(
        **_: object,
    ) -> None:
        raise botocore_exceptions.NoCredentialsError()

    client.receive_message = unreachable

    with pytest.raises(QueueError) as raised:
        SqsJobQueue(URL, client=client).receive(wait_seconds=0, visibility_timeout_seconds=30)

    assert str(raised.value) == (
        f"SQS ReceiveMessage failed on {URL}: NoCredentialsError: Unable to locate credentials"
    )


# The result queue


def test_a_result_is_sent_with_its_key_as_an_attribute(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "send_message",
        {"MessageId": "r-1"},
        {
            "QueueUrl": RESULTS_URL,
            "MessageBody": '{"status": "succeeded"}',
            "MessageAttributes": {
                "idempotency_key": {"DataType": "String", "StringValue": "order-4711"}
            },
        },
    )

    SqsResultQueue(RESULTS_URL, client=client).send(
        '{"status": "succeeded"}',
        idempotency_key="order-4711",
    )


def test_a_result_without_a_key_is_sent_without_attributes(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "send_message",
        {"MessageId": "r-2"},
        {"QueueUrl": RESULTS_URL, "MessageBody": '{"status": "rejected"}'},
    )

    SqsResultQueue(RESULTS_URL, client=client).send(
        '{"status": "rejected"}',
        idempotency_key=None,
    )
