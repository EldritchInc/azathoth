"""Tracing production invocations and jobs (ADR 0100).

An invocation is one `azathoth.invocation` span, and a job one `azathoth.job`
span. Each is current while it runs, so the run an invocation executes, and
the invocation a job starts, are traced under it.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue

from azathoth.inputs import InputProvenance
from azathoth.jobs import JobInvoker, JobResult, JobStatus
from azathoth.telemetry.api import Telemetry, TelemetrySpan, traced
from azathoth.telemetry.attributes import invocation_attributes, job_attributes
from azathoth.telemetry.conventions import INVOCATION_SPAN, JOB_SPAN, WORKFLOW_ID
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationFailure,
    ProductionInvocationResult,
)


@dataclass(frozen=True)
class InvocationTrace:
    """The span of one production invocation."""

    span: TelemetrySpan
    workflow_id: UUID

    def record(
        self,
        result: ProductionInvocationResult,
    ) -> None:
        """Describe the span with the invocation's identity and outcome.

        A failed invocation is marked failed with its error code.
        """

        self.span.set_attributes(
            invocation_attributes(
                result,
                workflow_id=self.workflow_id,
            )
        )

        if isinstance(result, ProductionInvocationFailure):
            self.span.set_error(result.error_code.value)


@contextmanager
def traced_invocation(
    telemetry: Telemetry,
    *,
    workflow_id: UUID,
) -> Iterator[InvocationTrace]:
    """Run a block inside one current invocation span.

    Pass the invocation's result to `record`. An exception escaping the
    block marks the span failed with its type, and is raised again.
    """

    with traced(telemetry, INVOCATION_SPAN, {WORKFLOW_ID: str(workflow_id)}) as span:
        yield InvocationTrace(
            span=span,
            workflow_id=workflow_id,
        )


@dataclass(frozen=True)
class JobTrace:
    """The span of one job."""

    span: TelemetrySpan

    def record(
        self,
        result: JobResult,
    ) -> None:
        """Describe the span with the job's outcome, never its idempotency key.

        A job that did not succeed is marked failed with its error code, or,
        when it has none, its status.
        """

        self.span.set_attributes(job_attributes(result))

        if result.status is JobStatus.SUCCEEDED:
            return

        self.span.set_error(
            result.error.code.value if result.error is not None else result.status.value
        )


@contextmanager
def traced_job(
    telemetry: Telemetry,
) -> Iterator[JobTrace]:
    """Run a block inside one current job span.

    Pass the job's result to `record`. An exception escaping the block marks
    the span failed with its type, and is raised again.
    """

    with traced(telemetry, JOB_SPAN) as span:
        yield JobTrace(span=span)


def traced_job_invoker(
    telemetry: Telemetry,
    invoke: JobInvoker,
) -> JobInvoker:
    """Return an invoker that traces each invocation it makes under the current span."""

    async def traced_invoke(
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        with traced_invocation(telemetry, workflow_id=workflow_id) as trace:
            result = await invoke(
                workflow_id=workflow_id,
                payload=payload,
                caller_metadata=caller_metadata,
                input_provenance=input_provenance,
                idempotency=idempotency,
            )

            trace.record(result)

        return result

    return traced_invoke


__all__ = [
    "InvocationTrace",
    "JobTrace",
    "traced_invocation",
    "traced_job",
    "traced_job_invoker",
]
