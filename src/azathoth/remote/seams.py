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

MAX_EDITION_DETAIL_LENGTH: Final = 200
"""The longest a policy's edition detail may be."""


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
    """What a remote tells its audit it did, or refused (ADRs 0124 and 0127).

    The protocol's eight come first. After them is one kind for each
    outcome of an action that changes something or reads restricted data,
    so promoting and rolling back, both the `promote` action, are told
    apart. Reading what is not restricted is not audited. A remote tells
    its audit before it acts, so `request_failed` follows an event whose
    act then failed (ADR 0136). Kinds grow only by additions within 1.x,
    and no value changes.
    """

    PUSH = "push"
    PULL = "pull"
    CONTENT_READ = "content_read"
    TOKEN_CREATED = "token_created"
    TOKEN_REVOKED = "token_revoked"
    REQUEST_DENIED = "request_denied"
    CAPABILITIES_READ = "capabilities_read"
    PORTFOLIO_READ = "portfolio_read"
    WORKFLOW_IMPORTED = "workflow_imported"
    BENCHMARK_IMPORTED = "benchmark_imported"
    GOAL_IMPORTED = "goal_imported"
    TOOL_IMPORTED = "tool_imported"
    PROCESS_TOOL_IMPORTED = "process_tool_imported"
    TOOL_MADE_FROM_MCP = "tool_made_from_mcp"
    STANDARD_TOOLS_INSTALLED = "standard_tools_installed"
    WORKFLOW_RUN = "workflow_run"
    STEP_TRIED = "step_tried"
    WORKFLOW_INVOKED = "workflow_invoked"
    WORKFLOW_PROMOTED = "workflow_promoted"
    WORKFLOW_ROLLED_BACK = "workflow_rolled_back"
    MODEL_AUTHORIZED = "model_authorized"
    MODEL_REMOVED = "model_removed"
    DATA_POLICY_DECLARED = "data_policy_declared"
    JUDGE_ADDED = "judge_added"
    JUDGE_REMOVED = "judge_removed"
    RUN_ANNOTATED = "run_annotated"
    RUN_RESUMED = "run_resumed"
    BENCHMARK_CREATED = "benchmark_created"
    BENCHMARK_CASE_ADDED = "benchmark_case_added"
    BENCHMARK_CASE_CHANGED = "benchmark_case_changed"
    BENCHMARK_CASE_REMOVED = "benchmark_case_removed"
    BENCHMARK_RUN = "benchmark_run"
    WORKFLOW_OPTIMIZED = "workflow_optimized"
    RESTRICTED_READ = "restricted_read"
    REQUEST_FAILED = "request_failed"

    @property
    def action(
        self,
    ) -> Action | None:
        """Return the action this kind records, or None for a refusal or a failure."""

        return _KIND_ACTIONS.get(self)


