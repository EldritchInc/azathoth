"""The errors the service API raises (ADR 0120).

Every error the API raises on purpose is an `ApiError`. Each kind carries a
`code`, a short stable name that a caller, such as a local UI server, can
map to a response without parsing the message. Messages are exact and
documented, and say what to do next where there is something to do.
"""

from typing import ClassVar, Final

from azathoth.api.models import ProductionDependent

CLOSED_MESSAGE: Final = "This Azathoth instance is closed."

CANCELLED_MESSAGE: Final = "The run was cancelled."


class ApiError(Exception):
    """Base class of every error the service API raises on purpose."""

    code: ClassVar[str] = "error"
    """The stable name of this kind of error."""


class InstanceNotFoundError(ApiError):
    """The SQLite database file to open does not exist.

    Opening never creates a database: `azathoth init` does.
    """

    code: ClassVar[str] = "instance_not_found"


class InstanceUnavailableError(ApiError):
    """The database cannot be used here: PostgreSQL without the `postgres` extra."""

    code: ClassVar[str] = "instance_unavailable"


class InstanceSchemaError(ApiError):
    """The PostgreSQL database does not hold this Azathoth's schema."""

    code: ClassVar[str] = "instance_schema"


class InvalidArgumentError(ApiError, ValueError):
    """A call was given an argument it cannot use, such as a history limit below 1."""

    code: ClassVar[str] = "invalid_argument"


class InvalidDocumentError(InvalidArgumentError):
    """A document to import is not a valid workflow, tool or benchmark document."""

    code: ClassVar[str] = "invalid_document"


class InvalidAuthorError(InvalidArgumentError):
    """Who is importing was given in the wrong form, or could not be told (ADR 0122)."""

    code: ClassVar[str] = "invalid_author"


class NotFoundError(ApiError):
    """The workflow, tool, benchmark or named remote a call names is not configured."""

    code: ClassVar[str] = "not_found"


class RevisionNotFoundError(NotFoundError):
    """The component is configured, but has no revision with the number or digest named."""

    code: ClassVar[str] = "revision_not_found"


class ConflictError(ApiError):
    """A change was refused because of the state it would change, such as a duplicate."""

    code: ClassVar[str] = "conflict"


class ModelInUseError(ConflictError):
    """A model was kept in the portfolio because active production uses it.

    `dependents` names the workflows and steps that use it.
    """

    code: ClassVar[str] = "model_in_use"

    def __init__(
        self,
        message: str,
        *,
        dependents: tuple[ProductionDependent, ...],
    ) -> None:
        super().__init__(message)
        self.dependents = dependents


class PermissionDeniedError(ApiError):
    """A remote's policy refused the caller what a call asks (ADR 0127).

    Its message is the policy's reason, which says who may not do what, and
    why. A remote answers it with 403. It is never a `NotFoundError`, so a
    caller told no is never told that the thing it asked for is missing.
    """

    code: ClassVar[str] = "permission_denied"


class ProviderConfigurationError(ApiError):
    """A provider is turned on in a way that cannot be used, such as Bedrock without boto3."""

    code: ClassVar[str] = "provider_configuration"


class ProviderUnavailableError(ApiError):
    """A configured provider could not be asked which models it serves."""

    code: ClassVar[str] = "provider_unavailable"


class WorkflowResultMissingError(ApiError):
    """A workflow declares no result, so it cannot be promoted (ADR 0128)."""

    code: ClassVar[str] = "workflow_result_missing"


class ExperimentNotFoundError(NotFoundError):
    """No optimization experiment has the ID named (ADR 0128)."""

    code: ClassVar[str] = "experiment_not_found"


class CandidateUnavailableError(ApiError):
    """No candidate of a workflow could be made with the models authorized now (ADR 0128)."""

    code: ClassVar[str] = "candidate_unavailable"


class CandidateRebuildError(CandidateUnavailableError):
    """An experiment's winner cannot be rebuilt from the workflow's latest revision (ADR 0128)."""

    code: ClassVar[str] = "candidate_rebuild"


