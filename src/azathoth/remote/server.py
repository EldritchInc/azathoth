"""The HTTP server a remote serves its protocol with (ADR 0124).

This module needs the `remote` extra, Starlette, so the core never imports
it. Every route but `/health` needs a bearer token its authenticator knows,
and a policy that allows what it asks; each refusal says why, and is
audited. The service routes (ADR 0127) refuse with a code as well. A push
carrying a process tool asks for importing a process tool as well, for each
such tool.

| Route | Action | Answers |
| --- | --- | --- |
| `GET /health` | | `{"status": "ok"}`, with no token |
| `GET /v1/service` | read capabilities | the `ServiceDescription` |
| `GET /v1/permissions` | | the caller's `PermissionsResponse` |
| `POST /v1/permissions` | | the `ResourcePermissionsResponse` to a `PermissionsRequest` |
| `POST /v1/calls/{name}` | the call's own | the call's result, given its arguments by name |
| `GET /v1/capabilities` | read capabilities | `Capabilities` |
| `POST /v1/missing` | push | the `MissingResponse` to a `MissingRequest` |
| `PUT /v1/content/{digest}` | push | the digest kept |
| `GET /v1/content/{digest}` | read content | the content's bytes |
| `POST /v1/push` | push; import process tool too | the `ReceiveReport` of a `PushBundle` |
| `POST /v1/pull` | pull | the `PullResponse` to a `PullRequest` |
| `POST /v1/heads` | pull | the `HeadsResponse` to a `HeadsRequest` |
| `GET /v1/portfolio` | read portfolio | the `PortfolioResponse` |
| `POST /v1/credentials` | push | the `CredentialsResponse` to a `CredentialsRequest` |

Requests are answered together (ADR 0135). Every call to a seam or a
repository runs off the event loop, in a thread of its own, so a slow
policy or a long push never holds up another request; at most
`max_concurrent` of them run at once, as many as a PostgreSQL database's
pool holds connections, and the rest wait their turn.
"""

import logging
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import partial
from http import HTTPStatus
from typing import Final, TypeVar

from anyio import CapacityLimiter, sleep, to_thread
from anyio.lowlevel import RunVar
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from azathoth.api.calls import ServiceCall, service_call
from azathoth.api.errors import ApiError, InvalidArgumentError, NotFoundError
from azathoth.evaluation import BenchmarkRepository
from azathoth.inputs import ContentStore
from azathoth.persistence.postgres import DEFAULT_POOL_SIZE
from azathoth.providers import ModelPortfolioRepository
from azathoth.remote.calling import (
    CALLS_ROUTE,
    CallerInstances,
    CallSignature,
    JobSignature,
    call_signature,
    job_signature,
)
from azathoth.remote.closure import lineage_records
from azathoth.remote.conditions import condition_checks
from azathoth.remote.inspection import heads, missing_credentials, portfolio_records
from azathoth.remote.job_reading import restricted
from azathoth.remote.jobs import (
    JOBS_ROUTE,
    JobAccepted,
    JobSummary,
    JobView,
    ServiceJob,
    ServiceJobRepository,
)
from azathoth.remote.listings import visible
from azathoth.remote.protocol import (
    MAX_CONTENT_BYTES,
    MAX_PUSH_BYTES,
    SENSITIVITY_HEADER,
    ProtocolMismatchError,
    require_protocol,
)
from azathoth.remote.pulling import pull
from azathoth.remote.receiving import (
    DivergedError,
    ReceiveRefusedError,
    RestrictedReceiveRefusedError,
    process_tool_lineages,
    receive,
    receive_content,
)
from azathoth.remote.records import (
    CredentialsRequest,
    HeadsRequest,
    MissingRequest,
    PullRequest,
    PushBundle,
)
from azathoth.remote.refusals import refusal_body
from azathoth.remote.seams import (
    Action,
    AuditEvent,
    AuditEventKind,
    Decision,
    Principal,
    RemotePluginError,
    Seams,
)
from azathoth.remote.service import (
    PERMISSIONS_ROUTE,
    SERVICE_ROUTE,
    PermissionsRequest,
    api_error_status,
    permissions,
    refusal_code,
    resource_permissions,
    service_description,
)
from azathoth.revisions import CONTENT_DIGEST_PATTERN
from azathoth.sensitivity import DEFAULT_SENSITIVITY, Sensitivity
from azathoth.tools import ToolRepository
from azathoth.workflows import WorkflowProductionStateRepository, WorkflowRepository

DEFAULT_MAX_CONCURRENT: Final = DEFAULT_POOL_SIZE
"""How many seam and repository calls a remote runs at once: one per pooled connection."""

CONTENT_MEDIA_TYPE: Final = "application/octet-stream"
"""The media type content is served as; its handle names its own."""

UNKNOWN_TOKEN_MESSAGE: Final = (
    "This remote does not know the token given. Send one its owner created with "
    "`azathoth remote token create`, as `Authorization: Bearer <TOKEN>`."
)
"""What a request without a token the remote knows is told."""

Model = TypeVar("Model", bound=BaseModel)

Result = TypeVar("Result")

Answer = tuple[Response, str | None, str | None]
"""A handler's response, and the resource and detail its audit event names."""

