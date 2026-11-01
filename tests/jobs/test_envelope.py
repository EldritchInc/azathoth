"""Tests for the job envelope's request and result models (ADR 0097)."""

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.inputs import InlineInput, ReferenceInput
from azathoth.jobs import (
    ENVELOPE_ERROR_CODES,
    JOB_VERSION,
    REJECTION_ERROR_CODES,
    SUPPORTED_JOB_KINDS,
    SUPPORTED_JOB_VERSIONS,
    InvokeJobRequest,
    JobError,
    JobErrorCode,
    JobKind,
    JobResult,
    JobStatus,
    decode_job_request,
    incomplete_job_result,
    job_error_code,
    job_result_from_invocation,
    rejected_job_result,
)
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
)

ADR = (
    Path(__file__).parents[2]
    / "docs"
    / "adrs"
    / ("0097-carry-invocations-in-a-versioned-job-envelope.md")
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")

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
        "caller_metadata": {"ticket": "OPS-12"},
    }

    data.update(changes)

    return data


def error(
    code: JobErrorCode,
) -> JobError:
    """Create one job error with a placeholder message."""

    return JobError(code=code, message="Something happened.")


# Codes, kinds and versions


def test_this_release_speaks_version_1_of_the_invoke_kind() -> None:
    assert JOB_VERSION == 1
    assert SUPPORTED_JOB_VERSIONS == (1,)
    assert SUPPORTED_JOB_KINDS == ("invoke",)
    assert tuple(JobKind) == (JobKind.INVOKE,)


def test_job_statuses_are_stable() -> None:
    assert [status.value for status in JobStatus] == [
        "succeeded",
        "failed",
        "rejected",
        "incomplete",
    ]


def test_job_error_codes_include_every_production_code() -> None:
    production = {code.value for code in ProductionInvocationErrorCode}

    assert production <= {code.value for code in JobErrorCode}


def test_only_the_four_envelope_codes_are_added() -> None:
    production = {code.value for code in ProductionInvocationErrorCode}

    added = {code.value for code in JobErrorCode} - production

    assert added == {
        "invalid_request",
        "unsupported_version",
        "idempotency_conflict",
        "invocation_incomplete",
    }

    assert {code.value for code in ENVELOPE_ERROR_CODES} == added


def test_rejections_carry_envelope_codes_or_invalid_input() -> None:
    assert {
        JobErrorCode.INVALID_REQUEST,
        JobErrorCode.UNSUPPORTED_VERSION,
        JobErrorCode.IDEMPOTENCY_CONFLICT,
        JobErrorCode.INVALID_INPUT,
    } == REJECTION_ERROR_CODES


@pytest.mark.parametrize("code", list(ProductionInvocationErrorCode))
def test_every_production_code_maps_to_the_job_code_of_its_value(
    code: ProductionInvocationErrorCode,
) -> None:
    assert job_error_code(code).value == code.value


def test_job_error_defaults_to_empty_metadata_and_requires_a_message() -> None:
    assert error(JobErrorCode.TIMEOUT).metadata == {}

    with pytest.raises(ValidationError):
        JobError(code=JobErrorCode.TIMEOUT, message="")


# Requests


def test_a_request_holds_an_inline_input() -> None:
    request = InvokeJobRequest.model_validate(request_data())

    assert request.kind == "invoke"
    assert request.version == 1
    assert request.idempotency_key == KEY
    assert request.workflow_id == WORKFLOW_ID
    assert request.input == InlineInput(value={"change": "rename"})
    assert request.caller_metadata == {"ticket": "OPS-12"}


def test_a_request_holds_a_reference_input() -> None:
    request = InvokeJobRequest.model_validate(
        request_data(
            input={"uri": "file:///Users/you/change.json", "media_type": "application/json"},
        )
    )

    assert request.input == ReferenceInput(
        uri="file:///Users/you/change.json",
        media_type="application/json",
    )


def test_caller_metadata_defaults_to_empty() -> None:
    data = request_data()
    del data["caller_metadata"]

    assert InvokeJobRequest.model_validate(data).caller_metadata == {}


