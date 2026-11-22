"""Tests that a remote's installed audit is told of its tokens before they change (ADR 0136)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import azathoth.cli.remote as remote_commands
from azathoth.cli.remote import AUDIT_UNTOLD_MESSAGE, OPERATOR_PREFIX
from azathoth.remote import (
    AuditEvent,
    AuditEventKind,
    OwnerOnlyPolicy,
    RemotePluginError,
    Seams,
    SQLiteRemoteTokenRepository,
)
from tests.cli.test_remote_token_commands import ERIS, database, run
from tests.remote.test_service_routes import ListAudit

__all__ = ["database"]


class Watching(ListAudit):
    """An audit that keeps what it is told, and what tokens there were when it was told."""

    def __init__(
        self,
        look: Callable[[], object],
    ) -> None:
        super().__init__()
        self.look = look
        self.seen: list[object] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        super().record(event)
        self.seen.append(self.look())


class Down(ListAudit):
    """An audit that cannot be told anything."""

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        raise ConnectionError("the audit's database is down")


def installed(
    monkeypatch: pytest.MonkeyPatch,
    audit: ListAudit,
) -> None:
    """Have the token commands load seams whose audit is the one given."""

    def load(
        **options: Any,
    ) -> Seams:
        return Seams(
            authenticator=options["default_authenticator"],
            policy=OwnerOnlyPolicy(),
            audit=audit,
        )

    monkeypatch.setattr(remote_commands, "load_seams", load)


def names(
    database: Path,
) -> list[str]:
    return [token.name for token in SQLiteRemoteTokenRepository(database).tokens()]


def test_creating_a_token_is_told_before_it_is_made(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit = Watching(lambda: names(database))
    installed(monkeypatch, audit)

    assert run(capsys, "remote", "token", "create", "laptop")[0] == 0

    (event,) = audit.events

    assert (event.kind, event.principal, event.resource, event.detail) == (
        AuditEventKind.TOKEN_CREATED,
        f"operator:{ERIS.name}",
        "token laptop",
        "remote token create",
    )
    assert OPERATOR_PREFIX == "operator:"
    assert audit.seen == [[]]


def test_revoking_a_token_is_told_before_it_is_revoked(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    SQLiteRemoteTokenRepository(database).create("laptop")
    audit = Watching(lambda: names(database))
    installed(monkeypatch, audit)

    assert run(capsys, "remote", "token", "revoke", "laptop")[0] == 0

    (event,) = audit.events

    assert (event.kind, event.resource, event.detail) == (
        AuditEventKind.TOKEN_REVOKED,
        "token laptop",
        "remote token revoke",
    )
    assert audit.seen == [["laptop"]]
    assert names(database) == []


def test_a_token_change_that_fails_is_told_to_have_failed(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit = ListAudit()
    installed(monkeypatch, audit)

    status, _, errors = run(capsys, "remote", "token", "revoke", "nowhere")

    assert status == 1
    assert [event.kind for event in audit.events] == [
        AuditEventKind.TOKEN_REVOKED,
        AuditEventKind.REQUEST_FAILED,
    ]
    assert audit.events[1].detail == f"remote token revoke: {errors.strip()}"


@pytest.mark.parametrize("action", ["create", "revoke"])
def test_nothing_changes_when_the_audit_cannot_be_told(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    SQLiteRemoteTokenRepository(database).create("laptop")
    installed(monkeypatch, Down())

    status, output, errors = run(capsys, "remote", "token", action, "laptop")

    assert (status, output) == (1, "")
    assert errors == AUDIT_UNTOLD_MESSAGE.format(reason="the audit's database is down") + "\n"
    assert names(database) == ["laptop"]


def test_the_audit_untold_message_says_nothing_was_changed() -> None:
    assert AUDIT_UNTOLD_MESSAGE == (
        "The remote's audit could not be told of this, so nothing was changed: {reason}"
    )


def test_seams_that_cannot_be_loaded_change_nothing_and_say_why(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken(
        **options: Any,
    ) -> Seams:
        raise RemotePluginError("Two plugins fill the remote's audit seam, a and b.")

    monkeypatch.setattr(remote_commands, "load_seams", broken)

    status, _, errors = run(capsys, "remote", "token", "create", "laptop")

    assert status == 1
    assert errors == "Two plugins fill the remote's audit seam, a and b.\n"
    assert names(database) == []
