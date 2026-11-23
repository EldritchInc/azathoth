"""The service API of a remote, called over HTTP as a local instance is called (ADR 0137).

An `Instance` is what a local `Azathoth` and a `ConnectedInstance` both are:
the collections of calls a remote serves, `describe`, and closing. A
connected instance's collections are typed as a local instance's, and take
the same arguments, but each call is sent to the remote: its arguments are
bound as Python binds them locally, and only those given are sent, so the
rest take the call's defaults at the remote.

A `CallTransport` sends one call of the service API to a remote, as `POST
/v1/calls/<name>` with the call's arguments by name, and returns its result
as the call returns it locally: `azathoth.remote.calling` writes the
arguments and reads the result from the call's own method, as the remote
does. A refusal is raised as the error a local instance would have raised,
with the remote's message (`azathoth.remote.refusals`).

A job, a call that takes a callback for its events, runs on a remote's
workers, which a connected instance does not call yet: it is refused
before anything is sent.

`azathoth.remote.calling` reads each call from `Azathoth`, and
`azathoth.remote.refusals` from `azathoth.api`'s errors, so both import
the package this module is part of; they are imported where a call is
sent, once the package is.
"""

import inspect
from collections.abc import Callable, Mapping
from http import HTTPStatus
from types import TracebackType
from typing import Any, Final, Protocol, Self, cast

import httpx
from pydantic import ValidationError

from azathoth.api.browsing import Benchmarks, Tools, Workflows
from azathoth.api.calls import service_call
from azathoth.api.catalog import Models, Portfolio
from azathoth.api.errors import InstanceClosedError, RemoteRefusedError, RemoteUnreachableError
from azathoth.api.experiments import Experiments
from azathoth.api.goals import Goals
from azathoth.api.invocations import Invocations
from azathoth.api.judges import Judges
from azathoth.api.models import InstanceDescription
from azathoth.api.optimization import Optimization
from azathoth.api.production import Production
from azathoth.api.running import Runs
from azathoth.api.spend import Spend
from azathoth.remote.client import DEFAULT_TIMEOUT_SECONDS, HttpClient, require_remote_url

JSON_MEDIA_TYPE: Final = "application/json"
"""The media type of a call's arguments, and of its result."""

JOB_REFUSAL: Final = "job"
"""The code a job is refused with, as a remote refuses one it does not run (ADR 0136)."""

NOT_IMPLEMENTED: Final = 501
"""The status a job is refused with, as a remote refuses one."""


