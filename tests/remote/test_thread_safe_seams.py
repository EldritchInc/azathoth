"""Tests that the core's seams and content stores may be called from many threads at once.

A remote answers requests together and calls them from the threads it
answers on (ADR 0135), so each must give every thread the answer it would
give one alone.
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from azathoth.inputs import InMemoryContentStore, SQLiteContentStore, content_bytes_digest
from azathoth.inputs.s3_store import S3ContentLocation, S3ContentStore
from azathoth.remote import (
    Action,
    AuditEvent,
    AuditEventKind,
    NoAuditSink,
    OwnerOnlyPolicy,
    Principal,
    SQLiteRemoteTokenRepository,
    TokenAuthenticator,
    load_seams,
)
from tests.remote.test_concurrent_server import WAIT

THREADS = 16

ROUNDS = 25


def at_once(
    work: Callable[[int], None],
) -> list[BaseException]:
    """Run `work(index)` on many threads, released together, and return what they raised."""

    start = threading.Barrier(THREADS, timeout=WAIT)
    failures: list[BaseException] = []

    def run(
        index: int,
    ) -> None:
        try:
            start.wait()
            work(index)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(THREADS)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(WAIT)

    return failures


# The seams


def test_the_token_authenticator_names_each_caller_rightly_from_many_threads(
    tmp_path: Path,
) -> None:
    tokens = SQLiteRemoteTokenRepository(tmp_path / "remote.db")
    secrets = {name: tokens.create(name).secret for name in ("laptop", "desktop")}
    tokens.revoke("desktop")
    authenticator = TokenAuthenticator(tokens)
    load_seams(default_authenticator=authenticator, installed=())

    def authenticate(
        index: int,
    ) -> None:
        for _ in range(ROUNDS):
            laptop = authenticator.authenticate(f"Bearer {secrets['laptop']}")
            assert laptop is not None
            assert (laptop.name, laptop.owner) == ("laptop", True)
            assert authenticator.authenticate(f"Bearer {secrets['desktop']}") is None
            assert authenticator.authenticate("Bearer azr_unknown") is None
            assert authenticator.authenticate(None) is None

    assert at_once(authenticate) == []


def test_the_owner_only_policy_decides_alike_on_every_thread() -> None:
    policy = OwnerOnlyPolicy()
    owner = Principal(name="laptop", owner=True)
    guest = Principal(name="guest")

    def decide(
        index: int,
    ) -> None:
        for action in Action:
            assert policy.decide(owner, action, None).allowed
            assert not policy.decide(guest, action, f"resource-{index}").allowed

    assert at_once(decide) == []


def test_the_core_audit_takes_events_from_every_thread() -> None:
    audit = NoAuditSink()

    def record(
        index: int,
    ) -> None:
        for _ in range(ROUNDS):
            audit.record(
                AuditEvent(
                    kind=AuditEventKind.CAPABILITIES_READ,
                    occurred_at=datetime(2026, 11, 22, tzinfo=UTC),
                    principal=f"thread-{index}",
                )
            )

    assert at_once(record) == []


def test_the_seams_are_made_once_and_serve_every_thread(
    tmp_path: Path,
) -> None:
    seams = load_seams(
        default_authenticator=TokenAuthenticator(SQLiteRemoteTokenRepository(tmp_path / "r.db")),
        installed=(),
    )
    seen: list[tuple[int, int, int]] = []

    def look(
        index: int,
    ) -> None:
        seen.append((id(seams.authenticator), id(seams.policy), id(seams.audit)))

    assert at_once(look) == []
    assert len(set(seen)) == 1


# The content stores


def blob(
    index: int,
) -> bytes:
    return f"content {index % 4}".encode()


def stores_and_reads_alike(
    store: Any,
) -> None:
    """Have every thread store and read content, some of it the same, and check what each saw."""

    def put_and_get(
        index: int,
    ) -> None:
        for _ in range(ROUNDS):
            content = blob(index)
            digest = store.put(content)

            assert digest == content_bytes_digest(content)
            assert store.contains(digest)
            assert store.get(digest) == content
            assert store.get("e" * 64) is None

    assert at_once(put_and_get) == []

    for index in range(4):
        assert store.get(content_bytes_digest(blob(index))) == blob(index)


def test_content_in_memory_is_stored_and_read_alike_from_many_threads() -> None:
    stores_and_reads_alike(InMemoryContentStore())


def test_content_in_a_database_is_stored_and_read_alike_from_many_threads(
    tmp_path: Path,
) -> None:
    stores_and_reads_alike(SQLiteContentStore(tmp_path / "content.db"))


class SharedClient:
    """An S3 client that keeps objects, and notes the threads that used it."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.threads: set[int] = set()
        self._lock = threading.Lock()

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        IfNoneMatch: str,
    ) -> None:
        with self._lock:
            self.threads.add(threading.get_ident())
            self.objects.setdefault(Key, Body)


def test_the_s3_store_makes_its_client_once_and_shares_it_between_threads() -> None:
    pytest.importorskip("boto3")
    made: list[SharedClient] = []

    def factory() -> SharedClient:
        made.append(SharedClient())

        return made[-1]

    store = S3ContentStore(S3ContentLocation.parse("s3://bucket/content"), client_factory=factory)

    def put(
        index: int,
    ) -> None:
        for _ in range(ROUNDS):
            store.put(blob(index))

    assert at_once(put) == []
    assert len(made) == 1
    assert len(made[0].threads) > 1
    assert len(made[0].objects) == 4


# The documentation


def test_writing_a_plugin_says_seams_are_called_from_many_threads() -> None:
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "remote" / "README.md"
    text = readme.read_text(encoding="utf-8")
    writing = text[text.index("### Writing a Plugin") : text.index("## The Server")]

    assert "safe to call from several threads at once" in writing
    assert "A factory\nruns once, when the remote starts" in writing
    assert "An audit must keep every event" in writing
