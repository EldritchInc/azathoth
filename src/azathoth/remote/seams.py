"""The seams a remote's plugins fill: who a caller is, what they may do, and the audit (ADR 0124).

A remote asks its `Authenticator` who a request's caller is, its `Policy`
whether they may do what they ask, and tells its `AuditSink` what was done.
The core fills each seam itself: tokens it issues authenticate, only the
owner may do anything, and nothing is audited. A plugin replaces one by an
entry point in the `azathoth.remote` group, named for its seam, whose object
is a factory taking no arguments.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import entry_points
from typing import Any, Final, Protocol, runtime_checkable

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth import __version__
from azathoth.persistence.database import SCHEMA_VERSION
from azathoth.remote.protocol import DEFAULT_EDITION, PROTOCOL_VERSION, Capabilities

REMOTE_PLUGIN_GROUP: Final = "azathoth.remote"
"""The entry-point group a remote's plugins are installed under."""

AUTH_SEAM: Final = "auth"
"""The seam that says who a request's caller is."""

POLICY_SEAM: Final = "policy"
"""The seam that says what a caller may do."""

AUDIT_SEAM: Final = "audit"
"""The seam told what a remote did, and what it refused."""

SEAMS: Final = (AUTH_SEAM, POLICY_SEAM, AUDIT_SEAM)
"""Every seam a plugin may fill, in the order messages name them."""


class RemotePluginError(RuntimeError):
    """The plugins installed for a remote cannot serve it."""


class Principal(BaseModel):
    """Who a request's caller is, as its authenticator says.

    The owner is whoever runs the remote; the default policy lets only the
    owner do anything.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str = Field(
        min_length=1,
    )

    owner: bool = False


class Action(StrEnum):
    """What a caller asks a remote to do: the action catalog (ADRs 0127 and 0133).

    Every route of a remote asks its policy for one of these, and for the
    resource it acts on when it names one. The catalog is stable within
    1.x: it grows only by additions, and no value changes. It names what can
    be done; a policy decides who may.
    """

    READ_CAPABILITIES = "read_capabilities"
    PUSH = "push"
    PULL = "pull"
    READ_CONTENT = "read_content"
    READ_PORTFOLIO = "read_portfolio"
    READ_CATALOG = "read_catalog"
    READ_RUNS = "read_runs"
    READ_RESTRICTED = "read_restricted"
    IMPORT_WORKFLOW = "import_workflow"
    IMPORT_BENCHMARK = "import_benchmark"
    IMPORT_GOAL = "import_goal"
    IMPORT_TOOL = "import_tool"
    IMPORT_PROCESS_TOOL = "import_process_tool"
    TOOL_FROM_MCP = "tool_from_mcp"
    INSTALL_STANDARD_TOOLS = "install_standard_tools"
    RUN_WORKFLOW = "run_workflow"
    INVOKE = "invoke"
    PROMOTE = "promote"
    AUTHORIZE_MODEL = "authorize_model"
    DECLARE_POLICY = "declare_policy"
    MANAGE_JUDGES = "manage_judges"
    ANNOTATE_RUN = "annotate_run"
    EDIT_BENCHMARK = "edit_benchmark"
    RUN_BENCHMARK = "run_benchmark"
    OPTIMIZE = "optimize"
    READ_SPEND = "read_spend"
    MANAGE_TOKENS = "manage_tokens"

    @property
    def description(
        self,
    ) -> str:
        """Return the action as a message names it, such as `read content`.

        A refusal says that its caller "may not" do this, so the few whose
        value would not read as a phrase are worded.
        """

        return _DESCRIPTIONS.get(self, self.value.replace("_", " "))

    @property
    def high_privilege(
        self,
    ) -> bool:
        """Return whether the action is one of the five of high privilege (ADR 0127)."""

        return self in HIGH_PRIVILEGE_ACTIONS


_DESCRIPTIONS: Final[Mapping[Action, str]] = {
    Action.READ_CATALOG: "read the catalog",
    Action.READ_RESTRICTED: "read restricted data",
    Action.TOOL_FROM_MCP: "make a tool from an MCP server",
}
"""The actions whose description is worded rather than read from their value."""

HIGH_PRIVILEGE_ACTIONS: Final = frozenset(
    {
        Action.IMPORT_PROCESS_TOOL,
        Action.TOOL_FROM_MCP,
        Action.INSTALL_STANDARD_TOOLS,
        Action.READ_RESTRICTED,
        Action.MANAGE_TOKENS,
    }
)
"""The five actions of high privilege (ADR 0127).

