"""Tests for decoding job requests, kind and version first (ADR 0097)."""

import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.inputs import InlineInput
from azathoth.inputs.source import EXCLUSIVE_KEYS_MESSAGE
from azathoth.jobs import (
    JobErrorCode,
    JobRequestError,
    decode_job_request,
    parse_job_request,
    readable_idempotency_key,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

KEY = "order-4711-review"


def request_data(
    **changes: Any,
) -> dict[str, Any]:
    """Return one valid request document, with changes."""

    data: dict[str, Any] = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": KEY,
        "workflow_id": str(WORKFLOW_ID),
        "input": {"value": {"change": "rename"}},
    }

    data.update(changes)

    return data


def without(
    field: str,
) -> dict[str, Any]:
    """Return one valid request document without one field."""

    data = request_data()
    del data[field]

    return data


def rejection(
    data: JsonValue,
) -> JobRequestError:
    """Decode data that must be refused, and return the refusal."""

    with pytest.raises(JobRequestError) as raised:
        decode_job_request(data)

    return raised.value


def parse_rejection(
    content: str | bytes,
) -> JobRequestError:
    """Parse content that must be refused, and return the refusal."""

    with pytest.raises(JobRequestError) as raised:
        parse_job_request(content)

    return raised.value


# Accepted


def test_a_valid_request_decodes() -> None:
    request = decode_job_request(request_data())

    assert request.workflow_id == WORKFLOW_ID
    assert request.input == InlineInput(value={"change": "rename"})


def test_a_valid_request_parses_from_text_and_bytes() -> None:
    text = json.dumps(request_data())

    assert parse_job_request(text) == decode_job_request(request_data())
    assert parse_job_request(text.encode("utf-8")) == decode_job_request(request_data())


def test_a_byte_order_mark_is_ignored() -> None:
    text = json.dumps(request_data())

    assert parse_job_request("﻿" + text).idempotency_key == KEY
    assert parse_job_request(("﻿" + text).encode("utf-8")).idempotency_key == KEY


# Not a request at all


@pytest.mark.parametrize("data", [None, 1, "invoke", [request_data()]])
def test_a_request_must_be_an_object(
    data: JsonValue,
) -> None:
    refused = rejection(data)

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == "A job request must be a JSON object."
    assert refused.idempotency_key is None


def test_text_that_is_not_json_is_an_invalid_request() -> None:
    refused = parse_rejection('{"kind": "invoke",')

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message.startswith("A job request must be JSON: ")
    assert "line 1" in refused.error.message


def test_bytes_that_are_not_utf_8_are_an_invalid_request() -> None:
    refused = parse_rejection(b"\xff\xfe{}")

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == "A job request must be UTF-8 text."


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_numbers_are_refused(
    constant: str,
) -> None:
    text = json.dumps(request_data(caller_metadata={"weight": 0})).replace(
        '"weight": 0',
        f'"weight": {constant}',
    )

    refused = parse_rejection(text)

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert f"{constant} is not a JSON number" in refused.error.message


def test_empty_text_is_an_invalid_request() -> None:
    assert parse_rejection("").error.code is JobErrorCode.INVALID_REQUEST


# Kind


def test_a_request_must_name_its_kind() -> None:
    refused = rejection(without("kind"))

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == "A job request must name its kind."
    assert refused.error.metadata == {"supported_kinds": ["invoke"]}
    assert refused.idempotency_key == KEY


@pytest.mark.parametrize("kind", ["map", "INVOKE", "", 1, None, ["invoke"]])
def test_an_unknown_kind_is_an_invalid_request_naming_the_supported_kinds(
    kind: JsonValue,
) -> None:
    refused = rejection(request_data(kind=kind))

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == (
        f"Unknown job kind {json.dumps(kind)}; supported kinds: invoke."
    )
    assert refused.error.metadata == {"supported_kinds": ["invoke"]}
    assert refused.idempotency_key == KEY


# Version


def test_a_request_must_name_its_version() -> None:
    refused = rejection(without("version"))

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == "A job request must name its version."


