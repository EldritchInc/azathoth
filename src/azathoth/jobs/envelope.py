"""The versioned job envelope: one request and one result (ADR 0097)."""

from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from azathoth.inputs import WorkflowInputSource
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    validate_idempotency_key,
)

JOB_VERSION: Final = 1
"""The job envelope version this release speaks."""

SUPPORTED_JOB_VERSIONS: Final = (JOB_VERSION,)
"""Every job envelope version this release accepts."""


class JobKind(StrEnum):
    """What a job asks for. Azathoth 1.1 knows one kind."""

    INVOKE = "invoke"


SUPPORTED_JOB_KINDS: Final = tuple(kind.value for kind in JobKind)
"""Every job kind this release accepts."""


class JobStatus(StrEnum):
    """How one job request ended.

    `succeeded` and `failed` report an invocation with a terminal result.
    `rejected` means no invocation was recorded for the request. `incomplete`
    means the key's invocation exists but has no result yet.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"


class JobErrorCode(StrEnum):
    """Every code a job result's error may carry.

    The production invocation error codes come first, with the same values,
    so a failed job and a failed `workflow invoke` report the same code. The
    rest only the envelope produces.
    """

    WORKFLOW_NOT_DEPLOYED = "workflow_not_deployed"
    INVALID_INPUT = "invalid_input"
    MODEL_UNAVAILABLE = "model_unavailable"
    NO_APPROVED_MODEL_SUBSTITUTE = "no_approved_model_substitute"
    TOOL_UNAVAILABLE = "tool_unavailable"
    WORKFLOW_EXECUTION_FAILED = "workflow_execution_failed"
    TIMEOUT = "timeout"

    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_VERSION = "unsupported_version"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVOCATION_INCOMPLETE = "invocation_incomplete"


ENVELOPE_ERROR_CODES: Final = frozenset(
    {
        JobErrorCode.INVALID_REQUEST,
        JobErrorCode.UNSUPPORTED_VERSION,
        JobErrorCode.IDEMPOTENCY_CONFLICT,
        JobErrorCode.INVOCATION_INCOMPLETE,
    }
)
"""The codes only the envelope produces, never an invocation."""

REJECTION_ERROR_CODES: Final = frozenset(
    {
        JobErrorCode.INVALID_REQUEST,
        JobErrorCode.UNSUPPORTED_VERSION,
        JobErrorCode.IDEMPOTENCY_CONFLICT,
        JobErrorCode.INVALID_INPUT,
    }
)
"""The codes a rejected request may carry."""


def job_error_code(
    code: ProductionInvocationErrorCode,
) -> JobErrorCode:
    """Return the job error code with one production code's value."""

    return JobErrorCode(code.value)


class JobError(BaseModel):
    """Why a job did not succeed: a stable code, a message and metadata."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    code: JobErrorCode
    message: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )


class InvokeJobRequest(BaseModel):
    """A request to invoke one workflow against its active production state.

    The shape is closed. `kind` and `version` are required, and checked
    before the rest of a request by `decode_job_request`.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    kind: Literal["invoke"]
    version: Literal[1]
    idempotency_key: str
    workflow_id: UUID
    input: WorkflowInputSource
    caller_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )

    @field_validator("version", mode="before")
    @classmethod
    def require_integer_version(
        cls,
        version: object,
    ) -> object:
        """Refuse a version that is not a JSON integer, such as `1.0` or `true`."""

        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("A job request's version must be an integer.")

        return version

    @field_validator("idempotency_key")
    @classmethod
    def check_idempotency_key(
        cls,
        key: str,
    ) -> str:
        """Require a valid idempotency key."""

        return validate_idempotency_key(key)


