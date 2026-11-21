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
    HIGH_PRIVILEGE_ACTIONS,
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
        assert policy.decide(GUEST, action, "workflow 1") == Decision(
            allowed=False,
            reason=f"guest may not {action.description} on this remote: only its owner may.",
        )

    assert policy.decide(GUEST, Action.READ_CONTENT, None) == Decision(
        allowed=False,
        reason="guest may not read content on this remote: only its owner may.",
    )


def test_the_catalog_is_every_action_of_adrs_0127_and_0133_in_their_order() -> None:
    assert [action.value for action in Action] == [
        "read_capabilities",
        "push",
        "pull",
        "read_content",
        "read_portfolio",
        "read_catalog",
        "read_runs",
        "read_restricted",
        "import_workflow",
        "import_benchmark",
        "import_goal",
        "import_tool",
        "import_process_tool",
        "tool_from_mcp",
        "install_standard_tools",
        "run_workflow",
        "invoke",
        "promote",
        "authorize_model",
        "declare_policy",
        "manage_judges",
        "annotate_run",
        "edit_benchmark",
        "run_benchmark",
        "optimize",
        "read_spend",
        "manage_tokens",
    ]


def test_the_protocols_actions_keep_their_values() -> None:
    assert Action.READ_CAPABILITIES.value == "read_capabilities"
    assert Action.PUSH.value == "push"
    assert Action.PULL.value == "pull"
    assert Action.READ_CONTENT.value == "read_content"
    assert Action.MANAGE_TOKENS.value == "manage_tokens"
    assert Action.READ_PORTFOLIO.value == "read_portfolio"


def test_actions_are_named_as_messages_name_them() -> None:
    assert {action: action.description for action in Action} == {
        Action.READ_CAPABILITIES: "read capabilities",
        Action.PUSH: "push",
        Action.PULL: "pull",
        Action.READ_CONTENT: "read content",
        Action.READ_PORTFOLIO: "read portfolio",
        Action.READ_CATALOG: "read the catalog",
        Action.READ_RUNS: "read runs",
        Action.READ_RESTRICTED: "read restricted data",
        Action.IMPORT_WORKFLOW: "import workflow",
        Action.IMPORT_BENCHMARK: "import benchmark",
        Action.IMPORT_GOAL: "import goal",
        Action.IMPORT_TOOL: "import tool",
        Action.IMPORT_PROCESS_TOOL: "import process tool",
        Action.TOOL_FROM_MCP: "make a tool from an MCP server",
        Action.INSTALL_STANDARD_TOOLS: "install standard tools",
        Action.RUN_WORKFLOW: "run workflow",
        Action.INVOKE: "invoke",
        Action.PROMOTE: "promote",
        Action.AUTHORIZE_MODEL: "authorize model",
        Action.DECLARE_POLICY: "declare policy",
        Action.MANAGE_JUDGES: "manage judges",
        Action.ANNOTATE_RUN: "annotate run",
        Action.EDIT_BENCHMARK: "edit benchmark",
        Action.RUN_BENCHMARK: "run benchmark",
        Action.OPTIMIZE: "optimize",
        Action.READ_SPEND: "read spend",
        Action.MANAGE_TOKENS: "manage tokens",
    }


def test_five_actions_are_high_privilege() -> None:
    assert (
        frozenset(
            {
                Action.IMPORT_PROCESS_TOOL,
                Action.TOOL_FROM_MCP,
                Action.INSTALL_STANDARD_TOOLS,
                Action.READ_RESTRICTED,
                Action.MANAGE_TOKENS,
            }
        )
        == HIGH_PRIVILEGE_ACTIONS
    )
    assert [action for action in Action if action.high_privilege] == [
        Action.READ_RESTRICTED,
        Action.IMPORT_PROCESS_TOOL,
        Action.TOOL_FROM_MCP,
        Action.INSTALL_STANDARD_TOOLS,
        Action.MANAGE_TOKENS,
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


def test_audit_events_are_the_eight_a_remote_records() -> None:
    assert [kind.value for kind in AuditEventKind] == [
        "push",
        "pull",
        "content_read",
        "token_created",
        "token_revoked",
        "request_denied",
        "capabilities_read",
        "portfolio_read",
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
