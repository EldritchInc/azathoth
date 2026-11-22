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
    """What the application answered: its status, its body, and the body as JSON."""

    def __init__(
        self,
        status: int,
        body: bytes,
    ) -> None:
        self.status = status
        self.body = body

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

    return Answer(start["status"], content)


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
