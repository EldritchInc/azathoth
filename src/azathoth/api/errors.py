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


class NotFoundError(ApiError):
    """The workflow, tool or benchmark a call names is not configured."""

    code: ClassVar[str] = "not_found"


class RevisionNotFoundError(NotFoundError):
    """The component is configured, but has no revision with the number named."""

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


class ProviderConfigurationError(ApiError):
    """A provider is turned on in a way that cannot be used, such as Bedrock without boto3."""

    code: ClassVar[str] = "provider_configuration"


class ProviderUnavailableError(ApiError):
    """A configured provider could not be asked which models it serves."""

    code: ClassVar[str] = "provider_unavailable"


class RunNotStartedError(ApiError):
    """A run could not start: no executable candidate of the workflow could be made."""

    code: ClassVar[str] = "run_not_started"


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
    "ConflictError",
    "InstanceClosedError",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
    "InvalidArgumentError",
    "InvalidDocumentError",
    "ModelInUseError",
    "NotFoundError",
    "ProviderConfigurationError",
    "ProviderUnavailableError",
    "RevisionNotFoundError",
    "RunCancelledError",
    "RunNotStartedError",
]
