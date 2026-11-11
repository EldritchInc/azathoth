"""Running tool calls: invoking exposed workflows and reading invocations (ADR 0111).

A call of an exposed workflow's tool is a job. The service builds an
`invoke` request in the job envelope, with the call's input as an inline
value and the caller under `mcp` in its caller metadata, and runs it as
`job run` does (ADR 0097, ADR 0105): a repeated key replays its result, an
interrupted invocation resumes, and one still running is reported as
incomplete. A call that names no key is given one, which the result returns.

Inputs are inline values only, so a call can never make the server read a
file or any other reference.

The server is a client of Azathoth's service API (ADR 0120): each call is
`runs.invoke` on a worker thread, and every read is `invocations.get`. A
call the client cancels cancels its invocation, which the same call under
the same key resumes.

Every refusal raises an error whose message is written for the model that
made the call: an unknown tool, a missing scope, arguments that are not
valid, a workflow that is no longer active, an invocation that cannot be
read, or a restricted invocation of a tool not exposed for restricted data.

A tool's calls carry the label its exposure gives it (ADR 0123). Restricted
data reaches a client only through a tool the operator exposed as
restricted.
"""

import asyncio
import contextlib
import functools
from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth import api
from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.inputs import InputPolicy
from azathoth.jobs import JobError, JobErrorCode, JobStatus
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


class RestrictedInvocationError(PermissionError):
    """Raised when `get_invocation` names a restricted invocation of a tool not exposed for it.

    The operator declares that a tool's client may hold restricted data by
    exposing it with `"sensitivity": "restricted"` (ADR 0123); until then the
    server returns no restricted invocation through it.
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
    """Run the calls of one server's tools on one Azathoth instance."""

    def __init__(
        self,
        *,
        catalog: ToolCatalog,
        instance: api.Azathoth,
        new_key: Callable[[], str] = generated_key,
    ) -> None:
        self._catalog = catalog
        self._instance = instance
        self._new_key = new_key

    @property
    def catalog(self) -> ToolCatalog:
        """Return the catalog of the tools this service runs."""

        return self._catalog

    def preload(
        self,
    ) -> None:
        """Ask every configured provider what it serves, before any call arrives.

        A server preloads when it starts, so a provider that cannot be used
        stops it before any client connects.

        Raises:
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        self._instance.models.list()

    async def invoke(
        self,
        tool: str,
        arguments: Mapping[str, JsonValue],
        *,
        caller: McpCaller,
        report_progress: ReportProgress | None = None,
    ) -> ToolOutcome:
        """Invoke one exposed workflow's tool, and return its outcome.

        The invocation runs on a worker thread, so the server keeps serving
        meanwhile. Cancelling the call cancels the invocation, and waits for
        it to stop.

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

        progress = (
            StepProgress(
                report_progress,
                total=len(state.specification.steps),
                loop=asyncio.get_running_loop(),
            )
            if report_progress is not None
            else None
        )
        token = api.CancellationToken()
        call = functools.partial(
            self._instance.runs.invoke,
            exposed.workflow_id,
            input=payload,
            sensitivity=exposed.sensitivity,
            idempotency_key=key,
            caller_metadata=caller.caller_metadata(tool),
            on_event=progress.observe if progress is not None else None,
            cancel=token,
        )
        invocation = asyncio.ensure_future(asyncio.to_thread(call))

        try:
            outcome = await asyncio.shield(invocation)
        except asyncio.CancelledError:
            token.cancel()

            with contextlib.suppress(api.RunCancelledError):
                await invocation

            raise

        if progress is not None:
            await progress.flush()

        return _outcome(outcome)

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
            RestrictedInvocationError: The invocation is restricted, and its
                tool is not exposed for restricted data.
        """

        if not caller.reads_every_invocation:
            caller.require(READ_SCOPE)

        invocation_id = _invocation_id(arguments)
        missing = InvocationNotFoundError(f"No invocation {invocation_id} was found.")

        try:
            detail = self._instance.invocations.get(invocation_id)
        except api.NotFoundError as exc:
            raise missing from exc

        if not self._catalog.is_exposed(detail.workflow_id) or not caller.may_read(
            detail.caller_metadata
        ):
            raise missing

        tool = self._tool_name(detail.workflow_id)

        if detail.sensitivity is api.Sensitivity.RESTRICTED and (
            self._catalog.exposed(tool).sensitivity is not api.Sensitivity.RESTRICTED
        ):
            raise RestrictedInvocationError(
                f"Invocation {invocation_id} is restricted, and the tool {tool!r} is not exposed "
                "for restricted data, so its result is not returned. If this client may hold "
                'restricted data, the operator exposes the tool with "sensitivity": "restricted".'
            )

        return invocation_evidence(detail, tool=tool)

    def _arguments(
        self,
        exposed: ExposedWorkflow,
        arguments: Mapping[str, JsonValue],
    ) -> tuple[JsonValue, str]:
        """Return a call's input and key, or refuse arguments that do not match the tool.

        The envelope is checked first, then the input against the operator's
        schema, or else the promoted workflow's (ADR 0118), in that schema's
        own dialect.
        """

        input_schema = self._catalog.input_schema_of(exposed)
        envelope = workflow_tool_schema(exposed.model_copy(update={"input_schema": None}))
        problems = [
            f"{violation.path}: {violation.message}"
            for violation in json_schema_violations(
                json_schema_validator(envelope),
                dict(arguments),
            )
        ]

        if not problems and input_schema is not None:
            problems.extend(
                f"$.{INPUT_ARGUMENT}{violation.path.removeprefix('$')}: {violation.message}"
                for violation in json_schema_violations(
                    json_schema_validator(input_schema),
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
    outcome: api.InvocationOutcome,
) -> ToolOutcome:
    """Return a call's outcome from its invocation's, naming its key."""

    return ToolOutcome(
        status=JobStatus(outcome.status),
        replayed=outcome.replayed,
        idempotency_key=outcome.idempotency_key,
        invocation_id=outcome.invocation_id,
        result=outcome.result,
        error=(
            JobError(
                code=JobErrorCode(outcome.error.code),
                message=outcome.error.message,
                metadata=outcome.error.metadata,
            )
            if outcome.error is not None
            else None
        ),
    )


__all__ = [
    "GENERATED_KEY_PREFIX",
    "INLINE_ONLY_POLICY",
    "InvocationNotFoundError",
    "RestrictedInvocationError",
    "ToolArgumentsError",
    "ToolOutcome",
    "ToolService",
    "generated_key",
]
