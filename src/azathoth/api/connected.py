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
runners (ADR 0138). A connected instance submits it, follows its events
as the remote streams them, handing each to `on_event`, asks the remote
to stop it once `cancel` is cancelled, and returns its result or raises
its refusal, as the local call does. A stream that drops is followed
again from the last event seen, a few times, before the job is given up
on; the job goes on at the remote, where `jobs` finds it.

`azathoth.remote.calling` reads each call from `Azathoth`, and
`azathoth.remote.refusals` from `azathoth.api`'s errors, so both import
the package this module is part of; they are imported where a call is
sent, once the package is.
"""

import inspect
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from http import HTTPStatus
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Protocol, Self, cast, runtime_checkable
from uuid import UUID

import httpx
from pydantic import ValidationError

from azathoth.api.browsing import Benchmarks, Tools, Workflows
from azathoth.api.calls import service_call
from azathoth.api.catalog import Models, Portfolio
from azathoth.api.errors import (
    InstanceClosedError,
    RemoteUnreachableError,
    RunCancelledError,
)
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

if TYPE_CHECKING:
    from azathoth.remote.calling import JobSignature
    from azathoth.remote.jobs import JobAccepted, JobSummary, JobView

LOGGER: Final = logging.getLogger(__name__)

JSON_MEDIA_TYPE: Final = "application/json"
"""The media type of a call's arguments, and of its result."""

RECONNECTS: Final = 5
"""How many times a dropped stream of a job's events is followed again before it is given up."""

RECONNECT_SECONDS: Final = 0.5
"""How long the first wait before following a dropped stream again is; each is longer."""

CANCEL_POLL_SECONDS: Final = 0.1
"""How often a token is looked at while its job runs, so a cancel reaches the remote soon."""

Cancellable = Any
"""What can ask a job to stop: anything with `cancelled`, as a `CancellationToken` has."""


class StreamedResponse(Protocol):
    """An HTTP answer read as it arrives, as a client follows a stream."""

    @property
    def status_code(
        self,
    ) -> int:
        """Return the answer's status."""

        ...

    @property
    def is_success(
        self,
    ) -> bool:
        """Return whether the status is a success."""

        ...

    def iter_lines(
        self,
    ) -> Iterator[str]:
        """Yield the answer's lines as they arrive, without their line breaks."""

        ...

    def read(
        self,
    ) -> bytes:
        """Return the rest of the answer's body."""

        ...