Handler = Callable[[Request, Principal], Awaitable[Answer]]
"""A route's handler, called for a principal the policy allows."""

DIGEST_PATTERN: Final = re.compile(CONTENT_DIGEST_PATTERN)
"""What a content route's digest must be."""

PLUGIN_ERROR_CODE: Final = "plugin_error"
"""The code of a service route's answer when a plugin of the remote's failed it."""

AUDIT_UNAVAILABLE_CODE: Final = "audit_unavailable"
"""The code of a request refused because the remote's audit could not be told of it."""

AUDIT_UNAVAILABLE_MESSAGE: Final = (
    "This remote could not tell its audit what was asked, so it did nothing; its log says why."
)
"""What a request is told when the remote's audit could not be told of it."""

JOB_CODE: Final = "job"
"""The code a call that runs as a job is answered with by a remote that runs none."""

INVOKE_CALL: Final = "runs.invoke"
"""The job that is given a key when submitted without one, so running it again resumes it."""

JOB_KEY_PREFIX: Final = "job-"
"""What the key an invocation is given when submitted without one starts with."""

NO_JOBS_MESSAGE: Final = "This remote runs no jobs."
"""What a remote that runs no jobs answers a request about one with."""

DEFAULT_JOBS_LISTED: Final = 100
"""How many of a caller's jobs a listing answers with, newest first, unless asked for fewer."""

MAX_JOBS_LISTED: Final = 1000
"""The most of a caller's jobs one listing answers with."""

EVENT_STREAM_MEDIA_TYPE: Final = "text/event-stream"
"""The media type a job's events are streamed as."""

EVENTS_POLL_SECONDS: Final = 0.25
"""How often a stream of a job's events looks for more."""

KEEP_ALIVE_SECONDS: Final = 15.0
"""How long a stream of a job's events goes quiet before it says it is still there."""

FINISHED_EVENT: Final = "finished"
"""The name of the last event a stream of a job's events sends: the job, as it ended."""

JOB_EVENT: Final = "event"
"""The name of each event a job told, as its stream sends it."""

JSON_MEDIA_TYPE: Final = "application/json"
"""The media type a call's result is answered with."""

_LOG = logging.getLogger(__name__)