Each lets a caller run code on the remote, read what should not spread, or
let others in: a process tool runs a command; making a tool from an MCP
server starts one; the standard tools are installed for everyone;
restricted data is not to spread; and tokens let others in.
"""


class Decision(BaseModel):
    """Whether a caller may do what they ask, and, when not, why."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    allowed: bool

    reason: str | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def require_a_reason_to_deny(
        self,
    ) -> "Decision":
        """Require a reason for a refusal, and none for a permission."""

        if not self.allowed and self.reason is None:
            raise ValueError("A refusal says why.")

        if self.allowed and self.reason is not None:
            raise ValueError("A permission gives no reason.")

        return self


class AuditEventKind(StrEnum):
    """What a remote tells its audit it did, or refused."""

    PUSH = "push"
    PULL = "pull"
    CONTENT_READ = "content_read"
    TOKEN_CREATED = "token_created"
    TOKEN_REVOKED = "token_revoked"
    REQUEST_DENIED = "request_denied"
    CAPABILITIES_READ = "capabilities_read"
    PORTFOLIO_READ = "portfolio_read"


class AuditEvent(BaseModel):
    """One thing a remote did or refused, and for whom.

    A request refused before its caller is known names no principal.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    kind: AuditEventKind

    occurred_at: AwareDatetime

    principal: str | None = None

    resource: str | None = None

    detail: str | None = None


@runtime_checkable
class Authenticator(Protocol):
    """Says who a request's caller is, from its `Authorization` header."""

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        """Return the caller a header names, or None when it names no one this remote knows."""

        ...


@runtime_checkable
class Policy(Protocol):
    """Says whether a caller may do what they ask, and which edition the remote is."""

    @property
    def edition(
        self,
    ) -> str:
        """Return the edition the remote names in its capabilities."""

        ...

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        """Return whether a caller may do one action, to a resource if it names one."""

        ...


@runtime_checkable
class AuditSink(Protocol):
    """Is told what a remote did, and what it refused."""

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        """Record one event."""

        ...


class OwnerOnlyPolicy:
    """The core's policy: the owner may do anything, and no one else may do anything."""

    @property
    def edition(
        self,
    ) -> str:
        """Return the community edition."""

        return DEFAULT_EDITION

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        """Allow the owner, and refuse anyone else, saying so."""

        if principal.owner:
            return Decision(allowed=True)

        return Decision(
            allowed=False,
            reason=(
                f"{principal.name} may not {action.description} on this remote: only its owner may."
            ),
        )


class NoAuditSink:
    """The core's audit, which records nothing."""

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        """Record nothing."""


class PluginEntryPoint(Protocol):
    """An installed entry point, as a remote reads one."""

    @property
    def name(
        self,
    ) -> str:
        """Return the seam the entry point fills."""

        ...

    @property
    def value(
        self,
    ) -> str:
        """Return the object it names, as `module:attribute`."""

        ...

    def load(
        self,
    ) -> Any:
        """Import and return the object it names."""

        ...


