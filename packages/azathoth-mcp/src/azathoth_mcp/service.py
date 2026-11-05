"""Running tool calls: invoking exposed workflows and reading invocations (ADR 0111).

A call of an exposed workflow's tool is a job. The service builds an
`invoke` request in the job envelope, with the call's input as an inline
value and the caller under `mcp` in its caller metadata, and runs it as
`job run` does (ADR 0097, ADR 0105): a repeated key replays its result, an
interrupted invocation resumes, and one still running is reported as
incomplete. A call that names no key is given one, which the result returns.

Inputs are inline values only, so a call can never make the server read a
file or any other reference.

Every refusal raises an error whose message is written for the model that
made the call: an unknown tool, a missing scope, arguments that are not
valid, a workflow that is no longer active, or an invocation that cannot be
read.
"""

from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.inputs import InlineInput, InputPolicy
from azathoth.jobs import (
    InvokeJobRequest,
    JobError,
    JobResult,
    JobStatus,
    run_invoke_job,
    runtime_job_invoker,
    runtime_job_resumer,
)
from azathoth.persistence.repositories import Repositories
from azathoth.runtime import AzathothRuntime
from azathoth.telemetry import NO_TELEMETRY, Telemetry
from azathoth.telemetry.invocations import traced_job_invoker
from azathoth.telemetry.runs import tracing_runner
from azathoth.workflows import journal_resumes
from azathoth_mcp.access import READ_SCOPE, McpCaller, invoke_scope
from azathoth_mcp.catalog import (
    GET_INVOCATION_SCHEMA,
    IDEMPOTENCY_KEY_ARGUMENT,
    INPUT_ARGUMENT,
    INVOCATION_ID_ARGUMENT,
    ToolCatalog,
    workflow_tool_schema,
)
from azathoth_mcp.evidence import InvocationEvidence, invocation_evidence
from azathoth_mcp.exposure import ExposedWorkflow
from azathoth_mcp.progress import ReportProgress, StepProgress
from azathoth_mcp.runtimes import RuntimeProvider

INLINE_ONLY_POLICY = InputPolicy()
"""The server resolves no references: every input is the value the call sent."""

GENERATED_KEY_PREFIX = "mcp-"


def generated_key() -> str:
    """Return a new idempotency key for a call that named none."""

    return f"{GENERATED_KEY_PREFIX}{uuid4()}"


class ToolArgumentsError(ValueError):
    """Raised when a call's arguments do not match its tool's input schema."""


class InvocationNotFoundError(LookupError):
    """Raised when `get_invocation` names an invocation the caller may not read.

    An invocation that does not exist, one of a workflow that is not exposed,
    and one another caller made are refused alike, so a caller learns nothing
    about invocations it may not read.
    """


class ToolOutcome(BaseModel):
    """What one call of an exposed workflow's tool returns.

    It is the job envelope's result (ADR 0097), without its kind and version,
    and always names the idempotency key the call ran under.
    """

    model_config = ConfigDict(frozen=True)

    status: JobStatus
    replayed: bool
    idempotency_key: str
    invocation_id: UUID | None
    result: JsonValue = None
    error: JobError | None = None

    @property
    def is_error(
        self,
    ) -> bool:
        """Report whether the call did not end with a result the model can use."""

        return self.status is not JobStatus.SUCCEEDED

    def structured_content(
        self,
    ) -> dict[str, JsonValue]:
        """Return the outcome as the JSON a client receives."""

        return self.model_dump(mode="json")


