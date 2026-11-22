"""How each call of the service API travels over HTTP, read from the call itself (ADR 0127).

A remote serves every call of `azathoth.api` at `POST /v1/calls/<name>`. The
request body is a JSON object of the call's arguments by name, and the
answer is its result as JSON, so the routes add no shapes of their own.
Nothing here is written by hand for any call: `call_signature` reads the
call's parameters and result from its method on `Azathoth`, and pydantic
reads and writes each as its own JSON. A `bytes` value, such as a file's
content, travels in base64.

A job, a call that runs a workflow, a benchmark or an optimization, takes a
callback for its events and a way to cancel it, which cannot travel as JSON;
a remote runs jobs on its workers instead, so they have no signature here.
A parameter only the server can give, such as the connection `tools.from_mcp`
is tested with, is never read from a request.

This module needs no web framework, so a client builds its requests from it
too.
"""

import inspect
import threading
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, create_model

from azathoth.api.calls import SERVICE_CALLS, ServiceCall, service_call
from azathoth.api.errors import InvalidArgumentError
from azathoth.api.instance import Azathoth
from azathoth.api.providers import ProviderSettings
from azathoth.persistence.repositories import Repositories
from azathoth.telemetry import NO_TELEMETRY, Telemetry

CALLS_ROUTE: Final = "/v1/calls/{name}"
"""Where a remote serves each call of the service API, by the call's name."""

SERVER_ONLY_PARAMETERS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("tools.from_mcp", "connect"),
    }
)
"""Parameters a call takes only from the code that holds the instance, never from a request."""


class CallArgumentsError(InvalidArgumentError):
    """A request's body is not the arguments its call takes."""


class NotServedError(LookupError):
    """A call that a remote does not serve over HTTP was asked for its signature."""


UNKNOWN_ARGUMENT: Final = "extra_forbidden"
"""The kind of pydantic error an argument the call does not take is."""


def arguments_refused(
    name: str,
    error: ValidationError,
) -> CallArgumentsError:
    """Return why arguments are not the ones a call takes, naming one thing wrong.

    An argument the call does not take is named before anything else, since
    it is most often one misnamed, which is also why one the call needs is
    missing: `workflow` given for `workflow_id` names `workflow`. Otherwise
    the first error pydantic gives is named. Pydantic's own order is not
    the same in every version, so it is never relied on to choose.
    """

    errors = error.errors()
    (first, *_) = sorted(errors, key=lambda each: each["type"] != UNKNOWN_ARGUMENT)
    location = ".".join(str(part) for part in first["loc"])
    where = f" at {location}" if location else ""

    return CallArgumentsError(f"These are not the arguments {name} takes{where}: {first['msg']}.")


@dataclass(frozen=True)
class CallSignature:
    """What one call takes and returns, as it travels over HTTP."""

    call: ServiceCall
    collection: str | None
    method: str
    arguments: type[BaseModel]
    result: TypeAdapter[Any]

    @property
    def name(
        self,
    ) -> str:
        """Return the call's name, such as `workflows.get`."""

        return self.call.name

    def read_arguments(
        self,
        body: bytes,
    ) -> dict[str, Any]:
        """Return the arguments a request's JSON body gives, by name, ready to call with.

        An empty body gives no arguments, as `{}` does.

        Raises:
            CallArgumentsError: The body is not a JSON object of the
                arguments the call takes, saying where and why.
        """

        try:
            read = self.arguments.model_validate_json(body or b"{}")
        except ValidationError as exc:
            raise arguments_refused(self.name, exc) from None

        return {field: getattr(read, field) for field in type(read).model_fields}

    def write_arguments(
        self,
        **arguments: Any,
    ) -> bytes:
        """Return a request's JSON body for arguments given by name, as a client sends it.

        Only the arguments given, and not given as their defaults, are
        written, so the remote's defaults are the call's own: an argument
        such as `expected`, whose default keeps what is there, is never
        mistaken for a value that reads the same.

        Raises:
            CallArgumentsError: They are not the arguments the call takes.
        """

        try:
            written = self.arguments.model_validate(arguments)
        except ValidationError as exc:
            raise arguments_refused(self.name, exc) from None

        return written.model_dump_json(exclude_unset=True, exclude_defaults=True).encode()

    def bound(
        self,
        instance: Azathoth,
    ) -> Callable[..., Any]:
        """Return the call's method on an instance."""

        target: object = instance if self.collection is None else getattr(instance, self.collection)
        method: Callable[..., Any] = getattr(target, self.method)

        return method

    def write_result(
        self,
        result: object,
    ) -> bytes:
        """Return a call's result as the JSON a remote answers with."""

        return self.result.dump_json(result)

    def read_result(
        self,
        body: bytes,
    ) -> Any:
        """Return the result a remote's JSON answer holds, as the call returns it locally."""

        return self.result.validate_json(body)


