"""The worker's queues on Amazon SQS, over boto3 (ADR 0107).

Nothing else in the worker imports boto3, and it is imported only when an
SQS queue is opened, so the rest of Azathoth runs without the `worker` extra.
boto3 ships no types, so it is imported by name.

The client uses AWS's own credential chain, and boto3 honors
`AWS_ENDPOINT_URL_SQS`, so a local stand-in for SQS needs no option of ours.
"""

import importlib
import os
import re
from collections.abc import Callable
from typing import Any, Final
from urllib.parse import urlsplit

from azathoth.worker.errors import QueueError, WorkerUnavailableError
from azathoth.worker.queue import QueueMessage

AMAZON_QUEUE_HOST: Final = re.compile(r"^sqs\.([a-z0-9-]+)\.amazonaws\.com(?:\.cn)?$")
"""The host of an SQS queue URL, which names its region."""

FIFO_SUFFIX: Final = ".fifo"
"""How SQS names a FIFO queue."""

IDEMPOTENCY_KEY_ATTRIBUTE: Final = "idempotency_key"
"""The message attribute a sent result carries its request's key in."""

AWS_REGION_VARIABLE: Final = "AWS_REGION"
"""AWS's variable naming the region, which ECS sets."""


def queue_region(
    url: str,
) -> str | None:
    """Return the region an SQS queue URL names, or `None` for any other host."""

    matched = AMAZON_QUEUE_HOST.match(urlsplit(url).hostname or "")

    return matched.group(1) if matched is not None else None


def sqs_client(
    url: str,
) -> Any:
    """Return an SQS client for one queue, with standard retries.

    The region is the one the queue's URL names, since that is where the
    queue lives. A URL of another host, such as a local stand-in for SQS,
    takes `AWS_REGION`, or else the region boto3 finds in the environment or
    profile.

    Raises:
        WorkerUnavailableError: boto3 is not installed.
        QueueError: No region was found.
    """

    boto3 = _import("boto3")
    botocore_config = _import("botocore.config")

    session = boto3.session.Session()
    region = queue_region(url) or os.environ.get(AWS_REGION_VARIABLE) or session.region_name

    if region is None:
        raise QueueError(f"Cannot tell the AWS region of queue {url}; set AWS_REGION.")

    return session.client(
        "sqs",
        region_name=region,
        config=botocore_config.Config(
            retries={"mode": "standard"},
        ),
    )


class _SqsQueue:
    """One SQS queue, whose failed calls raise `QueueError`."""

    def __init__(
        self,
        url: str,
        *,
        client: Any | None,
    ) -> None:
        parts = urlsplit(url)

        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise QueueError(f"Queue URL {url!r} is not an http or https URL.")

        self.url = url
        self._client: Any = client if client is not None else sqs_client(url)

    def _call(
        self,
        operation: str,
        function: Callable[..., Any],
        **parameters: Any,
    ) -> Any:
        """Make one SQS call, turning botocore's errors into one line."""

        botocore_exceptions = _import("botocore.exceptions")

        try:
            return function(QueueUrl=self.url, **parameters)
        except botocore_exceptions.ClientError as exc:
            error = exc.response.get("Error", {})

            raise QueueError(
                f"SQS {operation} failed on {self.url}: "
                f"{error.get('Code', 'Unknown')}: {error.get('Message', '')}"
            ) from exc
        except botocore_exceptions.BotoCoreError as exc:
            raise QueueError(
                f"SQS {operation} failed on {self.url}: {type(exc).__name__}: {exc}"
            ) from exc


class SqsJobQueue(_SqsQueue):
    """A `JobQueue` on one SQS queue, standard or FIFO."""

    def __init__(
        self,
        url: str,
        *,
        client: Any | None = None,
    ) -> None:
        """Open one queue; boto3's client is made for it unless one is given.

        Raises:
            WorkerUnavailableError: boto3 is not installed.
            QueueError: The URL is not an http or https URL, or names no
                region boto3 can find.
        """

        super().__init__(url, client=client)

    def receive(
        self,
        *,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Long-poll for one message, hidden for the visibility timeout."""

        response = self._call(
            "ReceiveMessage",
            self._client.receive_message,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_seconds,
            VisibilityTimeout=visibility_timeout_seconds,
        )

        messages = response.get("Messages") or []

        if not messages:
            return None

        message = messages[0]

        return QueueMessage(
            message_id=message["MessageId"],
            receipt_handle=message["ReceiptHandle"],
            body=str(message["Body"]).encode("utf-8"),
        )

    def delete(
        self,
        message: QueueMessage,
    ) -> None:
        """Delete one received message by its receipt."""

        self._call(
            "DeleteMessage",
            self._client.delete_message,
            ReceiptHandle=message.receipt_handle,
        )

    def change_visibility(
        self,
        message: QueueMessage,
        *,
        timeout_seconds: int,
    ) -> None:
        """Hide one received message for `timeout_seconds` from now."""

        self._call(
            "ChangeMessageVisibility",
            self._client.change_message_visibility,
            ReceiptHandle=message.receipt_handle,
            VisibilityTimeout=timeout_seconds,
        )


class SqsResultQueue(_SqsQueue):
    """A `ResultQueue` on one standard SQS queue."""

    def __init__(
        self,
        url: str,
        *,
        client: Any | None = None,
    ) -> None:
        """Open one result queue; boto3's client is made for it unless one is given.

        Raises:
            WorkerUnavailableError: boto3 is not installed.
            QueueError: The URL is not an http or https URL, names a FIFO
                queue, or names no region boto3 can find.
        """

        if urlsplit(url).path.endswith(FIFO_SUFFIX):
            raise QueueError(
                f"The result queue {url} is a FIFO queue; "
                "the worker sends results to standard queues only."
            )

        super().__init__(url, client=client)

    def send(
        self,
        body: str,
        *,
        idempotency_key: str | None,
    ) -> None:
        """Send one result, with its request's key as a string attribute."""

        attributes = (
            {
                "MessageAttributes": {
                    IDEMPOTENCY_KEY_ATTRIBUTE: {
                        "DataType": "String",
                        "StringValue": idempotency_key,
                    }
                }
            }
            if idempotency_key is not None
            else {}
        )

        self._call(
            "SendMessage",
            self._client.send_message,
            MessageBody=body,
            **attributes,
        )


def _import(
    name: str,
) -> Any:
    """Import one boto3 module, or say which extra to install."""

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise WorkerUnavailableError() from exc


__all__ = [
    "AMAZON_QUEUE_HOST",
    "AWS_REGION_VARIABLE",
    "FIFO_SUFFIX",
    "IDEMPOTENCY_KEY_ATTRIBUTE",
    "SqsJobQueue",
    "SqsResultQueue",
    "queue_region",
    "sqs_client",
]