class JobResult(BaseModel):
    """The outcome of one job request.

    The result always speaks the responder's own kind and version. Which
    fields are set follows from the status:

    - `succeeded`: an invocation, its result, and no error;
    - `failed`: an invocation and an error with a production code;
    - `rejected`: no invocation, and an error with a rejection code;
    - `incomplete`: a replayed invocation, and `invocation_incomplete`.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    kind: Literal["invoke"] = "invoke"
    version: Literal[1] = 1
    idempotency_key: str | None
    status: JobStatus
    replayed: bool = False
    invocation_id: UUID | None
    result: JsonValue = None
    error: JobError | None

    @model_validator(mode="after")
    def validate_status(
        self,
    ) -> "JobResult":
        """Require the fields each status sets, and only those."""

        if self.status is JobStatus.SUCCEEDED:
            if self.invocation_id is None:
                raise ValueError("A succeeded job names its invocation.")

            if self.error is not None:
                raise ValueError("A succeeded job carries no error.")

            return self

        if self.result is not None:
            raise ValueError(f"A {self.status.value} job carries no result.")

        if self.error is None:
            raise ValueError(f"A {self.status.value} job carries an error.")

        if self.status is JobStatus.FAILED:
            if self.invocation_id is None:
                raise ValueError("A failed job names its invocation.")

            if self.error.code in ENVELOPE_ERROR_CODES:
                raise ValueError(
                    f"A failed job carries a production error code, not {self.error.code.value!r}."
                )

        elif self.status is JobStatus.REJECTED:
            if self.invocation_id is not None:
                raise ValueError("A rejected job names no invocation.")

            if self.replayed:
                raise ValueError("A rejected job replays nothing.")

            if self.error.code not in REJECTION_ERROR_CODES:
                raise ValueError(
                    f"A rejected job cannot carry the {self.error.code.value!r} error code."
                )

        else:
            if self.invocation_id is None:
                raise ValueError("An incomplete job names its invocation.")

            if not self.replayed:
                raise ValueError("An incomplete job reports an earlier request's invocation.")

            if self.error.code is not JobErrorCode.INVOCATION_INCOMPLETE:
                raise ValueError("An incomplete job carries the 'invocation_incomplete' code.")

        return self


def job_result_from_invocation(
    result: ProductionInvocationResult,
    *,
    idempotency_key: str,
    replayed: bool = False,
) -> JobResult:
    """Return the job result reporting one terminal invocation result."""

    if isinstance(result, ProductionInvocationSuccess):
        return JobResult(
            idempotency_key=idempotency_key,
            status=JobStatus.SUCCEEDED,
            replayed=replayed,
            invocation_id=result.invocation_id,
            result=result.result,
            error=None,
        )

    assert isinstance(result, ProductionInvocationFailure)

    return JobResult(
        idempotency_key=idempotency_key,
        status=JobStatus.FAILED,
        replayed=replayed,
        invocation_id=result.invocation_id,
        error=JobError(
            code=job_error_code(result.error_code),
            message=result.message,
            metadata=dict(result.metadata),
        ),
    )


def incomplete_job_result(
    invocation_id: UUID,
    *,
    idempotency_key: str,
) -> JobResult:
    """Return the job result for a key whose invocation has no result yet."""

    return JobResult(
        idempotency_key=idempotency_key,
        status=JobStatus.INCOMPLETE,
        replayed=True,
        invocation_id=invocation_id,
        error=JobError(
            code=JobErrorCode.INVOCATION_INCOMPLETE,
            message=(
                f"Invocation {invocation_id} was started under this idempotency key "
                "and has no result yet; it was interrupted, or is still running."
            ),
        ),
    )


def rejected_job_result(
    error: JobError,
    *,
    idempotency_key: str | None,
) -> JobResult:
    """Return the job result for a request that recorded no invocation."""

    return JobResult(
        idempotency_key=idempotency_key,
        status=JobStatus.REJECTED,
        invocation_id=None,
        error=error,
    )


__all__ = [
    "ENVELOPE_ERROR_CODES",
    "JOB_VERSION",
    "REJECTION_ERROR_CODES",
    "SUPPORTED_JOB_KINDS",
    "SUPPORTED_JOB_VERSIONS",
    "InvokeJobRequest",
    "JobError",
    "JobErrorCode",
    "JobKind",
    "JobResult",
    "JobStatus",
    "incomplete_job_result",
    "job_error_code",
    "job_result_from_invocation",
    "rejected_job_result",
]
