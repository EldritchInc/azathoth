"""The HTTP server a remote serves its protocol with (ADR 0124).

This module needs the `remote` extra, Starlette, so the core never imports
it. Every route but `/health` needs a bearer token its authenticator knows,
and a policy that allows what it asks; each refusal says why, and is
audited. The service routes (ADR 0127) refuse with a code as well.

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
| `POST /v1/push` | push | the `ReceiveReport` of a `PushBundle` |
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
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Final, TypeVar

from anyio import CapacityLimiter, to_thread
from anyio.lowlevel import RunVar
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from azathoth.api.calls import ServiceCall, service_call
from azathoth.api.errors import ApiError
from azathoth.evaluation import BenchmarkRepository
from azathoth.inputs import ContentStore
from azathoth.persistence.postgres import DEFAULT_POOL_SIZE
from azathoth.providers import ModelPortfolioRepository
from azathoth.remote.calling import (
    CALLS_ROUTE,
    CallerInstances,
    CallSignature,
    call_signature,
)
from azathoth.remote.closure import lineage_records
from azathoth.remote.inspection import heads, missing_credentials, portfolio_records
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

JOB_CODE: Final = "job"
"""The code a call that runs as a job is answered with until the remote runs jobs."""

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
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


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
    ) -> None:
        """Serve the given repositories; `environ` defaults to the process's own environment.

        At most `max_concurrent` calls to the seams and repositories run at
        once. With `instances`, the remote serves the service API, answering
        each caller with an instance of their own; without, it serves only
        the protocol.

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

        return await self._serve(request, Action.PUSH, AuditEventKind.PUSH, self._push)

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
        described = await self._blocking(lambda: service_description(self.seams))

        return JSONResponse(described.model_dump(mode="json")), None, None

    async def _call(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        signature = _served_signature(request.path_params["name"], served=self.instances)
        arguments = signature.read_arguments(await _body(request, MAX_PUSH_BYTES))
        await self._decide_call(principal, signature.call, arguments)
        instances = self.instances
        assert instances is not None

        def answer() -> bytes:
            method = signature.bound(instances.instance(principal.name))

            return signature.write_result(method(**arguments))

        try:
            body = await self._blocking(answer)
        except ApiError:
            raise
        except Exception:
            _LOG.exception("The remote failed to answer %s.", signature.name)

            raise _Refused(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"This remote failed to answer {signature.name}; its log says why.",
            ) from None

        return Response(body, media_type=JSON_MEDIA_TYPE), None, None

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
            raise _Refused(HTTPStatus.FORBIDDEN, str(exc)) from exc
        except DivergedError as exc:
            raise _Refused(HTTPStatus.CONFLICT, str(exc)) from exc
        except ReceiveRefusedError as exc:
            raise _Refused(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc

        return (
            JSONResponse(report.model_dump(mode="json")),
            ", ".join(str(lineage) for lineage in lineages) or None,
            f"Received {len(report.received)} revisions; {report.already_held} already held.",
        )

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
        except ApiError as error:
            if not service:
                raise

            return error_response(api_error_status(error), str(error), error.code)
        except RemotePluginError as error:
            if not service:
                raise

            return error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(error), PLUGIN_ERROR_CODE)
        except _Refused as refused:
            if refused.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                await self._audit(
                    AuditEventKind.REQUEST_DENIED,
                    principal,
                    f"{request.method} {request.url.path}",
                    refused.message,
                )

            code = (refused.code or refusal_code(refused.status)) if service else None

            return error_response(refused.status, refused.message, code)

        if audited is not None:
            await self._audit(audited, principal, resource, detail)

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


def _served_signature(
    name: str,
    *,
    served: CallerInstances | None,
) -> CallSignature:
    """Return how a call a remote answers travels, or refuse it, saying why.

    Raises:
        _Refused: The remote serves no service API, the service API has no
            such call, the remote never serves it, or it runs as a job.
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
        raise _Refused(
            HTTPStatus.NOT_IMPLEMENTED,
            f"{name} runs on the remote's workers, which this remote does not run jobs on yet.",
            JOB_CODE,
        )

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
    "CONTENT_MEDIA_TYPE",
    "DEFAULT_MAX_CONCURRENT",
    "DIGEST_PATTERN",
    "JOB_CODE",
    "JSON_MEDIA_TYPE",
    "PLUGIN_ERROR_CODE",
    "UNKNOWN_TOKEN_MESSAGE",
    "call_resource",
    "RemoteServer",
    "error_response",
]
