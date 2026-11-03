"""Keeping resolved content in Amazon S3 instead of the database (ADR 0108).

`AZATHOTH_CONTENT_STORE=s3://<BUCKET>[/<PREFIX>]` keeps every resolved
input's bytes in S3, as `<PREFIX>/sha256/<DIGEST>`, rather than in the
database's `content_blobs` table. Content is immutable, so a write is made
only if nothing is there yet, with S3's conditional `If-None-Match: *`.

boto3 is imported only when the store is made, and the store is made only
when a command first needs it. boto3 ships no types, so it is imported by
name.
"""

import importlib
from collections.abc import Callable, Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from azathoth.inputs.s3 import BUCKET_NAME, S3_SCHEME
from azathoth.inputs.store import content_bytes_digest

CONTENT_STORE_VARIABLE: Final = "AZATHOTH_CONTENT_STORE"
"""The variable naming an S3 content store; unset keeps content in the database."""

DIGEST_FOLDER: Final = "sha256"
"""The folder, under the prefix, that content is kept in by its digest."""

ALREADY_STORED_CODES: Final = frozenset({"PreconditionFailed", "ConditionalRequestConflict"})
"""What S3 answers a conditional write with when the object exists, or is being written."""

MISSING_CODES: Final = frozenset({"NoSuchKey", "404", "NotFound"})
"""What S3 answers a read of an object that is not there with."""

MISSING_CONTENT_STORE_EXTRA_MESSAGE: Final = (
    f"{CONTENT_STORE_VARIABLE} names S3, but boto3 is not installed; install azathoth-ai[worker]."
)
"""What an S3 content store without the `worker` extra reports."""


class ContentStoreError(RuntimeError):
    """The content store cannot be used: it is misconfigured, unreachable or refuses.

    It is never the fault of the request whose content was being stored, so
    it stops the command rather than refusing the request.
    """