def test_a_request_round_trips_through_json() -> None:
    request = InvokeJobRequest.model_validate(request_data())

    assert InvokeJobRequest.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "map"},
        {"version": 2},
        {"version": 1.0},
        {"version": True},
        {"version": "1"},
        {"idempotency_key": ""},
        {"idempotency_key": "x" * 256},
        {"idempotency_key": "a\nb"},
        {"idempotency_key": 4711},
        {"workflow_id": "not-a-uuid"},
        {"input": {"value": 1, "uri": "file:///x.json"}},
        {"input": {}},
        {"input": {"uri": "file:///x.md"}},
        {"input": {"value": 3, "media_type": "text/plain"}},
        {"input": "just a string"},
        {"caller_metadata": ["not", "an", "object"]},
        {"priority": "high"},
    ],
)
def test_requests_outside_the_shape_are_refused(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        InvokeJobRequest.model_validate(request_data(**changes))


@pytest.mark.parametrize("field", ["kind", "version", "idempotency_key", "workflow_id", "input"])
def test_every_required_request_field_is_required(
    field: str,
) -> None:
    data = request_data()
    del data[field]

    with pytest.raises(ValidationError):
        InvokeJobRequest.model_validate(data)


def test_a_request_is_immutable() -> None:
    request = InvokeJobRequest.model_validate(request_data())

    with pytest.raises(ValidationError, match="Instance is frozen"):
        request.__setattr__("idempotency_key", "other")


# Results


def test_a_succeeded_result_dumps_every_field() -> None:
    result = JobResult(
        idempotency_key=KEY,
        status=JobStatus.SUCCEEDED,
        invocation_id=INVOCATION_ID,
        result={"verdict": "approve"},
        error=None,
    )

    assert result.model_dump(mode="json") == {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": KEY,
        "status": "succeeded",
        "replayed": False,
        "invocation_id": str(INVOCATION_ID),
        "result": {"verdict": "approve"},
        "error": None,
    }


def test_a_succeeded_result_may_hold_a_null_result() -> None:
    result = JobResult(
        idempotency_key=KEY,
        status=JobStatus.SUCCEEDED,
        invocation_id=INVOCATION_ID,
        error=None,
    )

    assert result.result is None


def test_a_result_round_trips_through_json() -> None:
    result = JobResult(
        idempotency_key=KEY,
        status=JobStatus.FAILED,
        replayed=True,
        invocation_id=INVOCATION_ID,
        error=JobError(
            code=JobErrorCode.TIMEOUT,
            message="The workflow timed out.",
            metadata={"seconds": 30},
        ),
    )

    assert JobResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"status": "succeeded", "invocation_id": None, "error": None},
            "A succeeded job names its invocation",
        ),
        (
            {
                "status": "succeeded",
                "invocation_id": INVOCATION_ID,
                "error": error(JobErrorCode.TIMEOUT),
            },
            "A succeeded job carries no error",
        ),
        (
            {"status": "failed", "invocation_id": INVOCATION_ID, "error": None},
            "A failed job carries an error",
        ),
        (
            {
                "status": "failed",
                "invocation_id": None,
                "error": error(JobErrorCode.TIMEOUT),
            },
            "A failed job names its invocation",
        ),
        (
            {
                "status": "failed",
                "invocation_id": INVOCATION_ID,
                "result": "partial",
                "error": error(JobErrorCode.TIMEOUT),
            },
            "A failed job carries no result",
        ),
        (
            {
                "status": "failed",
                "invocation_id": INVOCATION_ID,
                "error": error(JobErrorCode.IDEMPOTENCY_CONFLICT),
            },
            "A failed job carries a production error code",
        ),
        (
            {
                "status": "rejected",
                "invocation_id": INVOCATION_ID,
                "error": error(JobErrorCode.INVALID_REQUEST),
            },
            "A rejected job names no invocation",
        ),
        (
            {
                "status": "rejected",
                "invocation_id": None,
                "replayed": True,
                "error": error(JobErrorCode.INVALID_REQUEST),
            },
            "A rejected job replays nothing",
        ),
        (
            {
                "status": "rejected",
                "invocation_id": None,
                "error": error(JobErrorCode.TIMEOUT),
            },
            "A rejected job cannot carry the 'timeout' error code",
        ),
        (
            {
                "status": "incomplete",
                "invocation_id": None,
                "replayed": True,
                "error": error(JobErrorCode.INVOCATION_INCOMPLETE),
            },
            "An incomplete job names its invocation",
        ),
        (
            {
                "status": "incomplete",
                "invocation_id": INVOCATION_ID,
                "error": error(JobErrorCode.INVOCATION_INCOMPLETE),
            },
            "An incomplete job reports an earlier request's invocation",
        ),
        (
            {
                "status": "incomplete",
                "invocation_id": INVOCATION_ID,
                "replayed": True,
                "error": error(JobErrorCode.TIMEOUT),
            },
            "An incomplete job carries the 'invocation_incomplete' code",
        ),
    ],
)
def test_results_hold_exactly_the_fields_their_status_sets(
    fields: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        JobResult.model_validate({"idempotency_key": KEY, **fields})


def test_a_result_speaks_only_this_releases_kind_and_version() -> None:
    with pytest.raises(ValidationError):
        JobResult.model_validate(
            {
                "kind": "invoke",
                "version": 2,
                "idempotency_key": KEY,
                "status": "succeeded",
                "invocation_id": str(INVOCATION_ID),
                "error": None,
            }
        )


def test_a_result_shape_is_closed() -> None:
    with pytest.raises(ValidationError):
        JobResult.model_validate(
            {
                "idempotency_key": KEY,
                "status": "succeeded",
                "invocation_id": str(INVOCATION_ID),
                "error": None,
                "duration_seconds": 3,
            }
        )


# Building results


def test_a_production_success_becomes_a_succeeded_result() -> None:
    result = job_result_from_invocation(
        ProductionInvocationSuccess(
            invocation_id=INVOCATION_ID,
            result={"verdict": "approve"},
        ),
        idempotency_key=KEY,
    )

    assert result == JobResult(
        idempotency_key=KEY,
        status=JobStatus.SUCCEEDED,
        replayed=False,
        invocation_id=INVOCATION_ID,
        result={"verdict": "approve"},
        error=None,
    )


def test_a_production_failure_becomes_a_failed_result_with_the_same_code() -> None:
    result = job_result_from_invocation(
        ProductionInvocationFailure(
            invocation_id=INVOCATION_ID,
            error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
            message="The primary model is unavailable.",
            metadata={"model": "test-provider/production-model"},
        ),
        idempotency_key=KEY,
        replayed=True,
    )

    assert result == JobResult(
        idempotency_key=KEY,
        status=JobStatus.FAILED,
        replayed=True,
        invocation_id=INVOCATION_ID,
        error=JobError(
            code=JobErrorCode.MODEL_UNAVAILABLE,
            message="The primary model is unavailable.",
            metadata={"model": "test-provider/production-model"},
        ),
    )


def test_an_incomplete_result_is_a_replay_naming_its_invocation() -> None:
    result = incomplete_job_result(INVOCATION_ID, idempotency_key=KEY)

    assert result.status is JobStatus.INCOMPLETE
    assert result.replayed is True
    assert result.invocation_id == INVOCATION_ID
    assert result.result is None
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVOCATION_INCOMPLETE
    assert str(INVOCATION_ID) in result.error.message


@pytest.mark.parametrize("key", [KEY, None])
def test_a_rejected_result_names_no_invocation(
    key: str | None,
) -> None:
    result = rejected_job_result(
        error(JobErrorCode.IDEMPOTENCY_CONFLICT),
        idempotency_key=key,
    )

    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key == key
    assert result.invocation_id is None
    assert result.replayed is False


# The ADR's examples


def adr_json_block(
    heading: str,
) -> str:
    """Return the first JSON block after one heading of ADR 0097."""

    text = ADR.read_text(encoding="utf-8")
    section = text.split(f"### {heading}\n", 1)[1]
    matched = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)

    assert matched is not None

    return matched.group(1).replace("<UUID>", str(WORKFLOW_ID))


def test_the_adrs_request_example_decodes() -> None:
    request = decode_job_request(json.loads(adr_json_block("The request")))

    assert request.idempotency_key == KEY
    assert isinstance(request.input, ReferenceInput)


def test_the_adrs_result_example_validates() -> None:
    result = JobResult.model_validate_json(adr_json_block("The result"))

    assert result.status is JobStatus.SUCCEEDED
    assert result.idempotency_key == KEY
