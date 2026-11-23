"""A caller of a remote's ASGI application, on one event loop, as uvicorn serves it.

Tests that need requests in flight together, or a body of their own, call
the application directly rather than through a test client.
"""

import asyncio
import json
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


async def send(
    app: Any,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    authorization: str | None = BEARER,
) -> Answer:
    """Send one request to an ASGI application, and return its answer."""

    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered

        if delivered:
            return {"type": "http.disconnect"}

        delivered = True

        return {"type": "http.request", "body": body, "more_body": False}

    async def reply(
        message: dict[str, Any],
    ) -> None:
        sent.append(message)

    headers = [(b"host", b"remote"), (b"content-type", b"application/json")]

    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("remote", 80),
        },
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

        return AsgiResponse(call(self.app, method, url, raw=body, authorization=authorization))

    def close(
        self,
    ) -> None:
        self.closed = True
