"""What `get_invocation` returns: an invocation's result and its evidence (ADR 0111).

It is what `invocation show` reports, as data: the invocation, its input,
its outcome, who made it, and its run, with each step's status, attempts and
confidence. An invocation whose run has not finished names the run its
journal records, without steps.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.cli.rendering.invocation_history import production_invocation_input
from azathoth.jobs import JobErrorCode, job_error_code
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    WorkflowRun,
    WorkflowStepStatus,
)


class InvocationStatus(StrEnum):
    """Where one invocation stands."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class InvocationError(BaseModel):
    """Why one invocation failed: the job envelope's code, a message and metadata."""

    model_config = ConfigDict(frozen=True)

    code: JobErrorCode
    message: str
    metadata: dict[str, JsonValue]


class StepEvidence(BaseModel):
    """One step of a finished run."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    status: WorkflowStepStatus
    attempts: int
    confidence: float | None


class RunEvidence(BaseModel):
    """The run behind one invocation.

    A run that has not finished names only its ID and how often it was
    resumed; `finished` is false and its steps are empty.
    """

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    finished: bool
    resumes: int
    workflow_revision: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    halted: bool | None = None
    steps: tuple[StepEvidence, ...] = ()


class InvocationEvidence(BaseModel):
    """One invocation, its outcome, who made it, and its run."""

    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    workflow_id: UUID
    tool: str
    created_at: datetime
    status: InvocationStatus
    result: JsonValue = None
    error: InvocationError | None = None
    idempotency_key: str | None
    input: JsonValue
    caller: dict[str, JsonValue]
    run: RunEvidence | None


def invocation_evidence(
    invocation: ProductionInvocation,
    *,
    tool: str,
    result: ProductionInvocationResult | None,
    run_id: UUID | None,
    run: WorkflowRun | None,
    resumes: int,
) -> InvocationEvidence:
    """Return the evidence of one invocation, from what its repositories recorded."""

    status = InvocationStatus.INCOMPLETE
    value: JsonValue = None
    error: InvocationError | None = None

    if isinstance(result, ProductionInvocationSuccess):
        status = InvocationStatus.SUCCEEDED
        value = result.result

    if isinstance(result, ProductionInvocationFailure):
        status = InvocationStatus.FAILED
        error = InvocationError(
            code=job_error_code(result.error_code),
            message=result.message,
            metadata=dict(result.metadata),
        )

    return InvocationEvidence(
        invocation_id=invocation.id,
        workflow_id=invocation.workflow_id,
        tool=tool,
        created_at=invocation.created_at,
        status=status,
        result=value,
        error=error,
        idempotency_key=invocation.idempotency.key if invocation.idempotency else None,
        input=production_invocation_input(invocation),
        caller=dict(invocation.caller_metadata),
        run=_run_evidence(run_id, run, resumes),
    )


def _run_evidence(
    run_id: UUID | None,
    run: WorkflowRun | None,
    resumes: int,
) -> RunEvidence | None:
    """Return the evidence of an invocation's run, finished or not, if it has one."""

    if run is not None:
        return RunEvidence(
            run_id=run.id,
            finished=True,
            resumes=resumes,
            workflow_revision=run.workflow_revision,
            started_at=run.started_at,
            completed_at=run.completed_at,
            halted=run.halted,
            steps=tuple(
                StepEvidence(
                    step_id=step.step_id,
                    status=step.status,
                    attempts=len(step.attempts),
                    confidence=step.confidence,
                )
                for step in run.steps
            ),
        )

    if run_id is not None:
        return RunEvidence(run_id=run_id, finished=False, resumes=resumes)

    return None


__all__ = [
    "InvocationError",
    "InvocationEvidence",
    "InvocationStatus",
    "RunEvidence",
    "StepEvidence",
    "invocation_evidence",
]
