"""What a remote asks its policy for each call of the service API (ADRs 0127, 0133 and 0134).

Every call of an `Azathoth` instance is listed here once, as a
`ServiceCall`: the actions it always asks, the resource it acts on when it
names one, the kind of resource a listing returns, the actions it asks only
when a condition holds, what it tells the audit, and whether a remote
serves it at all. A remote's routes are built from this list, and a test
keeps it, each call's docstring and the service API's README in step.

A call that runs a workflow, a benchmark or an optimization is a job: a
remote runs it on its workers, as ADR 0107 runs a queued job, rather than
while the request that starts it waits (ADR 0127).

The list names what each call does; a policy decides who may. A call that
needs another action's data asks for both, such as a restricted case, which
asks `read_restricted` as well as `read_catalog`. The calls that name an
instance's own remotes are never served, since remotes never hold each
other's tokens (ADR 0127).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from azathoth.remote.seams import Action, AuditEventKind


@dataclass(frozen=True)
class Resource:
    """What a call acts on: its kind, and the parameter that names it by ID or identifier."""

    kind: str
    parameter: str


@dataclass(frozen=True)
class Condition:
    """An action a call asks only when something holds, saying when."""

    action: Action
    when: str


@dataclass(frozen=True)
class ServiceCall:
    """What a remote asks its policy, and tells its audit, for one call."""

    name: str
    actions: tuple[Action, ...] = ()
    resource: Resource | None = None
    lists: str | None = None
    also: tuple[Condition, ...] = ()
    audit: tuple[AuditEventKind, ...] = ()
    served: bool = True
    job: bool = False
    """Whether a remote runs the call as a job on its workers, not while the request waits."""


def _workflow(
    parameter: str = "workflow_id",
) -> Resource:
    return Resource(kind="workflow", parameter=parameter)


def _tool() -> Resource:
    return Resource(kind="tool", parameter="tool_id")


def _benchmark() -> Resource:
    return Resource(kind="benchmark", parameter="benchmark_id")


def _model() -> Resource:
    return Resource(kind="model", parameter="identifier")


def _run() -> Resource:
    return Resource(kind="run", parameter="run_id")


def _invocation() -> Resource:
    return Resource(kind="invocation", parameter="invocation_id")


def _experiment() -> Resource:
    return Resource(kind="experiment", parameter="experiment_id")


RESTRICTED_BENCHMARK: Final = Condition(
    action=Action.READ_RESTRICTED,
    when="for a restricted benchmark",
)

RESTRICTED_CASE: Final = Condition(
    action=Action.READ_RESTRICTED,
    when="for a restricted case",
)

RESTRICTED_RUN: Final = Condition(
    action=Action.READ_RESTRICTED,
    when="for a run of restricted input",
)

READ_CATALOG: Final = (Action.READ_CATALOG,)
READ_RUNS: Final = (Action.READ_RUNS,)
READ_PORTFOLIO: Final = (Action.READ_PORTFOLIO,)

SERVICE_CALLS: Final[tuple[ServiceCall, ...]] = (
    # The instance
    ServiceCall("describe", (Action.READ_CAPABILITIES,)),
    ServiceCall("remote", served=False),
    # Workflows
    ServiceCall("workflows.list", READ_CATALOG, lists="workflow"),
    ServiceCall("workflows.get", READ_CATALOG, _workflow()),
    ServiceCall("workflows.history", READ_CATALOG, _workflow()),
    ServiceCall("workflows.check", READ_CATALOG),
    ServiceCall("workflows.export", READ_CATALOG, _workflow()),
    ServiceCall("workflows.compare_revisions", READ_CATALOG, _workflow()),
    ServiceCall(
        "workflows.import_document",
        (Action.IMPORT_WORKFLOW,),
        audit=(AuditEventKind.WORKFLOW_IMPORTED,),
    ),
    # Tools
    ServiceCall("tools.list", READ_CATALOG, lists="tool"),
    ServiceCall("tools.versions", READ_CATALOG, _tool(), lists="tool"),
    ServiceCall("tools.get", READ_CATALOG, _tool()),
    ServiceCall("tools.history", READ_CATALOG, _tool()),
    ServiceCall("tools.export", READ_CATALOG, _tool()),
    ServiceCall("tools.compare_revisions", READ_CATALOG, _tool()),
    ServiceCall("tools.usage", (Action.READ_CATALOG, Action.READ_RUNS), _tool()),
    ServiceCall(
        "tools.import_document",
        (Action.IMPORT_TOOL,),
        also=(Condition(action=Action.IMPORT_PROCESS_TOOL, when="for a process tool"),),
        audit=(AuditEventKind.TOOL_IMPORTED, AuditEventKind.PROCESS_TOOL_IMPORTED),
    ),
    ServiceCall(
        "tools.from_mcp",
        (Action.TOOL_FROM_MCP,),
        audit=(AuditEventKind.TOOL_MADE_FROM_MCP,),
    ),
    # Benchmarks
    ServiceCall("benchmarks.list", READ_CATALOG, lists="benchmark"),
    ServiceCall(
        "benchmarks.get",
        READ_CATALOG,
        _benchmark(),
        also=(RESTRICTED_BENCHMARK,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall("benchmarks.history", READ_CATALOG, _benchmark()),
    ServiceCall(
        "benchmarks.export",
        READ_CATALOG,
        _benchmark(),
        also=(RESTRICTED_BENCHMARK,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall(
        "benchmarks.compare_revisions",
        READ_CATALOG,
        _benchmark(),
        also=(RESTRICTED_CASE,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall("benchmarks.cases", READ_CATALOG, _benchmark()),
    ServiceCall(
        "benchmarks.case",
        READ_CATALOG,
        _benchmark(),
        also=(RESTRICTED_CASE,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall(
        "benchmarks.import_document",
        (Action.IMPORT_BENCHMARK,),
        audit=(AuditEventKind.BENCHMARK_IMPORTED,),
    ),
    ServiceCall(
        "benchmarks.create",
        (Action.EDIT_BENCHMARK,),
        audit=(AuditEventKind.BENCHMARK_CREATED,),
    ),
    ServiceCall(
        "benchmarks.add_case",
        (Action.EDIT_BENCHMARK,),
        _benchmark(),
        also=(
            Condition(action=Action.READ_RUNS, when="when the case is made from a run"),
            Condition(
                action=Action.READ_RESTRICTED,
                when="when the case is made from a run of restricted input",
            ),
        ),
        audit=(AuditEventKind.BENCHMARK_CASE_ADDED, AuditEventKind.RESTRICTED_READ),
    ),
    ServiceCall(
        "benchmarks.update_case",
        (Action.EDIT_BENCHMARK,),
        _benchmark(),
        audit=(AuditEventKind.BENCHMARK_CASE_CHANGED,),
    ),
    ServiceCall(
        "benchmarks.remove_case",
        (Action.EDIT_BENCHMARK,),
        _benchmark(),
        audit=(AuditEventKind.BENCHMARK_CASE_REMOVED,),
    ),
    ServiceCall("benchmarks.executions", READ_RUNS, _benchmark(), lists="execution"),
    ServiceCall(
        "benchmarks.execution",
        READ_RUNS,
        Resource(kind="execution", parameter="execution_id"),
    ),
    ServiceCall(
        "benchmarks.run",
        (Action.RUN_BENCHMARK,),
        _benchmark(),
        audit=(AuditEventKind.BENCHMARK_RUN,),
        job=True,
    ),
    ServiceCall(
        "benchmarks.compare",
        (Action.RUN_BENCHMARK,),
        _benchmark(),
        audit=(AuditEventKind.BENCHMARK_RUN,),
        job=True,
    ),
    # Goals
    ServiceCall("goals.list", READ_CATALOG, lists="goal"),
    ServiceCall("goals.get", READ_CATALOG, Resource(kind="goal", parameter="goal_id")),
    ServiceCall(
        "goals.import_document",
        (Action.IMPORT_GOAL,),
        audit=(AuditEventKind.GOAL_IMPORTED,),
    ),
    # Models and the portfolio
    ServiceCall("models.list", READ_PORTFOLIO),
    ServiceCall("models.get", READ_PORTFOLIO, _model()),
    ServiceCall("models.matching", READ_PORTFOLIO),
    ServiceCall("models.usage", (Action.READ_CATALOG, Action.READ_RUNS), _model()),
    ServiceCall("portfolio.list", READ_PORTFOLIO),
    ServiceCall(
        "portfolio.add",
        (Action.AUTHORIZE_MODEL,),
        _model(),
        audit=(AuditEventKind.MODEL_AUTHORIZED,),
    ),
    ServiceCall(
        "portfolio.set_data_policy",
        (Action.DECLARE_POLICY,),
        _model(),
        audit=(AuditEventKind.DATA_POLICY_DECLARED,),
    ),
    ServiceCall(
        "portfolio.remove",
        (Action.AUTHORIZE_MODEL,),
        _model(),
        audit=(AuditEventKind.MODEL_REMOVED,),
    ),
    # Judges
    ServiceCall("judges.list", READ_PORTFOLIO),
    ServiceCall(
        "judges.add",
        (Action.MANAGE_JUDGES,),
        _model(),
        audit=(AuditEventKind.JUDGE_ADDED,),
    ),
    ServiceCall(
        "judges.remove",
        (Action.MANAGE_JUDGES,),
        _model(),
        audit=(AuditEventKind.JUDGE_REMOVED,),
    ),
    # Runs
    ServiceCall("runs.list", READ_RUNS, _workflow(), lists="run"),
    ServiceCall(
        "runs.get",
        READ_RUNS,
        _run(),
        also=(RESTRICTED_RUN,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall("runs.annotations", READ_RUNS, _run()),
    ServiceCall("runs.feedback", READ_RUNS, _run()),
    ServiceCall("runs.children", READ_RUNS, _run()),
    ServiceCall("runs.interrupted", READ_RUNS, _workflow(), lists="run"),
    ServiceCall("runs.readiness", READ_CATALOG),
    ServiceCall(
        "runs.run",
        (Action.RUN_WORKFLOW,),
        _workflow(),
        audit=(AuditEventKind.WORKFLOW_RUN,),
        job=True,
    ),
    ServiceCall(
        "runs.try_step",
        (Action.RUN_WORKFLOW,),
        audit=(AuditEventKind.STEP_TRIED,),
        job=True,
    ),
    ServiceCall(
        "runs.invoke",
        (Action.INVOKE,),
        _workflow(),
        audit=(AuditEventKind.WORKFLOW_INVOKED,),
        job=True,
    ),
    ServiceCall(
        "runs.record_feedback",
        (Action.ANNOTATE_RUN,),
        _run(),
        audit=(AuditEventKind.RUN_ANNOTATED,),
    ),
    ServiceCall(
        "runs.resume",
        (Action.ANNOTATE_RUN,),
        _run(),
        audit=(AuditEventKind.RUN_RESUMED,),
        job=True,
    ),
    # Invocations
    ServiceCall("invocations.list", READ_RUNS, _workflow(), lists="invocation"),
    ServiceCall(
        "invocations.get",
        READ_RUNS,
        _invocation(),
        also=(RESTRICTED_RUN,),
        audit=(AuditEventKind.RESTRICTED_READ,),
    ),
    ServiceCall("invocations.annotations", READ_RUNS, _invocation()),
    ServiceCall(
        "invocations.resume",
        (Action.ANNOTATE_RUN,),
        _invocation(),
        audit=(AuditEventKind.RUN_RESUMED,),
        job=True,
    ),
    # Production
    ServiceCall("production.get", READ_CATALOG, _workflow()),
    ServiceCall("production.revisions", READ_CATALOG, _workflow()),
    ServiceCall(
        "production.promote",
        (Action.PROMOTE,),
        _workflow(),
        also=(Condition(action=Action.READ_RUNS, when="when promoted from an experiment"),),
        audit=(AuditEventKind.WORKFLOW_PROMOTED,),
    ),
    ServiceCall(
        "production.roll_back",
        (Action.PROMOTE,),
        _workflow(),
        audit=(AuditEventKind.WORKFLOW_ROLLED_BACK,),
    ),
    # Experiments and optimization
    ServiceCall("experiments.list", READ_RUNS, _workflow(), lists="experiment"),
    ServiceCall("experiments.get", READ_RUNS, _experiment()),
    ServiceCall("experiments.compare", READ_RUNS, _experiment()),
    ServiceCall("experiments.promotable", READ_RUNS, _experiment()),
    ServiceCall(
        "optimization.optimize",
        (Action.OPTIMIZE,),
        _workflow(),
        audit=(AuditEventKind.WORKFLOW_OPTIMIZED,),
        job=True,
    ),
    # Spend
    ServiceCall("spend.report", (Action.READ_SPEND,)),
    # This instance's own names for remotes
    ServiceCall("remotes.list", served=False),
    ServiceCall("remotes.get", served=False),
    ServiceCall("remotes.add", served=False),
    ServiceCall("remotes.remove", served=False),
)
"""Every call of the service API, and what a remote asks and tells for it (ADR 0134)."""

_BY_NAME: Final[Mapping[str, ServiceCall]] = {call.name: call for call in SERVICE_CALLS}


def service_call(
    name: str,
) -> ServiceCall:
    """Return the call of a name, such as `workflows.get`.

    Raises:
        LookupError: The service API has no call of that name.
    """

    try:
        return _BY_NAME[name]
    except KeyError:
        raise LookupError(f"The service API has no call named {name!r}.") from None


__all__ = [
    "SERVICE_CALLS",
    "Condition",
    "Resource",
    "ServiceCall",
    "service_call",
]