class ToolService:
    """Run the calls of one server's tools.

    `load_runtime` composes a runtime from the configured database; it is
    called again only when production has moved on (see `RuntimeProvider`).
    """

    def __init__(
        self,
        *,
        catalog: ToolCatalog,
        repositories: Repositories,
        load_runtime: Callable[[], AzathothRuntime],
        telemetry: Telemetry = NO_TELEMETRY,
        new_key: Callable[[], str] = generated_key,
    ) -> None:
        self._catalog = catalog
        self._repositories = repositories
        self._runtimes = RuntimeProvider(load_runtime)
        self._telemetry = telemetry
        self._new_key = new_key

    @property
    def catalog(self) -> ToolCatalog:
        """Return the catalog of the tools this service runs."""

        return self._catalog

    async def invoke(
        self,
        tool: str,
        arguments: Mapping[str, JsonValue],
        *,
        caller: McpCaller,
        report_progress: ReportProgress | None = None,
    ) -> ToolOutcome:
        """Invoke one exposed workflow's tool, and return its outcome.

        Raises:
            UnknownToolError: No exposed workflow is offered under the name.
            ToolAccessError: The caller's token lacks the tool's scope.
            ToolArgumentsError: The arguments do not match the tool's schema.
            ToolUnavailableError: The workflow is no longer active.
        """

        exposed = self._catalog.exposed(tool)

        caller.require(invoke_scope(tool))

        payload, key = self._arguments(exposed, arguments)

        _, state = self._catalog.active_state(tool)

        stores = self._repositories
        progress = (
            StepProgress(report_progress, total=len(state.specification.steps))
            if report_progress is not None
            else None
        )
        runner = tracing_runner(
            self._telemetry,
            observer=progress,
            journal=stores.run_journal,
            leases=stores.run_leases,
            children=stores.run_children,
        )

        def runtime() -> AzathothRuntime:
            return self._runtimes.runtime_for(exposed.workflow_id, state)

        job = await run_invoke_job(
            InvokeJobRequest(
                kind="invoke",
                version=1,
                idempotency_key=key,
                workflow_id=exposed.workflow_id,
                input=InlineInput(value=payload),
                caller_metadata=caller.caller_metadata(tool),
            ),
            policy=INLINE_ONLY_POLICY,
            store=stores.content,
            invocation_repository=stores.invocations,
            invoke=traced_job_invoker(
                self._telemetry,
                runtime_job_invoker(
                    runtime,
                    invocation_repository=stores.invocations,
                    run_repository=stores.runs,
                    invocation_run_repository=stores.invocation_runs,
                    runner=runner,
                ),
            ),
            resume=runtime_job_resumer(
                runtime,
                invocation_repository=stores.invocations,
                run_repository=stores.runs,
                invocation_run_repository=stores.invocation_runs,
                revision_repository=stores.production_revisions,
                journal=stores.run_journal,
                runner=runner,
            ),
        )

        if progress is not None:
            await progress.flush()

        return _outcome(job, key)

    def get_invocation(
        self,
        arguments: Mapping[str, JsonValue],
        *,
        caller: McpCaller,
    ) -> InvocationEvidence:
        """Return one invocation's result and evidence.

        Raises:
            ToolAccessError: The caller's token lacks `azathoth:read`.
            ToolArgumentsError: The arguments do not name an invocation ID.
            InvocationNotFoundError: The caller may not read the invocation.
        """

        if not caller.reads_every_invocation:
            caller.require(READ_SCOPE)

        invocation_id = _invocation_id(arguments)
        stores = self._repositories
        invocation = stores.invocations.get(invocation_id)

        if (
            invocation is None
            or not self._catalog.is_exposed(invocation.workflow_id)
            or not caller.may_read(invocation.caller_metadata)
        ):
            raise InvocationNotFoundError(f"No invocation {invocation_id} was found.")

        association = stores.invocation_runs.get(invocation_id)
        run_id = (
            association.run_id
            if association is not None
            else stores.run_journal.invocation_run_id(invocation_id)
        )

        return invocation_evidence(
            invocation,
            tool=self._tool_name(invocation.workflow_id),
            result=stores.invocations.result(invocation_id),
            run_id=run_id,
            run=stores.runs.get(association.run_id) if association is not None else None,
            resumes=0 if run_id is None else journal_resumes(stores.run_journal.entries(run_id)),
        )

    def _arguments(
        self,
        exposed: ExposedWorkflow,
        arguments: Mapping[str, JsonValue],
    ) -> tuple[JsonValue, str]:
        """Return a call's input and key, or refuse arguments that do not match the tool.

        The envelope is checked first, then the input against the operator's
        schema in that schema's own dialect.
        """

        envelope = workflow_tool_schema(exposed.model_copy(update={"input_schema": None}))
        problems = [
            f"{violation.path}: {violation.message}"
            for violation in json_schema_violations(
                json_schema_validator(envelope),
                dict(arguments),
            )
        ]

        if not problems and exposed.input_schema is not None:
            problems.extend(
                f"$.{INPUT_ARGUMENT}{violation.path.removeprefix('$')}: {violation.message}"
                for violation in json_schema_violations(
                    json_schema_validator(exposed.input_schema),
                    arguments[INPUT_ARGUMENT],
                )
            )

        if problems:
            raise ToolArgumentsError(
                f'The arguments of "{exposed.name}" are not valid: ' + "; ".join(problems) + "."
            )

        key = arguments.get(IDEMPOTENCY_KEY_ARGUMENT)

        return arguments[INPUT_ARGUMENT], key if isinstance(key, str) else self._new_key()

    def _tool_name(
        self,
        workflow_id: UUID,
    ) -> str:
        """Return the tool name one exposed workflow is offered under."""

        return next(
            tool.name for tool in self._catalog.exposure.tools if tool.workflow_id == workflow_id
        )


def _invocation_id(
    arguments: Mapping[str, JsonValue],
) -> UUID:
    """Return the invocation ID `get_invocation`'s arguments name.

    Raises:
        ToolArgumentsError: The arguments do not match the tool's schema, or
            the ID is not a UUID.
    """

    problems = [
        f"{violation.path}: {violation.message}"
        for violation in json_schema_violations(
            json_schema_validator(GET_INVOCATION_SCHEMA),
            dict(arguments),
        )
    ]

    if problems:
        raise ToolArgumentsError(
            'The arguments of "get_invocation" are not valid: ' + "; ".join(problems) + "."
        )

    text = arguments[INVOCATION_ID_ARGUMENT]

    assert isinstance(text, str)

    try:
        return UUID(text)
    except ValueError as exc:
        raise ToolArgumentsError(f'The invocation ID must be a UUID; got "{text}".') from exc


def _outcome(
    job: JobResult,
    key: str,
) -> ToolOutcome:
    """Return a call's outcome from its job result, naming its key."""

    return ToolOutcome(
        status=job.status,
        replayed=job.replayed,
        idempotency_key=job.idempotency_key if job.idempotency_key is not None else key,
        invocation_id=job.invocation_id,
        result=job.result,
        error=job.error,
    )


__all__ = [
    "GENERATED_KEY_PREFIX",
    "INLINE_ONLY_POLICY",
    "InvocationNotFoundError",
    "ToolArgumentsError",
    "ToolOutcome",
    "ToolService",
    "generated_key",
]
