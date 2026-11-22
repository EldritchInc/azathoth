"""How a remote refuses a call, and the error a client reads back (ADR 0137).

A service route refuses with a `Refusal`: `{"error": "<MESSAGE>", "code":
"<CODE>"}`. One made of an `ApiError` names, in `kinds`, the code of the
error's kind and of each kind it descends from, nearest first, and a
`ModelInUseError` carries its `dependents`. A refusal the remote makes
itself, before any call, names no kinds.

`api_error` turns a refusal back into the error a local instance would have
raised, of the nearest kind this Azathoth knows: a newer remote's new kind
of `NotFoundError` is still read as a `NotFoundError`. A refusal of no kind
this Azathoth knows, such as `unauthenticated`, is a `RemoteRefusedError`
carrying its status and code, or a `RemoteUnavailableError` when the remote
answered 503, since it may answer later.

This module needs no web framework, so a client reads refusals with it too.
"""

from collections.abc import Callable, Iterator, Mapping
from http import HTTPStatus
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from azathoth.api import errors
from azathoth.api.errors import (
    ApiError,
    InstanceClosedError,
    ModelInUseError,
    RemoteRefusedError,
    RemoteUnavailableError,
    RunCancelledError,
)
from azathoth.api.models import ProductionDependent


class Refusal(BaseModel):
    """What a service route answers a call it refuses with.

    Fields a newer remote adds are ignored, so an older client still reads
    the message and the nearest kind it knows.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    error: str

    code: str = Field(
        min_length=1,
    )

    kinds: tuple[str, ...] = Field(
        default=(),
        description="The code of the error's kind and of each it descends from, nearest first.",
    )

    dependents: tuple[ProductionDependent, ...] | None = Field(
        default=None,
        description="The workflows that use a model kept in the portfolio, for `model_in_use`.",
    )


def _api_error_kinds() -> Iterator[type[ApiError]]:
    """Yield every kind of `ApiError` the service API defines, but `ApiError` itself."""

    waiting = list(ApiError.__subclasses__())

    while waiting:
        kind = waiting.pop(0)
        waiting.extend(kind.__subclasses__())

        if kind.__module__ == errors.__name__:
            yield kind


REFUSED_KINDS: Final[Mapping[str, type[ApiError]]] = {
    kind.code: kind for kind in _api_error_kinds()
}
"""Each kind of `ApiError` the service API defines, by its code, as a client rebuilds them."""

Rebuild = Callable[[Refusal, int], ApiError]

REBUILT_WITH: Final[Mapping[type[ApiError], Rebuild]] = {
    ModelInUseError: lambda refused, status: ModelInUseError(
        refused.error,
        dependents=refused.dependents or (),
    ),
    RunCancelledError: lambda refused, status: RunCancelledError(),
    InstanceClosedError: lambda refused, status: InstanceClosedError(),
    RemoteRefusedError: lambda refused, status: RemoteRefusedError(
        refused.error,
        status=status,
        refusal=refused.code,
    ),
    RemoteUnavailableError: lambda refused, status: RemoteUnavailableError(
        refused.error,
        status=status,
        refusal=refused.code,
    ),
}
"""How each kind that is not made of its message alone is rebuilt.

`RunCancelledError` and `InstanceClosedError` always say the same, so they
are made as they are raised.
"""


def refusal(
    error: ApiError,
) -> Refusal:
    """Return what a service route refuses a call with that raised an `ApiError`."""

    kinds = dict.fromkeys(kind.code for kind in type(error).__mro__ if issubclass(kind, ApiError))

    return Refusal(
        error=str(error),
        code=error.code,
        kinds=tuple(kinds),
        dependents=error.dependents if isinstance(error, ModelInUseError) else None,
    )


def refusal_body(
    error: ApiError,
) -> dict[str, Any]:
    """Return the JSON body a service route refuses a call with that raised an `ApiError`."""

    return refusal(error).model_dump(mode="json", exclude_none=True)


def api_error(
    status: int,
    refused: Refusal,
) -> ApiError:
    """Return the error a refusal is, of the nearest kind this Azathoth knows.

    The kinds a refusal names are tried nearest first, then its code; a
    refusal of none this Azathoth knows is a `RemoteUnavailableError` when
    the remote answered 503, and a `RemoteRefusedError` otherwise, each
    with the status and code it was refused with.
    """

    for code in (*refused.kinds, refused.code):
        kind = REFUSED_KINDS.get(code)

        if kind is not None:
            return _rebuilt(kind, refused, status)

    unknown = (
        RemoteUnavailableError if status == HTTPStatus.SERVICE_UNAVAILABLE else RemoteRefusedError
    )

    return unknown(refused.error, status=status, refusal=refused.code)


def _rebuilt(
    kind: type[ApiError],
    refused: Refusal,
    status: int,
) -> ApiError:
    """Return an error of one kind, made as that kind is raised, with the remote's message."""

    rebuild = REBUILT_WITH.get(kind)

    return rebuild(refused, status) if rebuild is not None else kind(refused.error)


__all__ = [
    "REBUILT_WITH",
    "REFUSED_KINDS",
    "Refusal",
    "api_error",
    "refusal",
    "refusal_body",
]
