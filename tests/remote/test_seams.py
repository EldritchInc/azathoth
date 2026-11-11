"""Tests for the seams a remote's plugins fill, and the core's own (ADR 0124)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from azathoth import __version__
from azathoth.persistence.database import SCHEMA_VERSION
from azathoth.remote import (
    REMOTE_PLUGIN_GROUP,
    SEAMS,
    Action,
    AuditEvent,
    AuditEventKind,
    Capabilities,
    Decision,
    NoAuditSink,
    OwnerOnlyPolicy,
    Principal,
    RemotePluginError,
    load_seams,
)

OWNER = Principal(name="eris", owner=True)

GUEST = Principal(name="guest")


class TokenAuthenticator:
    """Stands in for the core's token authenticator."""

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        return OWNER if authorization == "Bearer owner" else None


class TeamPolicy:
    """A plugin policy that lets anyone pull."""

    @property
    def edition(
        self,
    ) -> str:
        return "team"

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        if action is Action.PULL:
            return Decision(allowed=True)

        return Decision(allowed=False, reason="Only pulls.")


class ListAudit:
    """A plugin audit that keeps what it is told."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        self.events.append(event)


@dataclass(frozen=True)
class Installed:
    """An installed entry point, as `importlib.metadata` gives one."""

    name: str
    value: str
    factory: Callable[[], Any]

    def load(
        self,
    ) -> Any:
        return self.factory


def default(
    *installed: Installed,
) -> Any:
    return load_seams(default_authenticator=TokenAuthenticator(), installed=installed)


# The core's seams


def test_the_seams_and_their_group_are_named() -> None:
    assert REMOTE_PLUGIN_GROUP == "azathoth.remote"
    assert SEAMS == ("auth", "policy", "audit")


def test_without_plugins_the_core_fills_every_seam() -> None:
    authenticator = TokenAuthenticator()
    seams = load_seams(default_authenticator=authenticator, installed=())

    assert seams.authenticator is authenticator
    assert isinstance(seams.policy, OwnerOnlyPolicy)
    assert isinstance(seams.audit, NoAuditSink)
    assert seams.plugins == {}


def test_installed_entry_points_are_read_by_default() -> None:
    seams = load_seams(default_authenticator=TokenAuthenticator())

    assert seams.plugins == {}


def test_only_the_owner_may_do_anything() -> None:
    policy = OwnerOnlyPolicy()

    assert policy.edition == "community"

    for action in Action:
        assert policy.decide(OWNER, action, "workflow 1") == Decision(allowed=True)

    assert policy.decide(GUEST, Action.READ_CONTENT, None) == Decision(
        allowed=False,
        reason="guest may not read content on this remote: only its owner may.",
    )


def test_actions_are_named_as_messages_name_them() -> None:
    assert [action.description for action in Action] == [
        "read capabilities",
        "push",
        "pull",
        "read content",
        "manage tokens",
    ]


def test_a_refusal_says_why_and_a_permission_does_not() -> None:
    with pytest.raises(ValidationError, match="A refusal says why."):
        Decision(allowed=False)

    with pytest.raises(ValidationError, match="A permission gives no reason."):
        Decision(allowed=True, reason="Because.")


def test_the_core_audits_nothing() -> None:
    NoAuditSink().record(
        AuditEvent(kind=AuditEventKind.PUSH, occurred_at=datetime(2026, 11, 10, tzinfo=UTC))
    )


def test_audit_events_are_the_seven_a_remote_records() -> None:
    assert [kind.value for kind in AuditEventKind] == [
        "push",
        "pull",
        "content_read",
        "token_created",
        "token_revoked",
        "request_denied",
        "capabilities_read",
    ]

    with pytest.raises(ValidationError):
        AuditEvent(kind=AuditEventKind.PULL, occurred_at=datetime(2026, 11, 10))


# Plugins


def test_a_plugin_fills_its_seam_and_is_named() -> None:
    audit = ListAudit()
    seams = default(
        Installed("policy", "example_plugin:policy", TeamPolicy),
        Installed("audit", "example_plugin:audit", lambda: audit),
    )

    assert isinstance(seams.policy, TeamPolicy)
    assert seams.audit is audit
    assert isinstance(seams.authenticator, TokenAuthenticator)
    assert seams.plugins == {"policy": "example_plugin:policy", "audit": "example_plugin:audit"}


def test_an_auth_plugin_replaces_the_core_authenticator() -> None:
    seams = default(Installed("auth", "sso:authenticator", TokenAuthenticator))

    assert seams.plugins == {"auth": "sso:authenticator"}
    assert seams.authenticator.authenticate("Bearer owner") == OWNER


def test_two_plugins_for_one_seam_are_refused_naming_both() -> None:
    with pytest.raises(RemotePluginError) as caught:
        default(
            Installed("policy", "second:policy", TeamPolicy),
            Installed("policy", "first:policy", TeamPolicy),
        )

    assert str(caught.value) == (
        "Two plugins fill the remote's policy seam, first:policy and second:policy; uninstall "
        "one of them."
    )


def test_an_entry_point_naming_no_seam_is_refused() -> None:
    with pytest.raises(RemotePluginError) as caught:
        default(Installed("streams", "extra:streams", TeamPolicy))

    assert str(caught.value) == (
        "Remote plugin extra:streams names the seam 'streams'; a remote's seams are auth, policy "
        "and audit."
    )


@pytest.mark.parametrize(
    ("seam", "kind"),
    [("auth", "an Authenticator"), ("policy", "a Policy"), ("audit", "an AuditSink")],
)
def test_a_factory_making_something_else_is_refused(
    seam: str,
    kind: str,
) -> None:
    with pytest.raises(RemotePluginError) as caught:
        default(Installed(seam, "broken:factory", object))

    assert str(caught.value) == (
        f"Remote plugin broken:factory gave the {seam} seam an instance of object, which is not "
        f"{kind}."
    )


# Capabilities


def test_seams_tell_the_capabilities_of_their_remote() -> None:
    seams = default(Installed("policy", "example_plugin:policy", TeamPolicy))

    assert seams.capabilities(accepts_restricted=True) == Capabilities(
        protocol=1,
        azathoth_version=__version__,
        schema_version=SCHEMA_VERSION,
        edition="team",
        plugins={"policy": "example_plugin:policy"},
        accepts_restricted=True,
    )
    assert default().capabilities(accepts_restricted=False).edition == "community"
