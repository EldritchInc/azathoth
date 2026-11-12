"""The HTTP server a remote serves its protocol with (ADR 0124).

This module needs the `remote` extra, Starlette, so the core never imports
it. Every route but `/health` needs a bearer token its authenticator knows,
and a policy that allows what it asks; each refusal says why, and is
audited.

| Route | Action | Answers |
| --- | --- | --- |
| `GET /health` | | `{"status": "ok"}`, with no token |
| `GET /v1/capabilities` | read capabilities | `Capabilities` |
| `POST /v1/missing` | push | the `MissingResponse` to a `MissingRequest` |
| `PUT /v1/content/{digest}` | push | the digest kept |
| `GET /v1/content/{digest}` | read content | the content's bytes |
| `POST /v1/push` | push | the `ReceiveReport` of a `PushBundle` |
| `POST /v1/pull` | pull | the `PullResponse` to a `PullRequest` |
| `POST /v1/heads` | pull | the `HeadsResponse` to a `HeadsRequest` |
| `GET /v1/portfolio` | read portfolio | the `PortfolioResponse` |
| `POST /v1/credentials` | push | the `CredentialsResponse` to a `CredentialsRequest` |

Repositories are read and written off the event loop, one request at a
time, since a PostgreSQL database's repositories share one connection.
"""

import asyncio
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Final, TypeVar

from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from azathoth.evaluation import BenchmarkRepository
from azathoth.inputs import ContentStore
from azathoth.providers import ModelPortfolioRepository
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
from azathoth.remote.seams import Action, AuditEvent, AuditEventKind, Principal, Seams
from azathoth.revisions import CONTENT_DIGEST_PATTERN
from azathoth.sensitivity import DEFAULT_SENSITIVITY, Sensitivity
from azathoth.tools import ToolRepository
from azathoth.workflows import WorkflowProductionStateRepository, WorkflowRepository

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


class _Refused(Exception):
    """A request refused, with the status and message to answer it with."""

    def __init__(
        self,
        status: HTTPStatus,
        message: str,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def error_response(
    status: HTTPStatus,
    message: str,
) -> JSONResponse:
    """Return the JSON a remote refuses a request with: `{"error": message}`."""

    return JSONResponse({"error": message}, status_code=status)


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
    ) -> None:
        """Serve the given repositories; `environ` defaults to the process's own environment."""

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
        self._lock = asyncio.Lock()

    async def _blocking(
        self,
        work: Callable[[], Result],
    ) -> Result:
        """Run repository work off the event loop, one piece at a time."""

        async with self._lock:
            return await run_in_threadpool(work)

    def app(
        self,
    ) -> Starlette:
        """Return the Starlette application serving this remote."""

        return Starlette(
            routes=[
                Route("/health", self.health, methods=["GET"]),
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

    async def _capabilities(
        self,
        request: Request,
        principal: Principal,
    ) -> Answer:
        shown = self.seams.capabilities(accepts_restricted=self.accepts_restricted)

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
        self._decide(principal, Action.PUSH, digest)

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
        self._decide(principal, Action.READ_CONTENT, digest)
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

        for lineage in lineages:
            self._decide(principal, Action.PUSH, str(lineage))

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

        for root in asked.roots:
            self._decide(principal, Action.PULL, str(root))

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

        for lineage in asked.lineages:
            self._decide(principal, Action.PULL, str(lineage))

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
        action: Action,
        audited: AuditEventKind | None,
        handler: Handler,
    ) -> Response:
        """Answer one request for an authenticated principal, refusing and auditing as needed."""

        principal: Principal | None = None

        try:
            authorization = request.headers.get("Authorization")
            principal = await self._blocking(
                lambda: self.seams.authenticator.authenticate(authorization)
            )

            if principal is None:
                raise _Refused(HTTPStatus.UNAUTHORIZED, UNKNOWN_TOKEN_MESSAGE)

            self._decide(principal, action, None)
            response, resource, detail = await handler(request, principal)
        except _Refused as refused:
            if refused.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                self._audit(
                    AuditEventKind.REQUEST_DENIED,
                    principal,
                    f"{request.method} {request.url.path}",
                    refused.message,
                )

            return error_response(refused.status, refused.message)

        if audited is not None:
            self._audit(audited, principal, resource, detail)

        return response

    def _decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> None:
        """Refuse what the policy does not allow a principal to do, saying why."""

        decision = self.seams.policy.decide(principal, action, resource)

        if not decision.allowed:
            raise _Refused(HTTPStatus.FORBIDDEN, decision.reason or "Refused.")

    def _audit(
        self,
        kind: AuditEventKind,
        principal: Principal | None,
        resource: str | None,
        detail: str | None,
    ) -> None:
        """Tell the audit one thing the remote did, or refused."""

        self.seams.audit.record(
            AuditEvent(
                kind=kind,
                occurred_at=self._clock(),
                principal=None if principal is None else principal.name,
                resource=resource,
                detail=detail,
            )
        )

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
    "DIGEST_PATTERN",
    "UNKNOWN_TOKEN_MESSAGE",
    "RemoteServer",
    "error_response",
]
