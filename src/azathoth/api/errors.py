"""The errors the service API raises (ADR 0120).

Every error the API raises on purpose is an `ApiError`. Each kind carries a
`code`, a short stable name that a caller, such as a local UI server, can
map to a response without parsing the message. Messages are exact and
documented, and say what to do next where there is something to do.
"""

from typing import ClassVar, Final

CLOSED_MESSAGE: Final = "This Azathoth instance is closed."


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


class InstanceClosedError(ApiError):
    """A call was made on an instance that was already closed."""

    code: ClassVar[str] = "instance_closed"

    def __init__(
        self,
    ) -> None:
        super().__init__(CLOSED_MESSAGE)


__all__ = [
    "CLOSED_MESSAGE",
    "ApiError",
    "InstanceClosedError",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
]
