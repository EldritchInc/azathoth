"""Tests for tracing production invocations and jobs (ADR 0100)."""

import asyncio
from collections.abc import Mapping
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.inputs import InputProvenance
from azathoth.jobs import JobError, JobErrorCode, JobResult, JobStatus
from azathoth.telemetry import ATTRIBUTE_KEYS
from azathoth.telemetry.invocations import (
    traced_invocation,
    traced_job,
    traced_job_invoker,
)
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
)
from tests.telemetry.fakes import RecordingTelemetry

WORKFLOW_ID = UUID("f6a7b8c9-0d1e-4f2a-8b3c-5d6e7f8a9b01")

INVOCATION_ID = UUID("f6a7b8c9-0d1e-4f2a-8b3c-5d6e7f8a9b11")

KEY = "patient-0427-intake"

SECRET = "Jane Doe, DOB 1961-04-27, chart 0427"

DIGEST = "0" * 64

SUCCESS = ProductionInvocationSuccess(
    invocation_id=INVOCATION_ID,
    result={"summary": SECRET},
)

FAILURE = ProductionInvocationFailure(
    invocation_id=INVOCATION_ID,
    error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
    message=f"Step failed on {SECRET}.",
)


def assert_no_content(
    telemetry: RecordingTelemetry,
) -> None:
    """Assert no span carries anything but known attributes, and never the secret or key."""

    for span in telemetry.spans:
        assert set(span.attributes) <= ATTRIBUTE_KEYS
        assert SECRET not in repr(span.attributes)
        assert KEY not in repr(span.attributes)


# Invocations


def test_a_succeeded_invocation_names_itself_and_its_workflow() -> None:
    telemetry = RecordingTelemetry()

    with traced_invocation(telemetry, workflow_id=WORKFLOW_ID) as trace:
        trace.record(SUCCESS)

    (span,) = telemetry.spans

    assert span.name == "azathoth.invocation"
    assert span.ended
    assert span.error_type is None
    assert span.attributes == {
        "azathoth.workflow.id": str(WORKFLOW_ID),
        "azathoth.invocation.id": str(INVOCATION_ID),
        "azathoth.invocation.outcome": "succeeded",
    }
    assert_no_content(telemetry)


def test_a_failed_invocation_is_marked_failed_with_its_code_never_its_message() -> None:
    telemetry = RecordingTelemetry()

    with traced_invocation(telemetry, workflow_id=WORKFLOW_ID) as trace:
        trace.record(FAILURE)

    (span,) = telemetry.spans

    assert span.error_type == "workflow_execution_failed"
    assert span.attributes["azathoth.invocation.outcome"] == "workflow_execution_failed"
    assert span.attributes["azathoth.error.code"] == "workflow_execution_failed"
    assert_no_content(telemetry)


def test_the_invocation_span_is_current_inside_it() -> None:
    telemetry = RecordingTelemetry()

    with traced_invocation(telemetry, workflow_id=WORKFLOW_ID):
        inner = telemetry.start_span("azathoth.run")
        inner.end()

    invocation, run = telemetry.spans

    assert run.parent is invocation
    assert telemetry.trace_context() == {}


def test_an_exception_escaping_an_invocation_marks_it_by_type() -> None:
    telemetry = RecordingTelemetry()

    with (
        pytest.raises(LookupError),
        traced_invocation(telemetry, workflow_id=WORKFLOW_ID),
    ):
        raise LookupError(SECRET)

    (span,) = telemetry.spans

    assert span.error_type == "LookupError"
    assert span.ended


# Jobs


def job_result(
    status: JobStatus,
    *,
    error: JobErrorCode | None = None,
    replayed: bool = False,
) -> JobResult:
    """Create one job result under the test key."""

    return JobResult(
        idempotency_key=KEY,
        status=status,
        replayed=replayed,
        invocation_id=None if status is JobStatus.REJECTED else INVOCATION_ID,
        result={"summary": SECRET} if status is JobStatus.SUCCEEDED else None,
        error=JobError(code=error, message=f"About {SECRET}.") if error is not None else None,
    )


def test_a_succeeded_job_names_its_kind_status_and_invocation_never_its_key() -> None:
    telemetry = RecordingTelemetry()

    with traced_job(telemetry) as trace:
        trace.record(job_result(JobStatus.SUCCEEDED, replayed=True))

    (span,) = telemetry.spans

    assert span.name == "azathoth.job"
    assert span.error_type is None
    assert span.attributes == {
        "azathoth.job.kind": "invoke",
        "azathoth.job.version": 1,
        "azathoth.job.status": "succeeded",
        "azathoth.job.replayed": True,
        "azathoth.invocation.id": str(INVOCATION_ID),
    }
    assert_no_content(telemetry)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (JobStatus.FAILED, JobErrorCode.WORKFLOW_NOT_DEPLOYED),
        (JobStatus.REJECTED, JobErrorCode.INVALID_INPUT),
    ],
)
def test_a_job_that_did_not_succeed_is_marked_failed_with_its_code(
    status: JobStatus,
    code: JobErrorCode,
) -> None:
    telemetry = RecordingTelemetry()

    with traced_job(telemetry) as trace:
        trace.record(job_result(status, error=code))

    (span,) = telemetry.spans

    assert span.error_type == code.value
    assert span.attributes["azathoth.job.status"] == status.value
    assert span.attributes["azathoth.error.code"] == code.value
    assert_no_content(telemetry)


# The job invoker


def test_a_traced_invoker_traces_each_invocation_under_the_job() -> None:
    telemetry = RecordingTelemetry()
    calls: list[UUID] = []

    async def invoke(
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        calls.append(workflow_id)

        run = telemetry.start_span("azathoth.run")
        run.end()

        return FAILURE

    traced = traced_job_invoker(telemetry, invoke)

    with traced_job(telemetry):
        result = asyncio.run(
            traced(
                workflow_id=WORKFLOW_ID,
                payload={"note": SECRET},
                caller_metadata={},
                input_provenance=None,
                idempotency=InvocationIdempotency(key=KEY, request_digest=DIGEST),
            )
        )

    job, invocation, run = telemetry.spans

    assert result is FAILURE
    assert calls == [WORKFLOW_ID]
    assert invocation.parent is job
    assert run.parent is invocation
    assert invocation.error_type == "workflow_execution_failed"
    assert_no_content(telemetry)