class NothingToRollBackToError(ConflictError):
    """There is no earlier production revision, or the one named is already active (ADR 0128)."""

    code: ClassVar[str] = "nothing_to_roll_back_to"


class ModelNotAuthorizedError(ConflictError):
    """A model a change needs is not one the portfolio authorizes.

    A rollback's step has no model the portfolio still authorizes (ADR 0128),
    or a judge to add is not authorized (ADR 0129).
    """

    code: ClassVar[str] = "model_not_authorized"


class ContentUnavailableError(ApiError):
    """Content a call reads is not in the content store, or is not what it should be.

    A run's record of citation checks the store no longer holds, or holds
    something else under its digest, cannot be exported (ADR 0129).
    """

    code: ClassVar[str] = "content_unavailable"


class RunNotStartedError(ApiError):
    """A run could not start: no executable candidate of the workflow could be made."""

    code: ClassVar[str] = "run_not_started"


class RunNotResumableError(ConflictError):
    """A run cannot be resumed (ADR 0129).

    It has finished, executes a production invocation, which resumes as its
    invocation, is still held by another process, or its journal cannot be
    resumed with the revision it started from.
    """

    code: ClassVar[str] = "run_not_resumable"


class RunCancelledError(ApiError):
    """A run was stopped through its cancellation token before it finished.

    Nothing is kept as a finished run; what its journal recorded can be
    resumed, as for a run that was interrupted.
    """

    code: ClassVar[str] = "run_cancelled"

    def __init__(
        self,
    ) -> None:
        super().__init__(CANCELLED_MESSAGE)


class JudgeUnavailableError(ConflictError):
    """A benchmark's semantic cases need a judge the rotation cannot give (ADRs 0074 and 0130).

    No judge is configured, or none may judge the cases now, being no longer
    authorized or served, or not allowed their label; or a judge failed.
    """

    code: ClassVar[str] = "judge_unavailable"


class RemoteUnreachableError(ApiError):
    """A remote could not be reached, or answered as no Azathoth remote does (ADR 0124)."""

    code: ClassVar[str] = "remote_unreachable"


class RemoteProtocolError(ApiError):
    """A remote speaks another protocol version; nothing was sent to it."""

    code: ClassVar[str] = "remote_protocol"


class RemoteRefusedError(ApiError):
    """A remote refused a push or pull, or what it sent cannot be kept here, as the message says."""

    code: ClassVar[str] = "remote_refused"


class RemoteDivergedError(ConflictError):
    """A remote refused a push whose lineage has diverged there; pull first, then push again."""

    code: ClassVar[str] = "remote_diverged"


class McpUnavailableError(ApiError):
    """An MCP server could not be reached, listed or used to make a tool (ADR 0133).

    It failed the caller, not the person: a remote answers it with 502.
    """

    code: ClassVar[str] = "mcp_unavailable"


class InstanceClosedError(ApiError):
    """A call was made on an instance that was already closed."""

    code: ClassVar[str] = "instance_closed"

    def __init__(
        self,
    ) -> None:
        super().__init__(CLOSED_MESSAGE)


__all__ = [
    "CANCELLED_MESSAGE",
    "CLOSED_MESSAGE",
    "ApiError",
    "CandidateRebuildError",
    "CandidateUnavailableError",
    "ConflictError",
    "ExperimentNotFoundError",
    "InstanceClosedError",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
    "InvalidArgumentError",
    "InvalidAuthorError",
    "InvalidDocumentError",
    "JudgeUnavailableError",
    "McpUnavailableError",
    "ModelInUseError",
    "ModelNotAuthorizedError",
    "NotFoundError",
    "NothingToRollBackToError",
    "PermissionDeniedError",
    "ProviderConfigurationError",
    "ProviderUnavailableError",
    "RemoteDivergedError",
    "RemoteProtocolError",
    "RemoteRefusedError",
    "RemoteUnreachableError",
    "RevisionNotFoundError",
    "RunCancelledError",
    "RunNotStartedError",
    "WorkflowResultMissingError",
]