class _Refused(Exception):
    """A request refused, with the status and message to answer it with, and its code."""

    def __init__(
        self,
        status: HTTPStatus,
        message: str,
        code: str | None = None,
        *,
        told: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.told = told


def error_response(
    status: HTTPStatus,
    message: str,
    code: str | None = None,
) -> JSONResponse:
    """Return the JSON a remote refuses a request with.

    A protocol route answers `{"error": message}`, as remote protocol 1
    always has; a service route adds the refusal's `code` (ADR 0127).
    """

    body = {"error": message} if code is None else {"error": message, "code": code}

    return JSONResponse(body, status_code=status)


class RemoteServer:
    """One remote: what it serves, what fills its seams, and whether it takes restricted data."""

    def __init__(
        self,
        *,
        workflows: WorkflowRepository,
        tools: ToolRepository,
        benchmarks: BenchmarkRepository,
        content: ContentStore,
        production_states: WorkflowProductionStateRepository,
        portfolio: ModelPortfolioRepository,
        seams: Seams,
        accepts_restricted: bool,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        environ: Mapping[str, str] | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        instances: CallerInstances | None = None,
        jobs: ServiceJobRepository | None = None,
        events_poll_seconds: float = EVENTS_POLL_SECONDS,
        keep_alive_seconds: float = KEEP_ALIVE_SECONDS,
    ) -> None:
        """Serve the given repositories; `environ` defaults to the process's own environment.

        At most `max_concurrent` calls to the seams and repositories run at
        once. With `instances`, the remote serves the service API, answering
        each caller with an instance of their own; without, it serves only
        the protocol. With `jobs` too, a call that runs as a job is queued
        there, for the remote's runners, and answered at once (ADR 0138);
        without, it is refused. A stream of a job's events looks for more
        every `events_poll_seconds`, and says it is still there after
        `keep_alive_seconds` of quiet.

        Raises:
            ValueError: `max_concurrent` is below 1.
        """

        if max_concurrent < 1:
            raise ValueError(f"A remote runs at least one call at once, not {max_concurrent}.")

        self.workflows = workflows
        self.tools = tools
        self.benchmarks = benchmarks
        self.content = content
        self.production_states = production_states
        self.portfolio = portfolio
        self.environ: Mapping[str, str] = os.environ if environ is None else environ
        self.seams = seams
        self.accepts_restricted = accepts_restricted
        self._clock = clock
        self.max_concurrent = max_concurrent
        self.instances = instances
        self.jobs = jobs
        self.events_poll_seconds = events_poll_seconds
        self.keep_alive_seconds = keep_alive_seconds
        #
        # A limiter belongs to the event loop it is first used on, so each
        # loop that serves this remote gets one of its own.
        #
        self._limiter: RunVar[CapacityLimiter] = RunVar(f"azathoth-remote-limiter-{id(self)}")

    async def _blocking(
        self,
        work: Callable[[], Result],
    ) -> Result:
        """Run seam or repository work in a thread, at most `max_concurrent` pieces at once."""

        return await to_thread.run_sync(work, limiter=self._current_limiter())

    def _current_limiter(
        self,
    ) -> CapacityLimiter:
        """Return this event loop's limiter, making it the first time the loop needs it."""

        try:
            return self._limiter.get()
        except LookupError:
            limiter = CapacityLimiter(self.max_concurrent)
            self._limiter.set(limiter)

            return limiter

    def app(
        self,
    ) -> Starlette:
        """Return the Starlette application serving this remote."""

        return Starlette(
            routes=[
                Route("/health", self.health, methods=["GET"]),
                Route(SERVICE_ROUTE, self.service, methods=["GET"]),
                Route(PERMISSIONS_ROUTE, self.permissions_route, methods=["GET", "POST"]),
                Route(CALLS_ROUTE, self.call_route, methods=["POST"]),
                Route(JOBS_ROUTE, self.jobs_route, methods=["GET"]),
                Route(f"{JOBS_ROUTE}/{{job_id}}", self.job_route, methods=["GET"]),
                Route(f"{JOBS_ROUTE}/{{job_id}}/cancel", self.cancel_route, methods=["POST"]),
                Route(f"{JOBS_ROUTE}/{{job_id}}/events", self.events_route, methods=["GET"]),
                Route("/v1/capabilities", self.capabilities, methods=["GET"]),
                Route("/v1/missing", self.missing, methods=["POST"]),
                Route(
                    "/v1/content/{digest}",
                    self.content_route,
                    methods=["GET", "PUT"],
                ),
                Route("/v1/push", self.push, methods=["POST"]),
                Route("/v1/pull", self.pull, methods=["POST"]),
                Route("/v1/heads", self.heads, methods=["POST"]),
                Route("/v1/portfolio", self.portfolio_route, methods=["GET"]),
                Route("/v1/credentials", self.credentials, methods=["POST"]),
            ],
        )

    # Routes

    async def health(
        self,
        request: Request,
    ) -> Response:
        """Answer that the remote is up, to anyone."""

        return JSONResponse({"status": "ok"})

    async def service(
        self,
        request: Request,
    ) -> Response:
        """Answer with the service API this remote serves, and its edition."""

        return await self._serve(
            request,
            Action.READ_CAPABILITIES,
            None,
            self._service,
            service=True,
        )

    async def permissions_route(
        self,
        request: Request,
    ) -> Response:
        """Answer what the caller may do, on the remote or on each resource asked about.

        Any caller the remote knows may ask, since the answer is only about
        them.
        """

        return await self._serve(request, None, None, self._permissions, service=True)

    async def call_route(
        self,
        request: Request,
    ) -> Response:
        """Answer one call of the service API with its result, for a caller the policy allows."""

        return await self._serve(request, None, None, self._call, service=True)

    async def jobs_route(
        self,
        request: Request,
    ) -> Response:
        """Answer with the caller's own jobs, newest first."""

        return await self._serve(request, None, None, self._listed_jobs, service=True)

    async def job_route(
        self,
        request: Request,
    ) -> Response:
        """Answer with one job, and its result once it has one, for who may see it."""

        return await self._serve(request, None, None, self._job, service=True)

    async def events_route(
        self,
        request: Request,
    ) -> Response:
        """Stream one job's events as they are told, then the job as it ended, to who may see it."""

        return await self._serve(request, None, None, self._events, service=True)

    async def cancel_route(
        self,
        request: Request,
    ) -> Response:
        """Ask one job to stop, for who may stop it."""

        return await self._serve(request, None, None, self._cancel, service=True)

    async def capabilities(
        self,
        request: Request,
    ) -> Response:
        """Answer with what this remote is, and what it accepts."""

        return await self._serve(
            request,
            Action.READ_CAPABILITIES,
            AuditEventKind.CAPABILITIES_READ,
            self._capabilities,
        )

    async def missing(
        self,
        request: Request,
    ) -> Response:
        """Answer which of the offered revisions and content this remote lacks."""

        return await self._serve(
            request,
            Action.PUSH,
            None,
            self._missing,
        )

    async def content_route(
        self,
        request: Request,
    ) -> Response:
        """Keep pushed content, or send content asked for."""

        if request.method == "PUT":
            return await self._serve(request, Action.PUSH, None, self._put_content)

        return await self._serve(
            request,
            Action.READ_CONTENT,
            AuditEventKind.CONTENT_READ,
            self._get_content,
        )

    async def push(
        self,
        request: Request,
    ) -> Response:
        """Receive a pushed bundle, fast-forward only."""

        return await self._serve(request, Action.PUSH, None, self._push)

    async def pull(
        self,
        request: Request,
    ) -> Response:
        """Send the bundle a pull asks for."""

        return await self._serve(request, Action.PULL, AuditEventKind.PULL, self._pull)

    async def heads(
        self,
        request: Request,
    ) -> Response:
        """Answer with the head of each lineage asked about, or of every one held."""

        return await self._serve(request, Action.PULL, None, self._heads)

    async def portfolio_route(
        self,
        request: Request,
    ) -> Response:
        """Answer with the models this remote's portfolio authorizes."""

        return await self._serve(
            request,
            Action.READ_PORTFOLIO,
            AuditEventKind.PORTFOLIO_READ,
            self._portfolio,
        )

    async def credentials(
        self,
        request: Request,
    ) -> Response:
        """Answer which of the credential names asked about this remote does not set."""

        return await self._serve(request, Action.PUSH, None, self._credentials)

    # Handlers, each answering for an allowed principal

    async def _service(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        described = await self._blocking(
            lambda: service_description(self.seams, self.jobs, now=self._clock())
        )

        return JSONResponse(described.model_dump(mode="json")), None, None

    async def _call(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        signature = _served_signature(
            request.path_params["name"],
            served=self.instances,
            jobs=self.jobs,
        )
        arguments = signature.read_arguments(await _body(request, MAX_PUSH_BYTES))
        resource = call_resource(signature.call, arguments)
        await self._decide_call(principal, signature.call, arguments)
        instances = self.instances
        assert instances is not None
        instance = instances.instance(principal.name)
        checks = condition_checks(signature.name)
        call = signature.call

        try:
            asked = list(call.actions)

            for check in checks:
                if check.before is None:
                    continue

                if await self._blocking(partial(check.before, instance, arguments)):
                    await self._decide(principal, check.condition.action, resource)
                    asked.append(check.condition.action)

            told = audit_kinds(call, asked)

            for kind in told:
                await self._tell(kind, principal, resource, call.name)

            if isinstance(signature, JobSignature):
                try:
                    accepted = await self._blocking(
                        lambda: self._submitted(signature, principal, arguments, resource)
                    )
                except BaseException as error:
                    if told:
                        await self._failed(principal, resource, call.name, error)

                    raise

                return (
                    JSONResponse(
                        accepted.model_dump(mode="json"),
                        status_code=HTTPStatus.ACCEPTED,
                        headers={"Location": accepted.job},
                    ),
                    None,
                    None,
                )

            method = signature.bound(instance)

            try:
                result = await self._blocking(lambda: method(**arguments))
            except BaseException as error:
                if told:
                    await self._failed(principal, resource, call.name, error)

                raise

            read = []

            for check in checks:
                if check.after is not None and check.after(arguments, result):
                    await self._decide(principal, check.condition.action, resource)
                    read.append(check.condition.action)

            for kind in audit_kinds(call, read):
                await self._tell(kind, principal, resource, call.name)

            if signature.call.lists is not None:
                listed = result
                result = await self._blocking(
                    lambda: visible(signature.call, listed, self.seams.policy, principal)
                )

            body = await self._blocking(lambda: signature.write_result(result))
        except (ApiError, _Refused):
            raise
        except Exception:
            _LOG.exception("The remote failed to answer %s.", signature.name)

            raise _Refused(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"This remote failed to answer {signature.name}; its log says why.",
            ) from None

        return Response(body, media_type=JSON_MEDIA_TYPE), None, None

    def _submitted(
        self,
        signature: JobSignature,
        principal: Principal,
        arguments: Mapping[str, object],
        resource: str | None,
    ) -> JobAccepted:
        """Queue a job for the remote's runners, as its caller, and return where to follow it.

        An invocation submitted without a key is given one, so that a runner
        recovering it invokes it again under the key, which resumes it.
        """

        jobs = self.jobs
        assert jobs is not None, "A remote that queues jobs keeps them."
        job_id = uuid.uuid4()
        given = dict(arguments)

        if signature.name == INVOKE_CALL and given.get("idempotency_key") is None:
            given["idempotency_key"] = f"{JOB_KEY_PREFIX}{job_id}"

        job = jobs.submit(
            job_id,
            call=signature.name,
            principal=principal.name,
            arguments=signature.write_arguments(**given).decode(),
            resource=resource,
        )

        return JobAccepted.of(job)

    async def _listed_jobs(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        jobs = self._job_store()
        limit = _listing_limit(request.query_params.get("limit"))
        listed = await self._blocking(lambda: jobs.jobs(principal=principal.name, limit=limit))
        body = [JobSummary.of(job).model_dump(mode="json") for job in listed]

        return JSONResponse(body), None, None

    async def _job(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        job = await self._seen_job(await self._found_job(request), principal, (Action.READ_RUNS,))

        if job.result is not None:
            await self._decide_restricted(principal, job)

        return JSONResponse(JobView.viewed(job).model_dump(mode="json")), None, None

    async def _events(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        after = _events_after(request)
        job = await self._seen_job(await self._found_job(request), principal, (Action.READ_RUNS,))
        await self._decide_restricted(principal, job)
        stream = self._streamed(request, job.job_id, after)

        return (
            StreamingResponse(
                stream,
                media_type=EVENT_STREAM_MEDIA_TYPE,
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            ),
            None,
            None,
        )

    async def _streamed(
        self,
        request: Request,
        job_id: uuid.UUID,
        after: int,
    ) -> AsyncIterator[str]:
        """Yield a job's events after the one numbered `after`, until it ends, then the job.

        Each is sent with its number as its ID, so a client that reconnects
        with `Last-Event-ID` is sent only what it missed. A stream quiet for
        `keep_alive_seconds` sends a comment, so neither side takes it for
        lost. Once the job is seen to have ended, the events are read once
        more, since a runner keeps its last before it ends the job, perhaps
        after the stream last read them.
        """

        jobs = self._job_store()
        last = after
        quiet = 0.0

        while True:
            told = await self._blocking(partial(jobs.events, job_id, after=last))

            for event in told:
                last = event.sequence
                yield server_sent(JOB_EVENT, event.event, event_id=event.sequence)

            if told:
                quiet = 0.0
                continue

            job = await self._blocking(lambda: jobs.get(job_id))

            if job is None or job.status.finished:
                if job is not None:
                    for event in await self._blocking(partial(jobs.events, job_id, after=last)):
                        last = event.sequence
                        yield server_sent(JOB_EVENT, event.event, event_id=event.sequence)

                    ended = JobView.viewed(job).model_dump_json()
                    yield server_sent(FINISHED_EVENT, ended, event_id=last)

                return

            if await request.is_disconnected():
                return

            if quiet >= self.keep_alive_seconds:
                quiet = 0.0
                yield ": still running\n\n"

            await sleep(self.events_poll_seconds)
            quiet += self.events_poll_seconds

    async def _cancel(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        found = await self._found_job(request)
        job = await self._seen_job(found, principal, service_call(found.call).actions)
        resource = _job_resource(job)
        await self._tell(AuditEventKind.JOB_CANCELLED, principal, resource, job.call)
        jobs = self._job_store()

        try:
            asked = await self._blocking(lambda: jobs.request_cancel(job.job_id, principal.name))
        except BaseException as error:
            await self._failed(principal, resource, job.call, error)

            raise

        cancelled = job if asked is None else asked

        return JSONResponse(JobSummary.of(cancelled).model_dump(mode="json")), None, None

    def _job_store(
        self,
    ) -> ServiceJobRepository:
        """Return where this remote's jobs are kept, or refuse a remote that runs none.

        Raises:
            _Refused: The remote runs no jobs.
        """

        if self.jobs is None or self.instances is None:
            raise _Refused(HTTPStatus.NOT_FOUND, NO_JOBS_MESSAGE)

        return self.jobs

    async def _found_job(
        self,
        request: Request,
    ) -> ServiceJob:
        """Return the job a request's path names.

        Raises:
            NotFoundError: The remote has no job of that ID.
        """

        jobs = self._job_store()
        named = request.path_params["job_id"]

        try:
            job_id = uuid.UUID(named)
        except ValueError:
            raise NotFoundError(f"This remote has no job {named}.") from None

        job = await self._blocking(lambda: jobs.get(job_id))

        if job is None:
            raise NotFoundError(f"This remote has no job {job_id}.")

        return job

    async def _seen_job(
        self,
        job: ServiceJob,
        principal: Principal,
        actions: Sequence[Action],
    ) -> ServiceJob:
        """Return a job for its submitter, or for another the policy allows.

        Another caller is asked each action about the job, as `job <ID>`.
        """

        if job.principal != principal.name:
            for action in actions:
                await self._decide(principal, action, _job_resource(job))

        return job

    async def _decide_restricted(
        self,
        principal: Principal,
        job: ServiceJob,
    ) -> None:
        """Refuse a restricted job's result to who may not read it, and tell the audit before.

        Raises:
            _Refused: The policy refuses `read_restricted`, or the audit could not be told.
        """

        instances = self.instances
        assert instances is not None, "A remote that keeps jobs serves calls."
        instance = await self._blocking(lambda: instances.instance(principal.name))

        if not await self._blocking(lambda: restricted(instance, job)):
            return

        resource = _job_resource(job)
        await self._decide(principal, Action.READ_RESTRICTED, resource)
        await self._tell(AuditEventKind.RESTRICTED_READ, principal, resource, job.call)

    async def _decide_call(
        self,
        principal: Principal,
        call: ServiceCall,
        arguments: Mapping[str, object],
    ) -> None:
        """Refuse a call any of whose actions the policy does not allow, on what it names."""

        resource = call_resource(call, arguments)

        for action in call.actions:
            await self._decide(principal, action, resource)

    async def _permissions(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        if request.method == "GET":
            answer: BaseModel = await self._blocking(
                lambda: permissions(self.seams.policy, principal)
            )
        else:
            asked = _parse(PermissionsRequest, await _body(request, MAX_PUSH_BYTES))
            answer = await self._blocking(
                lambda: resource_permissions(self.seams.policy, principal, asked.resources)
            )

        return JSONResponse(answer.model_dump(mode="json")), None, None

    async def _capabilities(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        shown = await self._blocking(
            lambda: self.seams.capabilities(accepts_restricted=self.accepts_restricted)
        )

        return JSONResponse(shown.model_dump(mode="json")), None, None

    async def _missing(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        offered = _parse(MissingRequest, await _body(request, MAX_PUSH_BYTES))

        answer = await self._blocking(
            lambda: offered.missing(
                held_revisions=self._held_revisions(offered),
                held_content={
                    digest for digest in offered.content if self.content.contains(digest)
                },
            )
        )

        return JSONResponse(answer.model_dump(mode="json")), None, None

    async def _put_content(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        digest = _digest(request)
        label = _sensitivity(request.headers.get(SENSITIVITY_HEADER))
        data = await _body(request, MAX_CONTENT_BYTES, subject=f"Content {digest}")
        await self._decide(principal, Action.PUSH, digest)

        try:
            await self._blocking(
                lambda: receive_content(
                    self.content,
                    data,
                    digest=digest,
                    sensitivity=label,
                    accepts_restricted=self.accepts_restricted,
                )
            )
        except RestrictedReceiveRefusedError as exc:
            raise _Refused(HTTPStatus.FORBIDDEN, str(exc)) from exc
        except ReceiveRefusedError as exc:
            raise _Refused(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc

        return JSONResponse({"digest": digest}, status_code=HTTPStatus.CREATED), digest, None

    async def _get_content(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        digest = _digest(request)
        await self._decide(principal, Action.READ_CONTENT, digest)
        data = await self._blocking(lambda: self.content.get(digest))

        if data is None:
            raise _Refused(HTTPStatus.NOT_FOUND, f"This remote holds no content {digest}.")

        return Response(data, media_type=CONTENT_MEDIA_TYPE), digest, None

    async def _push(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        bundle = _parse(PushBundle, await _body(request, MAX_PUSH_BYTES, subject="This push"))
        _require_protocol(bundle.protocol)
        lineages = list(dict.fromkeys(record.lineage for record in bundle.revisions))

        await self._decide(principal, Action.PUSH, *(str(lineage) for lineage in lineages))
        processes = process_tool_lineages(bundle)
        await self._decide(
            principal,
            Action.IMPORT_PROCESS_TOOL,
            *(str(lineage) for lineage in processes),
        )
        pushed = ", ".join(str(lineage) for lineage in lineages) or None
        await self._tell(
            AuditEventKind.PUSH,
            principal,
            pushed,
            f"Offered {len(bundle.revisions)} revisions.",
        )

        if processes:
            await self._tell(
                AuditEventKind.PROCESS_TOOL_IMPORTED,
                principal,
                ", ".join(str(lineage) for lineage in processes),
                "push",
            )

        try:
            try:
                report = await self._blocking(
                    lambda: receive(
                        bundle,
                        workflows=self.workflows,
                        tools=self.tools,
                        benchmarks=self.benchmarks,
                        content=self.content,
                        accepts_restricted=self.accepts_restricted,
                    )
                )
            except RestrictedReceiveRefusedError as exc:
                raise _Refused(HTTPStatus.FORBIDDEN, str(exc), told=True) from exc
            except DivergedError as exc:
                raise _Refused(HTTPStatus.CONFLICT, str(exc)) from exc
            except ReceiveRefusedError as exc:
                raise _Refused(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        except BaseException as error:
            await self._failed(principal, pushed, "push", error)

            raise

        return JSONResponse(report.model_dump(mode="json")), None, None

    async def _pull(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        asked = _parse(PullRequest, await _body(request, MAX_PUSH_BYTES, subject="This pull"))
        _require_protocol(asked.protocol)

        await self._decide(principal, Action.PULL, *(str(root) for root in asked.roots))

        answer = await self._blocking(
            lambda: pull(
                asked,
                workflows=self.workflows,
                tools=self.tools,
                benchmarks=self.benchmarks,
            )
        )

        return (
            JSONResponse(answer.model_dump(mode="json")),
            ", ".join(str(root) for root in asked.roots),
            f"Sent {len(answer.bundle.revisions)} revisions; withheld {len(answer.withheld)}.",
        )

    async def _heads(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        asked = _parse(HeadsRequest, await _body(request, MAX_PUSH_BYTES))
        _require_protocol(asked.protocol)

        await self._decide(principal, Action.PULL, *(str(lineage) for lineage in asked.lineages))

        answer = await self._blocking(
            lambda: heads(
                asked,
                workflows=self.workflows,
                tools=self.tools,
                benchmarks=self.benchmarks,
                production_states=self.production_states,
            )
        )

        return JSONResponse(answer.model_dump(mode="json")), None, None

    async def _portfolio(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        answer = await self._blocking(lambda: portfolio_records(self.portfolio))

        return JSONResponse(answer.model_dump(mode="json")), None, None

    async def _credentials(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        asked = _parse(CredentialsRequest, await _body(request, MAX_PUSH_BYTES))
        answer = missing_credentials(asked, self.environ, case_insensitive=os.name == "nt")

        return JSONResponse(answer.model_dump(mode="json")), None, None

    # Authenticating, deciding and auditing

    async def _serve(
        self,
        request: Request,
        action: Action | None,
        audited: AuditEventKind | None,
        handler: Handler,
        *,
        service: bool = False,
    ) -> Response:
        """Answer one request for an authenticated principal, refusing and auditing as needed.

        A request with no `action` needs only a caller the remote knows. A
        service route's refusals carry a code: an `ApiError`'s own, with
        the status its kind is answered with, or the code of the status the
        remote refuses with itself.
        """

        principal: Principal | None = None

        try:
            authorization = request.headers.get("Authorization")
            principal = await self._blocking(
                lambda: self.seams.authenticator.authenticate(authorization)
            )

            if principal is None:
                raise _Refused(HTTPStatus.UNAUTHORIZED, UNKNOWN_TOKEN_MESSAGE)

            if action is not None:
                await self._decide(principal, action, None)

            response, resource, detail = await handler(request, principal)

            if audited is not None:
                await self._tell(audited, principal, resource, detail)
        except ApiError as error:
            if not service:
                raise

            return JSONResponse(refusal_body(error), status_code=api_error_status(error))
        except RemotePluginError as error:
            if not service:
                raise

            return error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(error), PLUGIN_ERROR_CODE)
        except _Refused as refused:
            denied = refused.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)

            if denied and not refused.told:
                await self._tell_quietly(
                    AuditEventKind.REQUEST_DENIED,
                    principal,
                    f"{request.method} {request.url.path}",
                    refused.message,
                )

            code = (refused.code or refusal_code(refused.status)) if service else None

            return error_response(refused.status, refused.message, code)

        return response

    async def _decide(
        self,
        principal: Principal,
        action: Action,
        *resources: str | None,
    ) -> None:
        """Refuse what the policy does not allow a principal to do, saying why.

        The policy decides each resource in turn, in one thread, and stops
        at the first it refuses.
        """

        if not resources:
            return

        def first_refusal() -> Decision | None:
            for resource in resources:
                decision = self.seams.policy.decide(principal, action, resource)

                if not decision.allowed:
                    return decision

            return None

        refused = await self._blocking(first_refusal)

        if refused is not None:
            raise _Refused(HTTPStatus.FORBIDDEN, refused.reason or "Refused.")

    async def _tell(
        self,
        kind: AuditEventKind,
        principal: Principal | None,
        resource: str | None,
        detail: str | None,
    ) -> None:
        """Tell the audit what the remote is about to do, or to send, or refuse the request.

        A remote tells its audit before it acts, and before it sends what
        it read, so an audit that cannot be told stops the request: nothing
        is changed and nothing is sent.

        Raises:
            _Refused: The audit could not be told.
        """

        try:
            await self._audit(kind, principal, resource, detail)
        except Exception:
            _LOG.exception("The remote's audit could not be told of %s.", kind.value)

            raise _Refused(
                HTTPStatus.SERVICE_UNAVAILABLE,
                AUDIT_UNAVAILABLE_MESSAGE,
                AUDIT_UNAVAILABLE_CODE,
            ) from None

    async def _tell_quietly(
        self,
        kind: AuditEventKind,
        principal: Principal | None,
        resource: str | None,
        detail: str | None,
    ) -> None:
        """Tell the audit of a refusal or a failure, logging rather than raising when it cannot.

        The request is answered either way, since nothing was done.
        """

        try:
            await self._audit(kind, principal, resource, detail)
        except Exception:
            _LOG.exception("The remote's audit could not be told of %s.", kind.value)

    async def _failed(
        self,
        principal: Principal,
        resource: str | None,
        what: str,
        error: BaseException,
    ) -> None:
        """Tell the audit that something it was told the remote would do was not done."""

        reason = (
            error.code
            if isinstance(error, ApiError)
            else error.message
            if isinstance(error, _Refused)
            else type(error).__name__
        )

        await self._tell_quietly(
            AuditEventKind.REQUEST_FAILED,
            principal,
            resource,
            f"{what}: {reason}",
        )

    async def _audit(
        self,
        kind: AuditEventKind,
        principal: Principal | None,
        resource: str | None,
        detail: str | None,
    ) -> None:
        """Tell the audit one thing the remote did, or refused."""

        event = AuditEvent(
            kind=kind,
            occurred_at=self._clock(),
            principal=None if principal is None else principal.name,
            resource=resource,
            detail=detail,
        )

        await self._blocking(lambda: self.seams.audit.record(event))

    def _held_revisions(
        self,
        offered: MissingRequest,
    ) -> set[str]:
        """Return the offered revision digests the offered lineages hold here."""

        return {
            record.revision_digest
            for lineage in offered.lineages
            for record in lineage_records(
                lineage,
                workflows=self.workflows,
                tools=self.tools,
                benchmarks=self.benchmarks,
            )
        }


async def _body(
    request: Request,
    limit: int,
    *,
    subject: str = "This request",
) -> bytes:
    """Return a request's body, refusing one larger than a limit as soon as it is read past it.

    Raises:
        _Refused: The body is larger than the limit.
    """

    chunks: list[bytes] = []
    size = 0

    async for chunk in request.stream():
        size += len(chunk)

        if size > limit:
            raise _Refused(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"{subject} is larger than this remote accepts, {limit} bytes.",
            )

        chunks.append(chunk)

    return b"".join(chunks)


def _parse(
    model: type[Model],
    body: bytes,
) -> Model:
    """Return a request body read as one protocol model, or refuse it, saying why.

    Raises:
        _Refused: The body is not that model's JSON.
    """

    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        (first, *_) = exc.errors()
        location = ".".join(str(part) for part in first["loc"])
        where = f" at {location}" if location else ""

        raise _Refused(
            HTTPStatus.BAD_REQUEST,
            f"This request is not a {model.__name__}{where}: {first['msg']}.",
        ) from None


def audit_kinds(
    call: ServiceCall,
    asked: Sequence[Action],
) -> tuple[AuditEventKind, ...]:
    """Return each kind a call may record whose action it asked, in the catalog's order.

    A process tool's import asks both import actions, so it records both
    `tool_imported` and `process_tool_imported`; a restricted read records
    `restricted_read` beside what the call did.
    """

    return tuple(kind for kind in call.audit if kind.action in asked)


def call_resource(
    call: ServiceCall,
    arguments: Mapping[str, object],
) -> str | None:
    """Return what a call acts on, as the policy is asked about it: its kind and its ID.

    A call that names no resource, or whose resource argument was not
    given, acts on none.
    """

    if call.resource is None:
        return None

    value = arguments.get(call.resource.parameter)

    return None if value is None else f"{call.resource.kind} {value}"


def server_sent(
    name: str,
    data: str,
    *,
    event_id: int,
) -> str:
    """Return one server-sent event: its ID, its name, and its data on one line."""

    flat = data.replace("\r", "").replace("\n", " ")

    return f"id: {event_id}\nevent: {name}\ndata: {flat}\n\n"


def _events_after(
    request: Request,
) -> int:
    """Return the number of the last event a client was sent, from `Last-Event-ID` or `after`.

    Raises:
        InvalidArgumentError: It is not a number from 0.
    """

    given = request.headers.get("Last-Event-ID") or request.query_params.get("after")

    if given is None:
        return 0

    try:
        after = int(given)
    except ValueError:
        after = -1

    if after < 0:
        raise InvalidArgumentError(
            f"The last event sent is numbered from 0, as Last-Event-ID or after, not {given}."
        )

    return after


def _job_resource(
    job: ServiceJob,
) -> str:
    """Return the resource the policy is asked about one job as."""

    return f"job {job.job_id}"


def _listing_limit(
    given: str | None,
) -> int:
    """Return how many jobs a listing asks for.

    Raises:
        InvalidArgumentError: It asks for a number that is not one from 1 to the most listed.
    """

    if given is None:
        return DEFAULT_JOBS_LISTED

    try:
        limit = int(given)
    except ValueError:
        limit = 0

    if not 1 <= limit <= MAX_JOBS_LISTED:
        raise InvalidArgumentError(
            f"A listing of jobs asks for 1 to {MAX_JOBS_LISTED} of them, not {given}."
        )

    return limit


def _served_signature(
    name: str,
    *,
    served: CallerInstances | None,
    jobs: ServiceJobRepository | None,
) -> CallSignature:
    """Return how a call a remote answers travels, or refuse it, saying why.

    A job's is a `JobSignature`, when the remote runs jobs.

    Raises:
        _Refused: The remote serves no service API, the service API has no
            such call, the remote never serves it, or it is a job and the
            remote runs none.
    """

    if served is None:
        raise _Refused(
            HTTPStatus.NOT_FOUND,
            "This remote serves only push, pull and status, not the service API.",
        )

    try:
        call = service_call(name)
    except LookupError:
        raise _Refused(HTTPStatus.NOT_FOUND, f"The service API has no call named {name}.") from None

    if not call.served:
        raise _Refused(
            HTTPStatus.NOT_FOUND,
            f"A remote never serves {name}: it names this instance's own remotes, which a "
            "remote never holds.",
        )

    if call.job:
        if jobs is None:
            raise _Refused(
                HTTPStatus.NOT_IMPLEMENTED,
                f"{name} runs as a job on a remote's runners, and this remote runs none.",
                JOB_CODE,
            )

        return job_signature(name)

    return call_signature(name)


def _require_protocol(
    protocol: int,
) -> None:
    """Refuse a client that speaks another protocol, naming both.

    Raises:
        _Refused: The protocols differ.
    """

    try:
        require_protocol(protocol, peer="The client")
    except ProtocolMismatchError as exc:
        raise _Refused(HTTPStatus.BAD_REQUEST, str(exc)) from exc


def _digest(
    request: Request,
) -> str:
    """Return the content digest a route names, or refuse one that is not a digest.

    Raises:
        _Refused: The path names no digest.
    """

    digest = str(request.path_params["digest"])

    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise _Refused(HTTPStatus.BAD_REQUEST, f"{digest!r} is not a content digest.")

    return digest


def _sensitivity(
    header: str | None,
) -> Sensitivity:
    """Return the label a content upload names, internal when it names none.

    Raises:
        _Refused: The header names no label.
    """

    if header is None:
        return DEFAULT_SENSITIVITY

    try:
        return Sensitivity(header)
    except ValueError:
        raise _Refused(
            HTTPStatus.BAD_REQUEST,
            f"{SENSITIVITY_HEADER} {header!r} is not public, internal or restricted.",
        ) from None


__all__ = [
    "AUDIT_UNAVAILABLE_CODE",
    "AUDIT_UNAVAILABLE_MESSAGE",
    "CONTENT_MEDIA_TYPE",
    "DEFAULT_JOBS_LISTED",
    "DEFAULT_MAX_CONCURRENT",
    "EVENTS_POLL_SECONDS",
    "EVENT_STREAM_MEDIA_TYPE",
    "FINISHED_EVENT",
    "DIGEST_PATTERN",
    "INVOKE_CALL",
    "JOB_CODE",
    "JOB_EVENT",
    "JOB_KEY_PREFIX",
    "JSON_MEDIA_TYPE",
    "KEEP_ALIVE_SECONDS",
    "MAX_JOBS_LISTED",
    "NO_JOBS_MESSAGE",
    "PLUGIN_ERROR_CODE",
    "UNKNOWN_TOKEN_MESSAGE",
    "audit_kinds",
    "call_resource",
    "RemoteServer",
    "error_response",
    "server_sent",
]
