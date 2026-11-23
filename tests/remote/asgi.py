"""A caller of a remote's ASGI application, on one event loop, as uvicorn serves it.

Tests that need requests in flight together, or a body of their own, call
the application directly rather than through a test client.
"""

import asyncio
import json
import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

BEARER = "Bearer azr_test"
"""The header tests send when the authenticator names every caller alike."""


class Answer:
    """What the application answered: its status, its headers, its body, and the body as JSON."""

    def __init__(
        self,
        status: int,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = {} if headers is None else headers

    def json(self) -> Any:
        return json.loads(self.body)


def scope(
    method: str,
    path: str,
    *,
    authorization: str | None = BEARER,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the ASGI scope of one request, its query string apart from its path."""

    sent = [(b"host", b"remote"), (b"content-type", b"application/json")]
    route, _, query = path.partition("?")

    if authorization is not None:
        sent.append((b"authorization", authorization.encode()))

    for name, value in (headers or {}).items():
        if name.lower() != "authorization":
            sent.append((name.lower().encode(), value.encode()))

    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": route,
        "raw_path": route.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": sent,
        "client": ("127.0.0.1", 50000),
        "server": ("remote", 80),
    }


async def send(
    app: Any,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    authorization: str | None = BEARER,
    headers: dict[str, str] | None = None,
) -> Answer:
    """Send one request to an ASGI application, and return its answer."""

    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered

        if delivered:
            #
            # The client stays until the answer is sent whole, as one
            # following a stream does; the application stops listening
            # once it has answered.
            #
            await asyncio.Event().wait()

        delivered = True

        return {"type": "http.request", "body": body, "more_body": False}

    async def reply(
        message: dict[str, Any],
    ) -> None:
        sent.append(message)

    await app(
        scope(method, path, authorization=authorization, headers=headers),
        receive,
        reply,
    )

    (start,) = [message for message in sent if message["type"] == "http.response.start"]
    content = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )

    answered = {name.decode().lower(): value.decode() for name, value in start.get("headers", [])}

    return Answer(start["status"], content, answered)


def call(
    app: Any,
    method: str,
    path: str,
    *,
    body: object | None = None,
    raw: bytes | None = None,
    authorization: str | None = BEARER,
) -> Answer:
    """Send one request on an event loop of its own, its body `body` as JSON or `raw` as is."""

    payload = raw if raw is not None else b"" if body is None else json.dumps(body).encode()

    return asyncio.run(send(app, method, path, body=payload, authorization=authorization))


class AsgiResponse:
    """An application's answer, as an HTTP client's response reads."""

    def __init__(
        self,
        answer: Answer,
    ) -> None:
        self.status_code = answer.status
        self.content = answer.body

    @property
    def is_success(
        self,
    ) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.content)


class AsgiStream:
    """An application's answer as it is sent, read line by line as a streaming client reads it."""

    def __init__(
        self,
        status: int,
        chunks: "queue.Queue[bytes | None]",
    ) -> None:
        self.status_code = status
        self._chunks = chunks

    @property
    def is_success(
        self,
    ) -> bool:
        return 200 <= self.status_code < 300

    def _received(
        self,
    ) -> Iterator[bytes]:
        while (chunk := self._chunks.get(timeout=30)) is not None:
            yield chunk

    def iter_lines(
        self,
    ) -> Iterator[str]:
        pending = ""

        for chunk in self._received():
            pending += chunk.decode()

            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                yield line.rstrip("\r")

        if pending:
            yield pending

    def read(
        self,
    ) -> bytes:
        return b"".join(self._received())


class AsgiHttp:
    """An HTTP client that sends each request to an ASGI application in process.

    It is what a client of a remote is given in tests, so the client speaks
    to the remote's own server, not to a fake of it. It notes the requests
    it sends, and the `Authorization` each was sent with.
    """

    def __init__(
        self,
        app: Any,
    ) -> None:
        self.app = app
        self.sent: list[tuple[str, str, bytes]] = []
        self.authorizations: list[str | None] = []
        self.closed = False

    def request(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> AsgiResponse:
        body = content.encode() if isinstance(content, str) else content or b""
        self.sent.append((method, url, body))
        authorization = (headers or {}).get("Authorization")
        self.authorizations.append(authorization)

        return AsgiResponse(
            asyncio.run(
                send(self.app, method, url, body=body, authorization=authorization, headers=headers)
            )
        )

    @contextmanager
    def stream(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Iterator[AsgiStream]:
        """Send one request, and read its answer as the application sends it.

        The application answers on a thread of its own; leaving the stream
        before it has answered whole tells it the client has gone.
        """

        body = content.encode() if isinstance(content, str) else content or b""
        self.sent.append((method, url, body))
        authorization = (headers or {}).get("Authorization")
        self.authorizations.append(authorization)
        chunks: queue.Queue[bytes | None] = queue.Queue()
        start: dict[str, Any] = {}
        started = threading.Event()
        running: dict[str, Any] = {}

        async def answer() -> None:
            gone = asyncio.Event()
            running["loop"] = asyncio.get_running_loop()
            running["gone"] = gone
            delivered = False

            async def receive() -> dict[str, Any]:
                nonlocal delivered

                if delivered:
                    await gone.wait()

                    return {"type": "http.disconnect"}

                delivered = True

                return {"type": "http.request", "body": body, "more_body": False}

            async def reply(
                message: dict[str, Any],
            ) -> None:
                if message["type"] == "http.response.start":
                    start.update(message)
                    started.set()
                elif message["type"] == "http.response.body":
                    chunks.put(message.get("body", b""))

                    if not message.get("more_body", False):
                        chunks.put(None)

            try:
                await self.app(
                    scope(method, url, authorization=authorization, headers=headers),
                    receive,
                    reply,
                )
            finally:
                chunks.put(None)
                started.set()

        answering = threading.Thread(target=lambda: asyncio.run(answer()), daemon=True)
        answering.start()
        started.wait(30)

        try:
            yield AsgiStream(start.get("status", 500), chunks)
        finally:
            if "loop" in running:
                with suppress(RuntimeError):
                    running["loop"].call_soon_threadsafe(running["gone"].set)

            answering.join(10)

    def close(
        self,
    ) -> None:
        self.closed = True