@dataclass(frozen=True)
class Seams:
    """What fills each of a remote's seams, and which plugin, if any, fills each."""

    authenticator: Authenticator
    policy: Policy
    audit: AuditSink
    plugins: Mapping[str, str] = field(default_factory=dict)

    def capabilities(
        self,
        *,
        accepts_restricted: bool,
    ) -> Capabilities:
        """Return the capabilities a remote served by these seams tells its clients."""

        return Capabilities(
            protocol=PROTOCOL_VERSION,
            azathoth_version=__version__,
            schema_version=SCHEMA_VERSION,
            edition=self.policy.edition,
            plugins=dict(self.plugins),
            accepts_restricted=accepts_restricted,
        )


def _plugin_entry_points(
    installed: Iterable[PluginEntryPoint],
) -> dict[str, PluginEntryPoint]:
    """Return the one installed entry point of each seam a plugin fills.

    Raises:
        RemotePluginError: An entry point names no seam, or two fill one.
    """

    chosen: dict[str, PluginEntryPoint] = {}

    for entry_point in installed:
        if entry_point.name not in SEAMS:
            raise RemotePluginError(
                f"Remote plugin {entry_point.value} names the seam {entry_point.name!r}; a "
                f"remote's seams are {', '.join(SEAMS[:-1])} and {SEAMS[-1]}."
            )

        other = chosen.get(entry_point.name)

        if other is not None:
            first, second = sorted((other.value, entry_point.value))

            raise RemotePluginError(
                f"Two plugins fill the remote's {entry_point.name} seam, {first} and {second}; "
                "uninstall one of them."
            )

        chosen[entry_point.name] = entry_point

    return chosen


def _made(
    entry_point: PluginEntryPoint,
    expected: type[Any],
    kind: str,
) -> Any:
    """Return what one plugin's factory makes, or refuse it when it is not its seam's kind.

    Raises:
        RemotePluginError: The factory made something else.
    """

    made = entry_point.load()()

    if not isinstance(made, expected):
        raise RemotePluginError(
            f"Remote plugin {entry_point.value} gave the {entry_point.name} seam an instance "
            f"of {type(made).__name__}, which is not {kind}."
        )

    return made


def load_seams(
    *,
    default_authenticator: Authenticator,
    installed: Iterable[PluginEntryPoint] | None = None,
) -> Seams:
    """Return what fills each seam: the one plugin installed for it, or the core's own.

    `installed` defaults to the entry points of the `azathoth.remote`
    group. The core's authenticator is given, since it reads the remote's
    database.

    Raises:
        RemotePluginError: An entry point names no seam, two fill one, or a
            factory makes something that is not its seam's kind.
    """

    chosen = _plugin_entry_points(
        entry_points(group=REMOTE_PLUGIN_GROUP) if installed is None else installed
    )

    authenticator: Authenticator = default_authenticator
    policy: Policy = OwnerOnlyPolicy()
    audit: AuditSink = NoAuditSink()

    if AUTH_SEAM in chosen:
        authenticator = _made(chosen[AUTH_SEAM], Authenticator, "an Authenticator")

    if POLICY_SEAM in chosen:
        policy = _made(chosen[POLICY_SEAM], Policy, "a Policy")

    if AUDIT_SEAM in chosen:
        audit = _made(chosen[AUDIT_SEAM], AuditSink, "an AuditSink")

    return Seams(
        authenticator=authenticator,
        policy=policy,
        audit=audit,
        plugins={seam: chosen[seam].value for seam in SEAMS if seam in chosen},
    )


__all__ = [
    "AUDIT_SEAM",
    "AUTH_SEAM",
    "HIGH_PRIVILEGE_ACTIONS",
    "POLICY_SEAM",
    "REMOTE_PLUGIN_GROUP",
    "SEAMS",
    "Action",
    "AuditEvent",
    "AuditEventKind",
    "AuditSink",
    "Authenticator",
    "Decision",
    "NoAuditSink",
    "OwnerOnlyPolicy",
    "PluginEntryPoint",
    "Policy",
    "Principal",
    "RemotePluginError",
    "Seams",
    "load_seams",
]