@pytest.mark.parametrize("version", [1.0, "1", True, None, [1]])
def test_a_version_must_be_an_integer(
    version: JsonValue,
) -> None:
    refused = rejection(request_data(version=version))

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == (
        f"A job request's version must be an integer; got {json.dumps(version)}."
    )


@pytest.mark.parametrize("version", [0, 2, 99, -1])
def test_an_unsupported_version_names_the_supported_versions(
    version: int,
) -> None:
    refused = rejection(request_data(version=version))

    assert refused.error.code is JobErrorCode.UNSUPPORTED_VERSION
    assert refused.error.message == (
        f"Job version {version} is not supported; supported versions: 1."
    )
    assert refused.error.metadata == {"supported_versions": [1]}
    assert refused.idempotency_key == KEY


def test_a_later_version_is_reported_as_a_version_not_as_unknown_fields() -> None:
    later: dict[str, JsonValue] = {
        "kind": "invoke",
        "version": 2,
        "idempotency_key": KEY,
        "workflow": {"id": str(WORKFLOW_ID), "revision": 7},
        "inputs": [{"value": 1}],
        "deadline": "2026-12-31T00:00:00Z",
    }

    refused = rejection(later)

    assert refused.error.code is JobErrorCode.UNSUPPORTED_VERSION
    assert refused.idempotency_key == KEY


def test_the_kind_is_checked_before_the_version() -> None:
    refused = rejection(request_data(kind="map", version=2))

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.metadata == {"supported_kinds": ["invoke"]}


# The rest of the shape


@pytest.mark.parametrize(
    ("data", "field", "message"),
    [
        (without("workflow_id"), "workflow_id", "is required"),
        (without("input"), "input", "is required"),
        (without("idempotency_key"), "idempotency_key", "is required"),
        (request_data(priority="high"), "priority", "is not a field of this request"),
        (
            request_data(input={"value": 1, "uri": "file:///x.json"}),
            "input",
            EXCLUSIVE_KEYS_MESSAGE,
        ),
        (
            request_data(input={"uri": "file:///x.md"}),
            "input.media_type",
            "is required",
        ),
        (
            request_data(input={"value": 1, "encoding": "utf-8"}),
            "input.encoding",
            "is not a field of this request",
        ),
        (
            request_data(input={"value": 3, "media_type": "text/plain"}),
            "input",
            "An inline text/plain input must hold a string.",
        ),
        (
            request_data(idempotency_key=""),
            "idempotency_key",
            "An idempotency key must not be empty.",
        ),
    ],
)
def test_shape_problems_name_their_field(
    data: dict[str, Any],
    field: str,
    message: str,
) -> None:
    refused = rejection(data)

    assert refused.error.code is JobErrorCode.INVALID_REQUEST
    assert refused.error.message == f"The job request is not valid: {field}: {message}"
    assert refused.error.metadata == {"errors": [{"field": field, "message": message}]}


def test_every_shape_problem_is_reported() -> None:
    refused = rejection(
        request_data(
            workflow_id="not-a-uuid",
            caller_metadata="not an object",
        )
    )

    problems = refused.error.metadata["errors"]

    assert isinstance(problems, list)
    assert [problem["field"] for problem in problems if isinstance(problem, dict)] == [
        "workflow_id",
        "caller_metadata",
    ]
    assert refused.error.message.count("; ") == 1


def test_a_shape_problem_keeps_a_valid_key_for_the_result() -> None:
    assert rejection(without("workflow_id")).idempotency_key == KEY


def test_an_invalid_key_is_not_echoed() -> None:
    assert rejection(request_data(idempotency_key="a\nb")).idempotency_key is None
    assert rejection(request_data(idempotency_key=4711, version=2)).idempotency_key is None


# Reading keys


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"idempotency_key": KEY}, KEY),
        ({"idempotency_key": ""}, None),
        ({"idempotency_key": "x" * 256}, None),
        ({"idempotency_key": 4711}, None),
        ({}, None),
        ([KEY], None),
        (KEY, None),
    ],
)
def test_readable_idempotency_key(
    data: object,
    key: str | None,
) -> None:
    assert readable_idempotency_key(data) == key
