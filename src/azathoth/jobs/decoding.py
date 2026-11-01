"""Decoding job requests, kind and version first (ADR 0097)."""

import json
from collections.abc import Mapping
from typing import NoReturn

from pydantic import JsonValue, ValidationError

from azathoth.jobs.envelope import (
    SUPPORTED_JOB_KINDS,
    SUPPORTED_JOB_VERSIONS,
    InvokeJobRequest,
    JobError,
    JobErrorCode,
)
from azathoth.workflows import validate_idempotency_key

KIND_KEY = "kind"

VERSION_KEY = "version"

IDEMPOTENCY_KEY_KEY = "idempotency_key"

_SOURCE_TAGS = frozenset({"inline", "reference"})


class JobRequestError(ValueError):
    """Raised when data is not one acceptable job request.

    It carries the job error to report, and the request's idempotency key
    when the request could be read far enough to find a valid one.
    """

    def __init__(
        self,
        code: JobErrorCode,
        message: str,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        super().__init__(message)

        self.error = JobError(
            code=code,
            message=message,
            metadata=dict(metadata) if metadata is not None else {},
        )
        self.idempotency_key = idempotency_key


def readable_idempotency_key(
    data: object,
) -> str | None:
    """Return the valid idempotency key data holds, if it holds one."""

    if not isinstance(data, dict):
        return None

    key = data.get(IDEMPOTENCY_KEY_KEY)

    if not isinstance(key, str):
        return None

    try:
        return validate_idempotency_key(key)
    except ValueError:
        return None


def decode_job_request(
    data: JsonValue,
) -> InvokeJobRequest:
    """Decode one job request from JSON data.

    The kind and version are checked before the rest of the request, so a
    request for another version is reported as an unsupported version, never
    as a list of fields this version does not know.

    Raises:
        JobRequestError: The data is not an object, names no or an unknown
            kind, names no, a non-integer or an unsupported version, or does
            not have the request's shape.
    """

    if not isinstance(data, dict):
        _reject(
            JobErrorCode.INVALID_REQUEST,
            "A job request must be a JSON object.",
        )

    key = readable_idempotency_key(data)

    _check_kind(data, key)
    _check_version(data, key)

    try:
        return InvokeJobRequest.model_validate(data)
    except ValidationError as exc:
        problems = _problems(exc)
        errors: list[JsonValue] = list(problems)

        raise JobRequestError(
            JobErrorCode.INVALID_REQUEST,
            "The job request is not valid: "
            + "; ".join(f"{problem['field']}: {problem['message']}" for problem in problems),
            metadata={"errors": errors},
            idempotency_key=key,
        ) from exc


def parse_job_request(
    content: str | bytes,
) -> InvokeJobRequest:
    """Parse and decode one job request from JSON text.

    Bytes are decoded as UTF-8, with or without a byte order mark. `NaN` and
    the infinities are refused, since JSON has no such numbers.

    Raises:
        JobRequestError: The content is not UTF-8, is not JSON, or does not
            decode as a job request.
    """

    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            _reject(
                JobErrorCode.INVALID_REQUEST,
                "A job request must be UTF-8 text.",
            )
    else:
        text = content.removeprefix("﻿")

    try:
        data = json.loads(
            text,
            parse_constant=_refuse_constant,
        )
    except json.JSONDecodeError as exc:
        _reject(
            JobErrorCode.INVALID_REQUEST,
            f"A job request must be JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.",
        )
    except ValueError as exc:
        _reject(
            JobErrorCode.INVALID_REQUEST,
            f"A job request must be JSON: {exc}",
        )

    return decode_job_request(data)


def _check_kind(
    data: dict[str, JsonValue],
    key: str | None,
) -> None:
    """Refuse a request that names no kind, or one this release does not know."""

    supported_kinds: list[JsonValue] = list(SUPPORTED_JOB_KINDS)
    metadata: dict[str, JsonValue] = {"supported_kinds": supported_kinds}

    if KIND_KEY not in data:
        _reject(
            JobErrorCode.INVALID_REQUEST,
            "A job request must name its kind.",
            metadata=metadata,
            idempotency_key=key,
        )

    kind = data[KIND_KEY]

    if not isinstance(kind, str) or kind not in SUPPORTED_JOB_KINDS:
        _reject(
            JobErrorCode.INVALID_REQUEST,
            f"Unknown job kind {json.dumps(kind)}; supported kinds: "
            + ", ".join(SUPPORTED_JOB_KINDS)
            + ".",
            metadata=metadata,
            idempotency_key=key,
        )


def _check_version(
    data: dict[str, JsonValue],
    key: str | None,
) -> None:
    """Refuse a request that names no version, or one this release does not speak."""

    if VERSION_KEY not in data:
        _reject(
            JobErrorCode.INVALID_REQUEST,
            "A job request must name its version.",
            idempotency_key=key,
        )

    version = data[VERSION_KEY]

    if isinstance(version, bool) or not isinstance(version, int):
        _reject(
            JobErrorCode.INVALID_REQUEST,
            f"A job request's version must be an integer; got {json.dumps(version)}.",
            idempotency_key=key,
        )

    if version not in SUPPORTED_JOB_VERSIONS:
        supported_versions: list[JsonValue] = list(SUPPORTED_JOB_VERSIONS)

        _reject(
            JobErrorCode.UNSUPPORTED_VERSION,
            f"Job version {version} is not supported; supported versions: "
            + ", ".join(str(supported) for supported in SUPPORTED_JOB_VERSIONS)
            + ".",
            metadata={"supported_versions": supported_versions},
            idempotency_key=key,
        )


def _problems(
    error: ValidationError,
) -> tuple[dict[str, JsonValue], ...]:
    """Return one validation error's problems as fields and messages."""

    problems: list[dict[str, JsonValue]] = []

    for detail in error.errors(include_url=False):
        location = [
            str(part)
            for index, part in enumerate(detail["loc"])
            if not (index == 1 and detail["loc"][0] == "input" and part in _SOURCE_TAGS)
        ]

        field = ".".join(location) or "request"

        if detail["type"] == "missing":
            message = "is required"
        elif detail["type"] == "extra_forbidden":
            message = "is not a field of this request"
        else:
            message = str(detail["msg"]).removeprefix("Value error, ")

        problems.append({"field": field, "message": message})

    return tuple(problems)


def _refuse_constant(
    constant: str,
) -> NoReturn:
    """Refuse `NaN`, `Infinity` and `-Infinity`, which JSON does not define."""

    raise ValueError(f"{constant} is not a JSON number.")


def _reject(
    code: JobErrorCode,
    message: str,
    *,
    metadata: Mapping[str, JsonValue] | None = None,
    idempotency_key: str | None = None,
) -> NoReturn:
    """Raise the job request error for one rejection."""

    raise JobRequestError(
        code,
        message,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


__all__ = [
    "IDEMPOTENCY_KEY_KEY",
    "KIND_KEY",
    "VERSION_KEY",
    "JobRequestError",
    "decode_job_request",
    "parse_job_request",
    "readable_idempotency_key",
]
