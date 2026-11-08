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

from azathoth import api
from azathoth.jobs import JobErrorCode
from azathoth.workflows import WorkflowStepStatus


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
    detail: api.InvocationDetail,
    *,
    tool: str,
) -> InvocationEvidence:
    """Return the evidence of one invocation, as the service API reads it back."""

    return InvocationEvidence(
        invocation_id=detail.invocation_id,
        workflow_id=detail.workflow_id,
        tool=tool,
        created_at=detail.created_at,
        status=InvocationStatus(detail.status),
        result=detail.result,
        error=(
            InvocationError(
                code=JobErrorCode(detail.error.code),
                message=detail.error.message,
                metadata=dict(detail.error.metadata),
            )
            if detail.error is not None
            else None
        ),
        idempotency_key=detail.idempotency_key,
        input=detail.input,
        caller=dict(detail.caller_metadata),
        run=_run_evidence(detail.run),
    )


def _run_evidence(
    run: api.InvocationRun | None,
) -> RunEvidence | None:
    """Return the evidence of an invocation's run, finished or not, if it has one."""

    if run is None:
        return None

    return RunEvidence(
        run_id=run.run_id,
        finished=run.finished,
        resumes=run.resumes,
        workflow_revision=run.workflow_revision,
        started_at=run.started_at,
        completed_at=run.completed_at,
        halted=run.halted,
        steps=tuple(
            StepEvidence(
                step_id=step.step_id,
                status=WorkflowStepStatus(step.status),
                attempts=step.attempts,
                confidence=step.confidence,
            )
            for step in run.steps
        ),
    )


__all__ = [
    "InvocationError",
    "InvocationEvidence",
    "InvocationStatus",
    "RunEvidence",
    "StepEvidence",
    "invocation_evidence",
]