def _function(
    call: ServiceCall,
) -> tuple[str | None, str, Callable[..., Any]]:
    """Return a call's collection, method name and function on `Azathoth`."""

    collection, _, method = call.name.rpartition(".")

    if not collection:
        return None, method, getattr(Azathoth, method)

    namespace = typing.get_type_hints(getattr(Azathoth, collection).fget)["return"]

    return collection, method, getattr(namespace, method)


@cache
def call_signature(
    name: str,
) -> CallSignature:
    """Return how the call of a name travels over HTTP.

    Raises:
        LookupError: The service API has no call of that name.
        NotServedError: A remote never serves it, or runs it as a job.
    """

    call = service_call(name)

    if not call.served:
        raise NotServedError(f"A remote never serves {name}.")

    if call.job:
        raise NotServedError(f"A remote runs {name} as a job on its workers.")

    collection, method, function = _function(call)
    hints = typing.get_type_hints(function)
    fields: dict[str, Any] = {}

    for parameter in list(inspect.signature(function).parameters.values())[1:]:
        if (name, parameter.name) in SERVER_ONLY_PARAMETERS:
            continue

        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        fields[parameter.name] = (hints[parameter.name], default)

    arguments = create_model(
        f"Arguments of {name}",
        __config__=ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64"),
        **fields,
    )

    return CallSignature(
        call=call,
        collection=collection,
        method=method,
        arguments=arguments,
        result=TypeAdapter(hints["return"]),
    )


class CallerInstances:
    """The service API a remote answers each caller with, over the repositories it serves.

    Each caller gets an `Azathoth` of their own, made the first time they
    call, so what they import or authorize is recorded as theirs: their
    principal's name is the author. Every instance shares the remote's
    repositories, and none is ever closed, since closing one would close
    the database the others serve.
    """

    def __init__(
        self,
        repositories: Repositories,
        *,
        providers: ProviderSettings | None = None,
        telemetry: Telemetry = NO_TELEMETRY,
    ) -> None:
        self._repositories = repositories
        self._providers = providers
        self._telemetry = telemetry
        self._instances: dict[str, Azathoth] = {}
        self._lock = threading.Lock()

    def instance(
        self,
        author: str,
    ) -> Azathoth:
        """Return the instance a caller of a name is answered with, recording them as author.

        Raises:
            InvalidAuthorError: The name is not one an author may have.
        """

        with self._lock:
            instance = self._instances.get(author)

            if instance is None:
                instance = Azathoth(
                    self._repositories,
                    providers=self._providers,
                    telemetry=self._telemetry,
                    author=author,
                )
                self._instances[author] = instance

            return instance


def call_signatures() -> Mapping[str, CallSignature]:
    """Return how every call a remote answers while the request waits travels, by name."""

    return {
        call.name: call_signature(call.name)
        for call in SERVICE_CALLS
        if call.served and not call.job
    }


__all__ = [
    "CALLS_ROUTE",
    "SERVER_ONLY_PARAMETERS",
    "UNKNOWN_ARGUMENT",
    "CallArgumentsError",
    "CallSignature",
    "CallerInstances",
    "NotServedError",
    "arguments_refused",
    "call_signature",
    "call_signatures",
]