_KIND_ACTIONS: Final[Mapping[AuditEventKind, Action]] = {
    AuditEventKind.PUSH: Action.PUSH,
    AuditEventKind.PULL: Action.PULL,
    AuditEventKind.CONTENT_READ: Action.READ_CONTENT,
    AuditEventKind.TOKEN_CREATED: Action.MANAGE_TOKENS,
    AuditEventKind.TOKEN_REVOKED: Action.MANAGE_TOKENS,
    AuditEventKind.CAPABILITIES_READ: Action.READ_CAPABILITIES,
    AuditEventKind.PORTFOLIO_READ: Action.READ_PORTFOLIO,
    AuditEventKind.WORKFLOW_IMPORTED: Action.IMPORT_WORKFLOW,
    AuditEventKind.BENCHMARK_IMPORTED: Action.IMPORT_BENCHMARK,
    AuditEventKind.GOAL_IMPORTED: Action.IMPORT_GOAL,
    AuditEventKind.TOOL_IMPORTED: Action.IMPORT_TOOL,
    AuditEventKind.PROCESS_TOOL_IMPORTED: Action.IMPORT_PROCESS_TOOL,
    AuditEventKind.TOOL_MADE_FROM_MCP: Action.TOOL_FROM_MCP,
    AuditEventKind.STANDARD_TOOLS_INSTALLED: Action.INSTALL_STANDARD_TOOLS,
    AuditEventKind.WORKFLOW_RUN: Action.RUN_WORKFLOW,
    AuditEventKind.STEP_TRIED: Action.RUN_WORKFLOW,
    AuditEventKind.WORKFLOW_INVOKED: Action.INVOKE,
    AuditEventKind.WORKFLOW_PROMOTED: Action.PROMOTE,
    AuditEventKind.WORKFLOW_ROLLED_BACK: Action.PROMOTE,
    AuditEventKind.MODEL_AUTHORIZED: Action.AUTHORIZE_MODEL,
    AuditEventKind.MODEL_REMOVED: Action.AUTHORIZE_MODEL,
    AuditEventKind.DATA_POLICY_DECLARED: Action.DECLARE_POLICY,
    AuditEventKind.JUDGE_ADDED: Action.MANAGE_JUDGES,
    AuditEventKind.JUDGE_REMOVED: Action.MANAGE_JUDGES,
    AuditEventKind.RUN_ANNOTATED: Action.ANNOTATE_RUN,
    AuditEventKind.RUN_RESUMED: Action.ANNOTATE_RUN,
    AuditEventKind.BENCHMARK_CREATED: Action.EDIT_BENCHMARK,
    AuditEventKind.BENCHMARK_CASE_ADDED: Action.EDIT_BENCHMARK,
    AuditEventKind.BENCHMARK_CASE_CHANGED: Action.EDIT_BENCHMARK,
    AuditEventKind.BENCHMARK_CASE_REMOVED: Action.EDIT_BENCHMARK,
    AuditEventKind.BENCHMARK_RUN: Action.RUN_BENCHMARK,
    AuditEventKind.WORKFLOW_OPTIMIZED: Action.OPTIMIZE,
    AuditEventKind.RESTRICTED_READ: Action.READ_RESTRICTED,
}
"""The action each kind records; a refusal, `request_denied`, and a failure, `request_failed`,
record none."""


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
    """Says who a request's caller is, from its `Authorization` header.

    A remote calls it from several threads at once (ADR 0135), so it must be
    safe to call concurrently.
    """

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        """Return the caller a header names, or None when it names no one this remote knows."""

        ...


@runtime_checkable
class Policy(Protocol):
    """Says whether a caller may do what they ask, and which edition the remote is.

    A policy may also have an `edition_detail` property: one printable line
    of at most `MAX_EDITION_DETAIL_LENGTH` characters saying more of its
    edition, such as who it is licensed to, or None. It is not one of the
    protocol's members, so a policy without it is still a `Policy`. A
    remote shows the edition and its detail, and never acts on either
    (ADR 0134).

    A remote calls it from several threads at once (ADR 0135), so it must be
    safe to call concurrently.
    """

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
    """Is told what a remote did, and what it refused.

    A remote tells it from several threads at once (ADR 0135), so it must be
    safe to call concurrently, and must keep every event it is told even
    when two arrive together.
    """

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        """Record one event."""

        ...


class OwnerOnlyPolicy:
    """The core's policy: the owner may do anything, and no one else may do anything.

    It keeps no state, so any number of threads may ask it at once.
    """

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
    """The core's audit, which records nothing, from any number of threads at once."""

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

    @property
    def edition_detail(
        self,
    ) -> str | None:
        """Return what the policy says of its edition beside its name, or None.

        It is read from the policy each time, so a policy may change what it
        says, as a licence nears its end. A policy without it says nothing
        more.

        Raises:
            RemotePluginError: The policy's detail is not one printable line
                of at most `MAX_EDITION_DETAIL_LENGTH` characters.
        """

        detail: object = getattr(self.policy, "edition_detail", None)

        if detail is None:
            return None

        if (
            not isinstance(detail, str)
            or not detail.strip()
            or not detail.isprintable()
            or len(detail) > MAX_EDITION_DETAIL_LENGTH
        ):
            shown = repr(detail)

            raise RemotePluginError(
                f"The remote's policy gave an edition detail of "
                f"{shown if len(shown) <= 80 else shown[:77] + '...'}; an edition detail is one "
                f"printable line of at most {MAX_EDITION_DETAIL_LENGTH} characters."
            )

        return detail

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
    "MAX_EDITION_DETAIL_LENGTH",
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