class CallTransport:
    """Calls of the service API, sent to one remote with one token."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        http: HttpClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Reach the remote at `url` with `token`, over `http` when given, as tests do.

        Without `http`, each call may take `timeout` seconds.

        Raises:
            ValueError: The URL is not an http or https URL.
        """

        self.url = require_remote_url(url)
        self._token = token
        self._owned = http is None
        self._http: HttpClient = (
            http if http is not None else httpx.Client(base_url=self.url, timeout=timeout)
        )

    def __enter__(
        self,
    ) -> "CallTransport":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(
        self,
    ) -> None:
        """Close the HTTP client, if this transport opened it."""

        if self._owned:
            self._http.close()

    def call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Send one call with the arguments given by name, and return its result.

        Only the arguments given are sent, so those left out take the
        call's defaults at the remote.

        Raises:
            CallArgumentsError: The arguments are not the call's; nothing
                was sent.
            NotServedError: A remote never serves the call, or runs it as a
                job; nothing was sent.
            LookupError: The service API has no call of the name.
            RemoteUnreachableError: The remote was not reached, or answered
                as no remote serving the service API does.
            ApiError: The remote refused the call: the error a local
                instance would have raised, of the nearest kind this
                Azathoth knows, or a `RemoteRefusedError`.
        """

        from azathoth.remote.calling import CALLS_ROUTE, call_signature

        signature = call_signature(name)
        body = signature.write_arguments(**arguments)

        try:
            response = self._http.request(
                "POST",
                CALLS_ROUTE.format(name=name),
                content=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": JSON_MEDIA_TYPE,
                },
            )
        except httpx.HTTPError as exc:
            raise RemoteUnreachableError(
                f"The remote at {self.url} could not be reached: {exc}"
            ) from exc

        if not response.is_success:
            raise self._refused(name, response.status_code, response.content)

        try:
            return signature.read_result(response.content)
        except ValidationError:
            raise RemoteUnreachableError(
                f"The remote at {self.url} answered {name} with something other than its "
                "result; it may serve another version of the service API."
            ) from None

    def _refused(
        self,
        name: str,
        status: int,
        body: bytes,
    ) -> Exception:
        """Return the error a refusal is, or say the remote answered as none serving calls does."""

        from azathoth.remote.refusals import Refusal, api_error

        try:
            refused = Refusal.model_validate_json(body)
        except ValidationError:
            refused = None

        if refused is not None:
            return api_error(status, refused)

        if status == HTTPStatus.NOT_FOUND:
            return RemoteUnreachableError(
                f"The remote at {self.url} does not serve {name}; it may not serve the service "
                "API, which a remote does from Azathoth 1.6."
            )

        return RemoteUnreachableError(
            f"The remote at {self.url} answered {name} with {status} without saying why; it may "
            "not be an Azathoth remote."
        )


class Instance(Protocol):
    """An Azathoth instance, local or connected to a remote: the service API a remote serves.

    `Azathoth` is one, and so is the `ConnectedInstance` `connect` returns.
    It has every collection of calls but `remotes`, and not `remote`, which
    name an instance's own remotes and are never served (ADR 0127).
    """

    def __enter__(
        self,
    ) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @property
    def closed(
        self,
    ) -> bool: ...

    @property
    def workflows(
        self,
    ) -> Workflows: ...

    @property
    def tools(
        self,
    ) -> Tools: ...

    @property
    def benchmarks(
        self,
    ) -> Benchmarks: ...

    @property
    def models(
        self,
    ) -> Models: ...

    @property
    def portfolio(
        self,
    ) -> Portfolio: ...

    @property
    def judges(
        self,
    ) -> Judges: ...

    @property
    def experiments(
        self,
    ) -> Experiments: ...

    @property
    def optimization(
        self,
    ) -> Optimization: ...

    @property
    def goals(
        self,
    ) -> Goals: ...

    @property
    def spend(
        self,
    ) -> Spend: ...

    @property
    def runs(
        self,
    ) -> Runs: ...

    @property
    def production(
        self,
    ) -> Production: ...

    @property
    def invocations(
        self,
    ) -> Invocations: ...

    def describe(
        self,
    ) -> InstanceDescription: ...

    def close(
        self,
    ) -> None: ...


class ConnectedCollection:
    """One collection of calls of a connected instance, such as its `workflows`.

    Each call is a method of the collection's name, taking the arguments
    the local collection's method takes. A name that is no call of the
    service API is no attribute.
    """

    def __init__(
        self,
        instance: "ConnectedInstance",
        name: str,
    ) -> None:
        self._instance = instance
        self._name = name
        self._calls: dict[str, Callable[..., Any]] = {}

    def __repr__(
        self,
    ) -> str:
        return f"<connected {self._name} of {self._instance.url}>"

    def __getattr__(
        self,
        method: str,
    ) -> Callable[..., Any]:
        if method.startswith("_"):
            raise AttributeError(method)

        if method not in self._calls:
            try:
                self._calls[method] = self._instance.method(f"{self._name}.{method}")
            except LookupError:
                raise AttributeError(
                    f"The service API's {self._name} have no call named {method}."
                ) from None

        return self._calls[method]


class ConnectedInstance:
    """The service API of one remote, called over HTTP as a local instance is called.

    Make one with `azathoth.api.connect`, and close it when done, best as a
    context manager. Each call is one request to the remote, which asks its
    policy and tells its audit as for any caller; what it changes is
    recorded as the caller's. A call may raise what the local call does,
    and `RemoteUnreachableError` or `RemoteRefusedError` too. Once closed,
    every call raises `InstanceClosedError`.
    """

    def __init__(
        self,
        transport: CallTransport,
    ) -> None:
        """Call the remote a transport reaches; `connect` is the way to make one."""

        self._transport = transport
        self._closed = False
        self._collections: dict[str, ConnectedCollection] = {}

    def __enter__(
        self,
    ) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(
        self,
    ) -> str:
        return f"<connected Azathoth at {self.url}>"

    @property
    def url(
        self,
    ) -> str:
        """Return the URL of the remote this instance calls."""

        return self._transport.url

    @property
    def closed(
        self,
    ) -> bool:
        """Return whether the instance was closed."""

        return self._closed

    @property
    def workflows(
        self,
    ) -> Workflows:
        """Return the remote's workflows."""

        return cast(Workflows, self._collection("workflows"))

    @property
    def tools(
        self,
    ) -> Tools:
        """Return the remote's tools."""

        return cast(Tools, self._collection("tools"))

    @property
    def benchmarks(
        self,
    ) -> Benchmarks:
        """Return the remote's benchmark datasets."""

        return cast(Benchmarks, self._collection("benchmarks"))

    @property
    def models(
        self,
    ) -> Models:
        """Return the models the remote's providers serve now."""

        return cast(Models, self._collection("models"))

    @property
    def portfolio(
        self,
    ) -> Portfolio:
        """Return the models the remote authorizes for selection."""

        return cast(Portfolio, self._collection("portfolio"))

    @property
    def judges(
        self,
    ) -> Judges:
        """Return the remote's rotation of models that judge semantic cases."""

        return cast(Judges, self._collection("judges"))

    @property
    def experiments(
        self,
    ) -> Experiments:
        """Read and compare the optimization experiments the remote recorded."""

        return cast(Experiments, self._collection("experiments"))

    @property
    def optimization(
        self,
    ) -> Optimization:
        """Optimize the remote's workflows; its one call is a job."""

        return cast(Optimization, self._collection("optimization"))

    @property
    def goals(
        self,
    ) -> Goals:
        """Return the remote's reusable goals."""

        return cast(Goals, self._collection("goals"))

    @property
    def spend(
        self,
    ) -> Spend:
        """Read what the remote spent, and when."""

        return cast(Spend, self._collection("spend"))

    @property
    def runs(
        self,
    ) -> Runs:
        """Return runs of the remote's workflows."""

        return cast(Runs, self._collection("runs"))

    @property
    def production(
        self,
    ) -> Production:
        """Return the production of the remote's workflows."""

        return cast(Production, self._collection("production"))

    @property
    def invocations(
        self,
    ) -> Invocations:
        """Return the invocations of the remote's promoted workflows."""

        return cast(Invocations, self._collection("invocations"))

    def describe(
        self,
    ) -> InstanceDescription:
        """Return what the remote's instance is: its database, and the Azathoth serving it.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        described: InstanceDescription = self.method("describe")()

        return described

    def close(
        self,
    ) -> None:
        """Close the HTTP client this instance opened; closing again does nothing."""

        if self._closed:
            return

        self._closed = True
        self._transport.close()

    def method(
        self,
        name: str,
    ) -> Callable[..., Any]:
        """Return a call of the service API by its name, as this instance makes it.

        It takes the arguments the local call takes, positionally or by name,
        and sends only those given. A job raises `RemoteRefusedError`, its
        `status` 501 and its `refusal` `job`, whatever it is given, without
        sending anything.

        Raises:
            LookupError: The service API has no call of that name.
        """

        from azathoth.remote.calling import call_function

        call = service_call(name)
        function = call_function(name)
        signature = inspect.signature(function)
        (owner, *_) = signature.parameters
        shown = signature.replace(parameters=list(signature.parameters.values())[1:])

        def called(
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if self._closed:
                raise InstanceClosedError()

            if call.job:
                raise RemoteRefusedError(
                    f"{name} runs on a remote's workers, which a connected instance does not "
                    "call yet.",
                    status=NOT_IMPLEMENTED,
                    refusal=JOB_REFUSAL,
                )

            arguments = dict(signature.bind(None, *args, **kwargs).arguments)
            del arguments[owner]

            return self._transport.call(name, arguments)

        called.__name__ = function.__name__
        called.__qualname__ = f"{type(self).__name__}.{name}"
        called.__doc__ = function.__doc__
        called.__signature__ = shown  # type: ignore[attr-defined]

        return called

    def _collection(
        self,
        name: str,
    ) -> ConnectedCollection:
        """Return one collection of calls, made the first time it is asked for."""

        if name not in self._collections:
            self._collections[name] = ConnectedCollection(self, name)

        return self._collections[name]


__all__ = [
    "JOB_REFUSAL",
    "JSON_MEDIA_TYPE",
    "NOT_IMPLEMENTED",
    "CallTransport",
    "ConnectedCollection",
    "ConnectedInstance",
    "Instance",
]