class S3ContentLocation(BaseModel):
    """Where an S3 content store keeps content: a bucket, and a prefix in it."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    bucket: str
    prefix: str = ""

    @classmethod
    def parse(
        cls,
        url: str,
    ) -> "S3ContentLocation":
        """Parse `s3://<BUCKET>[/<PREFIX>]`; a trailing `/` changes nothing.

        Raises:
            ContentStoreError: The URL is not an `s3://` URL naming a valid
                bucket, with no query or fragment.
        """

        parts = urlsplit(url)

        if (
            parts.scheme.lower() != S3_SCHEME
            or BUCKET_NAME.match(parts.netloc) is None
            or parts.query
            or parts.fragment
            or "?" in url
            or "#" in url
        ):
            raise ContentStoreError(
                f"{CONTENT_STORE_VARIABLE} {url!r} is not an s3://<BUCKET>[/<PREFIX>] URL."
            )

        return cls(bucket=parts.netloc, prefix=parts.path.strip("/"))

    def key(
        self,
        digest: str,
    ) -> str:
        """Return the key content with one digest is kept under."""

        folder = f"{self.prefix}/{DIGEST_FOLDER}" if self.prefix else DIGEST_FOLDER

        return f"{folder}/{digest}"

    def url(
        self,
        digest: str,
    ) -> str:
        """Return the `s3://` URL content with one digest is kept at."""

        return f"s3://{self.bucket}/{self.key(digest)}"


def content_store_location(
    environment: Mapping[str, str],
) -> S3ContentLocation | None:
    """Return the S3 content store the environment names, or `None` for the database.

    Raises:
        ContentStoreError: `AZATHOTH_CONTENT_STORE` is set, but not to an
            `s3://` URL.
    """

    value = environment.get(CONTENT_STORE_VARIABLE)

    return S3ContentLocation.parse(value) if value else None


class S3ContentStore:
    """A `ContentStore` in one S3 bucket, under one prefix."""

    def __init__(
        self,
        location: S3ContentLocation,
        *,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Keep content at one location; boto3's client is made now unless given.

        Raises:
            ContentStoreError: boto3 is not installed.
        """

        self.location = location
        self._client: Any = (
            client
            if client is not None
            else (client_factory if client_factory is not None else s3_content_client)()
        )
        botocore_exceptions = _import("botocore.exceptions")
        self._client_error: type[Exception] = botocore_exceptions.ClientError
        self._botocore_error: type[Exception] = botocore_exceptions.BotoCoreError

    def put(
        self,
        content: bytes,
    ) -> str:
        """Store content, unless it is already stored, and return its digest.

        Raises:
            ContentStoreError: S3 refused the write, or could not be reached.
        """

        digest = content_bytes_digest(content)
        what = f"Cannot store content in {self.location.url(digest)}"

        try:
            self._client.put_object(
                Bucket=self.location.bucket,
                Key=self.location.key(digest),
                Body=content,
                IfNoneMatch="*",
            )
        except self._client_error as exc:
            if _code(exc) not in ALREADY_STORED_CODES:
                raise self._failure(what, exc) from exc
        except self._botocore_error as exc:
            raise self._failure(what, exc) from exc

        return digest

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the content with one digest, or `None` when it is not stored.

        Raises:
            ContentStoreError: S3 refused the read, or could not be reached.
        """

        try:
            response = self._client.get_object(
                Bucket=self.location.bucket,
                Key=self.location.key(digest),
            )
        except self._client_error as exc:
            if _code(exc) in MISSING_CODES:
                return None

            raise self._failure(f"Cannot read {self.location.url(digest)}", exc) from exc
        except self._botocore_error as exc:
            raise self._failure(f"Cannot read {self.location.url(digest)}", exc) from exc

        stream = response["Body"]

        try:
            content: bytes = stream.read()
        finally:
            stream.close()

        return content

    def contains(
        self,
        digest: str,
    ) -> bool:
        """Return whether content with one digest is stored.

        Raises:
            ContentStoreError: S3 refused the read, or could not be reached.
        """

        try:
            self._client.head_object(
                Bucket=self.location.bucket,
                Key=self.location.key(digest),
            )
        except self._client_error as exc:
            if _code(exc) in MISSING_CODES:
                return False

            raise self._failure(f"Cannot read {self.location.url(digest)}", exc) from exc
        except self._botocore_error as exc:
            raise self._failure(f"Cannot read {self.location.url(digest)}", exc) from exc

        return True

    def _failure(
        self,
        what: str,
        exc: Exception,
    ) -> ContentStoreError:
        """Return the one-line error for a call S3 refused, or that never reached it."""

        if isinstance(exc, self._client_error):
            error = getattr(exc, "response", {}).get("Error", {})

            return ContentStoreError(
                f"{what}: {error.get('Code', 'Unknown')}: {error.get('Message', '')}"
            )

        return ContentStoreError(f"{what}: {type(exc).__name__}: {exc}")


def s3_content_client() -> Any:
    """Return an S3 client with standard retries, through AWS's own credential chain.

    Raises:
        ContentStoreError: boto3 is not installed.
    """

    boto3 = _import("boto3")
    botocore_config = _import("botocore.config")

    return boto3.session.Session().client(
        "s3",
        config=botocore_config.Config(
            retries={"mode": "standard"},
        ),
    )


def _code(
    exc: Exception,
) -> str:
    """Return the error code of one botocore `ClientError`."""

    return str(getattr(exc, "response", {}).get("Error", {}).get("Code", "Unknown"))


def _import(
    name: str,
) -> Any:
    """Import one boto3 module, or say which extra to install."""

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ContentStoreError(MISSING_CONTENT_STORE_EXTRA_MESSAGE) from exc


__all__ = [
    "ALREADY_STORED_CODES",
    "CONTENT_STORE_VARIABLE",
    "DIGEST_FOLDER",
    "MISSING_CODES",
    "MISSING_CONTENT_STORE_EXTRA_MESSAGE",
    "ContentStoreError",
    "S3ContentLocation",
    "S3ContentStore",
    "content_store_location",
    "s3_content_client",
]
