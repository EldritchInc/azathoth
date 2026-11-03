"""Resolving `s3://` references from allow-listed locations (ADR 0108).

An `s3://<BUCKET>/<KEY>` reference names one object. A resolver reads only
objects inside the locations it allows, a bucket or a bucket and a key
prefix, and never more than the cap plus one byte, with one ranged GET.

boto3 is imported only when a resolver first reads an allowed object, so
the rest of Azathoth runs without the `worker` extra. boto3 ships no types,
so it is imported by name.
"""

import importlib
import re
from collections.abc import Callable, Sequence
from typing import Any, Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from azathoth.inputs.resolution import InputResolutionError, input_too_large

S3_SCHEME: Final = "s3"
"""The scheme of references to objects in Amazon S3."""

BUCKET_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
"""A valid S3 bucket name: 3 to 63 lowercase letters, digits, dots and hyphens."""

MISSING_OBJECT_CODES: Final = frozenset({"NoSuchKey", "NoSuchBucket"})
"""The error codes S3 answers a missing object or bucket with."""

EMPTY_RANGE_CODE: Final = "InvalidRange"
"""What S3 answers a ranged GET of an empty object with."""

MISSING_S3_EXTRA_MESSAGE: Final = (
    "s3:// inputs need boto3, which is not installed; install azathoth-ai[worker]."
)
"""What reading an `s3://` reference without the `worker` extra reports."""


class InputUnavailableError(RuntimeError):
    """An input source could not be reached at all, through no fault of the request.

    Unlike `InputResolutionError`, it is not reported to the request's caller
    as `invalid_input`: the entry point itself cannot read inputs, as when it
    has no credentials or boto3 is not installed.
    """


class S3InputLocation(BaseModel):
    """Where `s3://` references may point: a bucket, and a key prefix within it."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    bucket: str
    prefix: str = ""

    @classmethod
    def parse(
        cls,
        value: str,
    ) -> "S3InputLocation":
        """Parse `BUCKET` or `BUCKET/PREFIX`.

        Raises:
            ValueError: The value does not start with a valid bucket name.
        """

        bucket, _, prefix = value.partition("/")

        if BUCKET_NAME.match(bucket) is None:
            raise ValueError(
                f"{value!r} is not an S3 bucket, or a bucket and a key prefix: "
                "a bucket name is 3 to 63 lowercase letters, digits, dots and hyphens."
            )

        return cls(bucket=bucket, prefix=prefix)

    def allows(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Return whether an object lies inside this location.

        A prefix is matched literally, as S3 matches it: keys have no paths.
        """

        return bucket == self.bucket and key.startswith(self.prefix)

    def __str__(
        self,
    ) -> str:
        return f"{self.bucket}/{self.prefix}" if self.prefix else self.bucket


def s3_object(
    uri: str,
) -> tuple[str, str]:
    """Return the bucket and key one `s3://` URI names.

    The key is the rest of the URI after the bucket, exactly as written.

    Raises:
        InputResolutionError: The URI is not an `s3://` URI, names no bucket
            or no key, or has a query or a fragment.
    """

    parts = urlsplit(uri)

    if parts.scheme.lower() != S3_SCHEME:
        raise InputResolutionError(f"Input {uri} is not an s3:// URI.")

    if parts.query or parts.fragment or "?" in uri or "#" in uri:
        raise InputResolutionError(
            f"Input {uri} must name an object only, with no query or fragment."
        )

    key = parts.path.removeprefix("/")

    if not parts.netloc or not key:
        raise InputResolutionError(f"Input {uri} must name a bucket and an object key.")

    return parts.netloc, key


class S3InputResolver:
    """Read `s3://` references inside the allowed locations."""

    def __init__(
        self,
        allowed: Sequence[S3InputLocation],
        *,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Allow some locations; boto3's client is made on the first read unless given.

        Args:
            allowed: The locations references may point into. None allows
                nothing.
            client: An S3 client to read with.
            client_factory: Makes the client on the first read, when none is
                given; boto3's own, with standard retries, when omitted.
        """

        self.allowed = tuple(allowed)
        self._client: Any | None = client
        self._client_factory = client_factory if client_factory is not None else s3_client

    def read(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> bytes:
        """Return an allowed object's content, reading at most one byte past the cap.

        Raises:
            InputResolutionError: The URI names no object, lies outside the
                allowed locations, or the object is missing, may not be read,
                or is larger than `max_bytes`.
            InputUnavailableError: S3 could not be reached, or boto3 is not
                installed.
        """

        bucket, key = s3_object(uri)

        if not any(location.allows(bucket, key) for location in self.allowed):
            allowed = ", ".join(str(location) for location in self.allowed) or "none"

            raise InputResolutionError(
                f"Input {uri} is not in an allowed location; allowed: {allowed}."
            )

        botocore_exceptions = _import("botocore.exceptions")
        client = self._reader()

        try:
            response = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes}")
        except botocore_exceptions.ClientError as exc:
            error = exc.response.get("Error", {})
            code = str(error.get("Code", "Unknown"))

            if code == EMPTY_RANGE_CODE:
                return b""

            if code in MISSING_OBJECT_CODES:
                raise InputResolutionError(f"Input {uri} does not exist.") from exc

            raise InputResolutionError(
                f"Unable to read input {uri}: {code}: {error.get('Message', '')}"
            ) from exc
        except botocore_exceptions.BotoCoreError as exc:
            raise InputUnavailableError(
                f"Unable to reach S3 for input {uri}: {type(exc).__name__}: {exc}"
            ) from exc

        stream = response["Body"]

        try:
            content: bytes = stream.read(max_bytes + 1)
        finally:
            stream.close()

        if len(content) > max_bytes:
            raise input_too_large(uri, max_bytes)

        return content

    def _reader(
        self,
    ) -> Any:
        """Return the client, making it on the first read."""

        if self._client is None:
            self._client = self._client_factory()

        return self._client


def s3_client() -> Any:
    """Return an S3 client with standard retries, through AWS's own credential chain.

    Raises:
        InputUnavailableError: boto3 is not installed.
    """

    boto3 = _import("boto3")
    botocore_config = _import("botocore.config")

    return boto3.session.Session().client(
        "s3",
        config=botocore_config.Config(
            retries={"mode": "standard"},
        ),
    )


def _import(
    name: str,
) -> Any:
    """Import one boto3 module, or say which extra to install."""

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise InputUnavailableError(MISSING_S3_EXTRA_MESSAGE) from exc


__all__ = [
    "BUCKET_NAME",
    "EMPTY_RANGE_CODE",
    "MISSING_OBJECT_CODES",
    "MISSING_S3_EXTRA_MESSAGE",
    "S3_SCHEME",
    "InputUnavailableError",
    "S3InputLocation",
    "S3InputResolver",
    "s3_client",
    "s3_object",
]