@runtime_checkable
class StreamingHttpClient(HttpClient, Protocol):
    """An HTTP client that can also read an answer as it arrives, as httpx's can."""

    def stream(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> AbstractContextManager[StreamedResponse]:
        """Send one request, and read its answer as it arrives."""

        ...


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

    def _headers(
        self,
    ) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": JSON_MEDIA_TYPE}

    def _sent(
        self,
        method: str,
        path: str,
        what: str,
        body: bytes | None = None,
    ) -> bytes:
        """Send one request, and return its answer's body, or raise what its refusal is."""

        try:
            response = self._http.request(method, path, content=body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise RemoteUnreachableError(
                f"The remote at {self.url} could not be reached: {exc}"
            ) from exc

        if not response.is_success:
            raise self._refused(what, response.status_code, response.content)

        return response.content

    def _model(
        self,
        body: bytes,
        what: str,
        read: Callable[[bytes], Any],
    ) -> Any:
        """Return what an answer holds, or say the remote answered as none does."""

        try:
            return read(body)
        except ValidationError:
            raise RemoteUnreachableError(
                f"The remote at {self.url} answered {what} with something other than its "
                "result; it may serve another version of the service API."
            ) from None

    def submit(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> "JobAccepted":
        """Submit one job with the arguments given by name, and return where to follow it.

        Raises:
            CallArgumentsError: The arguments are not the job's; nothing was sent.
            NotServedError: The call is not a job.
            RemoteUnreachableError: The remote was not reached, or answered
                as no remote serving the service API does.
            ApiError: The remote refused the job.
        """

        from azathoth.remote.calling import CALLS_ROUTE, job_signature
        from azathoth.remote.jobs import JobAccepted

        body = job_signature(name).write_arguments(**arguments)
        answered = self._sent("POST", CALLS_ROUTE.format(name=name), name, body)

        return cast(JobAccepted, self._model(answered, name, JobAccepted.model_validate_json))

    def job(
        self,
        job_id: UUID,
    ) -> "JobView":
        """Return one job as the remote says it stands, with its result once it has one."""

        from azathoth.remote.jobs import JobView, job_path

        what = f"job {job_id}"
        answered = self._sent("GET", job_path(job_id), what)

        return cast(JobView, self._model(answered, what, JobView.model_validate_json))

    def jobs(
        self,
        *,
        limit: int = 100,
    ) -> tuple["JobSummary", ...]:
        """Return the caller's own jobs, newest first, at most `limit` of them."""

        from pydantic import TypeAdapter

        from azathoth.remote.jobs import JOBS_ROUTE, JobSummary

        answered = self._sent("GET", f"{JOBS_ROUTE}?limit={limit}", "jobs")
        listed = TypeAdapter(tuple[JobSummary, ...])

        return cast(tuple[JobSummary, ...], self._model(answered, "jobs", listed.validate_json))

    def cancel(
        self,
        job_id: UUID,
    ) -> "JobSummary":
        """Ask one job to stop, and return it as it stands once asked."""

        from azathoth.remote.jobs import JobSummary, job_path

        what = f"job {job_id}"
        answered = self._sent("POST", f"{job_path(job_id)}/cancel", what)

        return cast(JobSummary, self._model(answered, what, JobSummary.model_validate_json))

    def run(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        on_event: Callable[[Any], None] | None = None,
        cancel: Cancellable | None = None,
    ) -> Any:
        """Submit one job, follow it to its end, and return its result as the local call does.

        Raises:
            RunCancelledError: `cancel` was cancelled before it was
                submitted, and nothing was sent; or the job was stopped.
            RemoteUnreachableError: The remote was not reached, or its
                stream of the job's events was lost too often to follow.
            ApiError: The remote refused the job, or it ended as the local
                call would have raised.
        """

        if cancel is not None and cancel.cancelled:
            raise RunCancelledError()

        accepted = self.submit(name, arguments)

        return self.follow(accepted.job_id, name, on_event=on_event, cancel=cancel)

    def follow(
        self,
        job_id: UUID,
        name: str,
        *,
        on_event: Callable[[Any], None] | None = None,
        cancel: Cancellable | None = None,
    ) -> Any:
        """Follow one job of a call to its end, handing each event to `on_event`.

        Once `cancel` is cancelled, the remote is asked to stop the job; the
        job then ends, and its refusal is raised. A stream that drops is
        followed again from the last event seen, up to `RECONNECTS` times.
        A callback that raises is told no more events, and the job goes on.
        """

        from azathoth.remote.calling import job_signature

        signature = job_signature(name)
        heard = _Heard(on_event)
        done = threading.Event()
        watcher = (
            threading.Thread(
                target=self._pass_on_cancel,
                args=(job_id, cancel, done),
                name=f"cancel-{job_id}",
                daemon=True,
            )
            if cancel is not None
            else None
        )

        if watcher is not None:
            watcher.start()

        try:
            last = 0
            dropped = 0

            while True:
                last, ended = self._read_events(job_id, signature, last, heard)

                if ended is not None:
                    return self._ended(signature, ended)

                dropped += 1

                if dropped > RECONNECTS:
                    raise RemoteUnreachableError(
                        f"The remote at {self.url} dropped the events of job {job_id} "
                        f"{RECONNECTS + 1} times, so they are no longer followed; the job goes "
                        "on there, and jobs.get finds it."
                    )

                time.sleep(RECONNECT_SECONDS * dropped)
        finally:
            done.set()

            if watcher is not None:
                watcher.join()

    def _read_events(
        self,
        job_id: UUID,
        signature: "JobSignature",
        after: int,
        heard: "_Heard",
    ) -> tuple[int, "JobView | None"]:
        """Read a job's events after one, handing each on, until it ends or the stream drops.

        Returns the number of the last event read, and the job once it ended,
        or None when the stream dropped first.
        """

        from azathoth.remote.jobs import JobView, events_path
        from azathoth.remote.sse import read_server_sent

        what = f"the events of job {job_id}"

        if not isinstance(self._http, StreamingHttpClient):
            raise TypeError(f"The HTTP client given cannot stream {what}.")

        headers = {**self._headers(), "Last-Event-ID": str(after), "Accept": "text/event-stream"}
        last = after
        refused: Exception | None = None

        try:
            with self._http.stream("GET", events_path(job_id), headers=headers) as response:
                if not response.is_success:
                    refused = self._refused(what, response.status_code, response.read())

                for sent in () if refused is not None else read_server_sent(response.iter_lines()):
                    if sent.name == "finished":
                        view = self._model(sent.data.encode(), what, JobView.model_validate_json)

                        return last, cast(JobView, view)

                    if sent.event_id is not None:
                        last = int(sent.event_id)

                    event = self._model(sent.data.encode(), what, signature.read_event)
                    heard(event)
        except httpx.HTTPError:
            LOGGER.info("The stream of %s dropped after event %s.", what, last)

        if refused is not None:
            raise refused

        return last, None

    def _ended(
        self,
        signature: "JobSignature",
        ended: "JobView",
    ) -> Any:
        """Return a job's result, or raise what its ending is, as the local call would.

        A job cancelled before it ran ends with no refusal, and raises the
        `RunCancelledError` one cancelled while it ran does.
        """

        from azathoth.remote.jobs import ServiceJobStatus
        from azathoth.remote.refusals import Refusal, api_error

        if ended.status is ServiceJobStatus.SUCCEEDED:
            written = json.dumps(ended.result).encode()

            return self._model(written, signature.name, signature.read_result)

        status = ended.refusal_status or HTTPStatus.INTERNAL_SERVER_ERROR

        try:
            refused = Refusal.model_validate(ended.refusal)
        except ValidationError:
            if ended.status is ServiceJobStatus.CANCELLED:
                raise RunCancelledError() from None

            refused = Refusal(
                error=f"Job {ended.job_id} of {signature.name} ended {ended.status.value}.",
                code=ended.status.value,
            )

        raise api_error(status, refused)

    def _pass_on_cancel(
        self,
        job_id: UUID,
        cancel: Cancellable,
        done: threading.Event,
    ) -> None:
        """Ask the remote to stop a job once its token is cancelled, until it ends."""

        while not done.wait(CANCEL_POLL_SECONDS):
            if cancel.cancelled:
                try:
                    self.cancel(job_id)
                except Exception:
                    LOGGER.exception("The remote could not be asked to stop job %s.", job_id)

                return

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


class _Heard:
    """A callback a job's events are handed to, told no more once it raises."""

    def __init__(
        self,
        callback: Callable[[Any], None] | None,
    ) -> None:
        self._callback = callback

    def __call__(
        self,
        event: object,
    ) -> None:
        if self._callback is None:
            return

        try:
            self._callback(event)
        except Exception:
            LOGGER.warning("An event callback raised, so it is told no more events.", exc_info=True)
            self._callback = None


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


class ConnectedJobs:
    """The jobs a connected instance's caller submitted to the remote (ADR 0138).

    A job called as its call, such as `runs.run`, is submitted and followed
    to its end at once. These are for code that submits a job and follows
    it later, or from elsewhere, or stops it.
    """

    def __init__(
        self,
        instance: "ConnectedInstance",
    ) -> None:
        self._instance = instance

    def list(
        self,
        *,
        limit: int = 100,
    ) -> tuple["JobSummary", ...]:
        """Return the caller's own jobs, newest first, at most `limit` of them.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is not from 1 to 1000.
        """

        return self._instance._open().jobs(limit=limit)

    def get(
        self,
        job_id: UUID,
    ) -> "JobView":
        """Return one job as it stands, with its result or its refusal once it has ended.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The remote has no job of that ID.
            PermissionDeniedError: The job is another caller's, and the
                remote's policy refuses to show it, or its restricted result.
        """

        return self._instance._open().job(job_id)

    def submit(
        self,
        name: str,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> "JobAccepted":
        """Submit one job of a call by its name, with the call's arguments, and return at once.

        Its events are followed apart, with `follow`, so it takes no
        `on_event` or `cancel`.

        Raises:
            InstanceClosedError: The instance was closed.
            TypeError: The arguments are not ones the call takes, or name
                `on_event` or `cancel`.
            NotServedError: The call is not a job.
            ApiError: The remote refused the job.
        """

        from azathoth.remote.calling import JOB_PARAMETERS, call_function

        transport = self._instance._open()
        signature = inspect.signature(call_function(name))
        (owner, *_) = signature.parameters
        arguments = dict(signature.bind(None, *args, **kwargs).arguments)
        del arguments[owner]
        given = sorted(JOB_PARAMETERS & set(arguments))

        if given:
            raise TypeError(f"A job submitted is followed apart, so it takes no {given[0]}.")

        return transport.submit(name, arguments)

    def follow(
        self,
        job_id: UUID,
        *,
        on_event: Callable[[Any], None] | None = None,
        cancel: Cancellable | None = None,
    ) -> Any:
        """Follow one job to its end, from its first event, and return its result.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The remote has no job of that ID.
            ApiError: The job ended as its local call would have raised.
        """

        transport = self._instance._open()
        job = transport.job(job_id)

        return transport.follow(job_id, job.call, on_event=on_event, cancel=cancel)

    def cancel(
        self,
        job_id: UUID,
    ) -> "JobSummary":
        """Ask one job to stop, and return it as it stands once asked.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The remote has no job of that ID.
            PermissionDeniedError: The job is another caller's, and the
                remote's policy refuses to let this caller stop it.
        """

        return self._instance._open().cancel(job_id)


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

    @property
    def jobs(
        self,
    ) -> ConnectedJobs:
        """Return the jobs this instance's caller submitted to the remote, to follow apart."""

        return ConnectedJobs(self)

    def _open(
        self,
    ) -> CallTransport:
        """Return the transport calls are sent over, once the instance is known open.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        if self._closed:
            raise InstanceClosedError()

        return self._transport

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
        and sends only those given. A job is submitted and followed to its
        end, its events handed to its `on_event`, and stopped once its
        `cancel` is cancelled.

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

            arguments = dict(signature.bind(None, *args, **kwargs).arguments)
            del arguments[owner]

            if call.job:
                on_event = arguments.pop("on_event", None)
                cancel = arguments.pop("cancel", None)

                return self._transport.run(name, arguments, on_event=on_event, cancel=cancel)

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
    "CANCEL_POLL_SECONDS",
    "JSON_MEDIA_TYPE",
    "RECONNECTS",
    "RECONNECT_SECONDS",
    "CallTransport",
    "ConnectedCollection",
    "ConnectedInstance",
    "ConnectedJobs",
    "Instance",
    "StreamedResponse",
    "StreamingHttpClient",
]
