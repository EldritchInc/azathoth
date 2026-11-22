"""Tests that a remote answers requests together (ADR 0135).

Each test drives the server's ASGI application directly, on one event loop,
as uvicorn does, so requests sent together really are in flight together.
"""

import asyncio
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from azathoth.persistence.postgres import DEFAULT_POOL_SIZE
from azathoth.remote import (
    Action,
    AuditEvent,
    AuditEventKind,
    Decision,
    OwnerOnlyPolicy,
    Principal,
    Seams,
)
from azathoth.remote.server import DEFAULT_MAX_CONCURRENT, RemoteServer
from tests.remote.test_receiving import Bare

WAIT = 10.0
"""How long a test waits for another request before it counts as stuck."""

OWNER = Principal(name="laptop", owner=True)

BEARER = "Bearer azr_test"


class Owner:
    """An authenticator that names every caller the owner, after doing what it is told."""

    def __init__(
        self,
        before: Callable[[], object] = lambda: None,
    ) -> None:
        self._before = before

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        self._before()

        return OWNER


class HeldPolicy(OwnerOnlyPolicy):
    """The core's policy, which waits until it is let go before deciding."""

    def __init__(self) -> None:
        self.deciding = threading.Event()
        self.release = threading.Event()

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        self.deciding.set()
        self.release.wait(WAIT)

        return super().decide(principal, action, resource)


class ThreadAudit:
    """An audit that keeps what it is told, and the thread it was told on."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self.threads: list[threading.Thread] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        self.events.append(event)
        self.threads.append(threading.current_thread())


class Counting:
    """Counts the calls in progress at once, and the most there ever were."""

    def __init__(self) -> None:
        self.now = 0
        self.most = 0
        self._lock = threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            self.now += 1
            self.most = max(self.most, self.now)

        time.sleep(0.05)

        with self._lock:
            self.now -= 1


def server(
    *,
    authenticator: Owner | None = None,
    policy: OwnerOnlyPolicy | None = None,
    audit: ThreadAudit | None = None,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> RemoteServer:
    """Return a remote holding nothing, over the seams given."""

    held = Bare()

    return RemoteServer(
        workflows=held.workflows,
        tools=held.tools,
        benchmarks=held.benchmarks,
        content=held.content,
        production_states=held.production_states,
        portfolio=held.portfolio,
        seams=Seams(
            authenticator=authenticator if authenticator is not None else Owner(),
            policy=policy if policy is not None else OwnerOnlyPolicy(),
            audit=audit if audit is not None else ThreadAudit(),
        ),
        accepts_restricted=False,
        environ={},
        max_concurrent=max_concurrent,
    )


async def get(
    app: Any,
    path: str,
) -> int:
    """Send one GET to an ASGI application, and return the status it answered with."""

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(
        message: dict[str, Any],
    ) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"remote"), (b"authorization", BEARER.encode())],
            "client": ("127.0.0.1", 50000),
            "server": ("remote", 80),
        },
        receive,
        send,
    )

    (start,) = [message for message in sent if message["type"] == "http.response.start"]
    status: int = start["status"]

    return status


def test_a_remote_runs_as_many_calls_at_once_as_a_pool_holds_connections() -> None:
    assert DEFAULT_MAX_CONCURRENT == DEFAULT_POOL_SIZE == 8
    assert server().max_concurrent == DEFAULT_MAX_CONCURRENT


def test_a_remote_runs_at_least_one_call_at_once() -> None:
    with pytest.raises(ValueError, match="at least one call at once, not 0"):
        server(max_concurrent=0)


def test_two_requests_are_authenticated_at_the_same_time() -> None:
    both = threading.Barrier(2, timeout=WAIT)
    app = server(authenticator=Owner(both.wait)).app()

    async def together() -> list[int]:
        return list(await asyncio.gather(get(app, "/v1/capabilities"), get(app, "/v1/portfolio")))

    assert asyncio.run(together()) == [200, 200]


def test_a_policy_that_is_slow_to_decide_holds_up_no_other_request() -> None:
    policy = HeldPolicy()
    app = server(policy=policy).app()

    async def meanwhile() -> tuple[int, int, bool]:
        slow = asyncio.create_task(get(app, "/v1/capabilities"))

        while not policy.deciding.is_set():
            await asyncio.sleep(0.01)

        health = await asyncio.wait_for(get(app, "/health"), WAIT)
        still_deciding = not slow.done()
        policy.release.set()

        return health, await slow, still_deciding

    health, slow, still_deciding = asyncio.run(meanwhile())

    assert (health, slow) == (200, 200)
    assert still_deciding


def test_no_more_calls_run_at_once_than_the_remote_allows() -> None:
    counting = Counting()
    app = server(authenticator=Owner(counting), max_concurrent=2).app()

    async def many() -> list[int]:
        return list(await asyncio.gather(*(get(app, "/v1/portfolio") for _ in range(6))))

    assert asyncio.run(many()) == [200] * 6
    assert counting.most == 2


def test_requests_sent_together_run_together_up_to_the_limit() -> None:
    counting = Counting()
    app = server(authenticator=Owner(counting), max_concurrent=4).app()

    async def many() -> list[int]:
        return list(await asyncio.gather(*(get(app, "/v1/portfolio") for _ in range(4))))

    assert asyncio.run(many()) == [200] * 4
    assert counting.most == 4


def test_the_audit_is_told_off_the_event_loop_and_told_the_same_events() -> None:
    audit = ThreadAudit()
    app = server(audit=audit).app()

    async def two() -> tuple[int, int, threading.Thread]:
        capabilities = await get(app, "/v1/capabilities")
        portfolio = await get(app, "/v1/portfolio")

        return capabilities, portfolio, threading.current_thread()

    capabilities, portfolio, loop_thread = asyncio.run(two())

    assert (capabilities, portfolio) == (200, 200)
    assert [event.kind for event in audit.events] == [
        AuditEventKind.CAPABILITIES_READ,
        AuditEventKind.PORTFOLIO_READ,
    ]
    assert all(thread is not loop_thread for thread in audit.threads)


def test_one_remote_serves_one_event_loop_after_another() -> None:
    app = server(max_concurrent=1).app()

    assert asyncio.run(get(app, "/v1/capabilities")) == 200
    assert asyncio.run(get(app, "/v1/capabilities")) == 200
