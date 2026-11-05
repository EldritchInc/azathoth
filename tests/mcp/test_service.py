"""Tests for running tool calls: invoking exposed workflows and reading invocations (ADR 0111)."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.jobs import JobErrorCode, JobStatus
from azathoth.persistence.repositories import Repositories, open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InvocationIdempotency,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    create_production_invocation,
)
from azathoth_mcp.access import (
    READ_ALL_SCOPE,
    READ_SCOPE,
    STDIO_CALLER,
    McpCaller,
    ToolAccessError,
    Transport,
    invoke_scope,
)
from azathoth_mcp.catalog import ToolCatalog, ToolUnavailableError, UnknownToolError
from azathoth_mcp.evidence import InvocationStatus, RunEvidence, invocation_evidence
from azathoth_mcp.exposure import ExposedWorkflow, ExposureDocument
from azathoth_mcp.service import (
    GENERATED_KEY_PREFIX,
    INLINE_ONLY_POLICY,
    InvocationNotFoundError,
    ToolArgumentsError,
    ToolOutcome,
    ToolService,
    generated_key,
)

SUMMARIZE_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

BROKEN_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")

HIDDEN_ID = UUID("9a3b5c7d-1e2f-4a6b-8c0d-2e4f6a8b0c1d")

PRIMARY = FixedModelSelection(provider="test-provider", model="production-model")

MISSING = FixedModelSelection(provider="test-provider", model="missing-model")

TICKET_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}},
    "required": ["ticket"],
}

TICKET: dict[str, JsonValue] = {"ticket": "The printer is on fire."}

ALICE = McpCaller(
    transport=Transport.HTTP,
    subject="alice",
    client_id="claude-desktop",
    scopes=frozenset({invoke_scope("summarize"), invoke_scope("broken"), READ_SCOPE}),
)

BOB = McpCaller(
    transport=Transport.HTTP,
    subject="bob",
    scopes=frozenset({invoke_scope("summarize"), READ_SCOPE}),
)


def step(
    number: int,
    selection: FixedModelSelection,
) -> WorkflowStepSpecification:
    """Return one prompt step of a test workflow."""

    return WorkflowStepSpecification(
        id=UUID(int=100 + number),
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=UUID(int=200 + number),
                name=f"step-{number}",
                description="Exercise the tool service.",
                version="1.0.0",
            ),
            prompt=Prompt(text="Summarize the ticket."),
            model_selection=selection,
        ),
    )


def production_state(
    workflow_id: UUID,
    *,
    steps: int = 2,
    selection: FixedModelSelection = PRIMARY,
    version: str = "1.0.0",
) -> WorkflowProductionState:
    """Return the production state of a workflow of some prompt steps."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"workflow-{workflow_id}",
                description="Exercise the tool service.",
                version=version,
            ),
            steps=tuple(step(number, selection) for number in range(1, steps + 1)),
        ),
    )


def exposure(
    *workflows: tuple[UUID, str],
) -> ExposureDocument:
    """Return an exposure document; the summarizer takes a ticket."""

    return ExposureDocument(
        version=1,
        tools=tuple(
            ExposedWorkflow(
                workflow_id=workflow_id,
                name=name,
                description=f"Run {name}.",
                input_schema=TICKET_SCHEMA if name == "summarize" else None,
            )
            for workflow_id, name in workflows
        ),
    )


DEFAULT_EXPOSURE = ((SUMMARIZE_ID, "summarize"), (BROKEN_ID, "broken"))


class Harness:
    """One server's tool service over a real SQLite database, with fake models."""

    def __init__(
        self,
        database: Path,
        *,
        exposed: tuple[tuple[UUID, str], ...] = DEFAULT_EXPOSURE,
    ) -> None:
        self.repositories: Repositories = open_repositories(database)
        self.loads = 0
        self.keys = 0

        for workflow_id in (SUMMARIZE_ID, HIDDEN_ID):
            if self.repositories.production_states.get(workflow_id) is None:
                self.repositories.production_states.set(production_state(workflow_id))

        if self.repositories.production_states.get(BROKEN_ID) is None:
            self.repositories.production_states.set(
                production_state(BROKEN_ID, steps=1, selection=MISSING)
            )

        self.service = ToolService(
            catalog=ToolCatalog(exposure(*exposed), self.repositories.production_states),
            repositories=self.repositories,
            load_runtime=self.load,
            new_key=self.new_key,
        )

    def load(
        self,
    ) -> AzathothRuntime:
        """Compose a runtime from the database's production states, counting each time."""

        self.loads += 1

        return AzathothRuntime(
            workflows=WorkflowCatalog(),
            production_states=self.repositories.production_states.states(),
            models=ModelCatalog(
                models=(
                    ModelMetadata(
                        provider=PRIMARY.provider,
                        model=PRIMARY.model,
                        display_name=PRIMARY.identifier,
                    ),
                )
            ),
            portfolio=ModelPortfolio(),
            language_models=LanguageModelRegistry(
                {
                    PRIMARY.identifier: DeterministicLanguageModel(
                        provider=PRIMARY.provider,
                        model=PRIMARY.model,
                    ),
                }
            ),
        )

    def new_key(
        self,
    ) -> str:
        """Return a deterministic key for a call that named none."""

        self.keys += 1

        return f"generated-{self.keys}"

    def invoke(
        self,
        tool: str,
        arguments: dict[str, JsonValue],
        *,
        caller: McpCaller = STDIO_CALLER,
    ) -> ToolOutcome:
        """Call one exposed workflow's tool."""

        return asyncio.run(self.service.invoke(tool, arguments, caller=caller))


def harness(
    tmp_path: Path,
    *,
    exposed: tuple[tuple[UUID, str], ...] = DEFAULT_EXPOSURE,
) -> Harness:
    """Return a harness over a database in a test's directory."""

    return Harness(tmp_path / "azathoth.db", exposed=exposed)


# Invoking


def test_a_call_invokes_the_workflow_under_a_generated_key(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    outcome = server.invoke("summarize", {"input": TICKET})

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.replayed is False
    assert outcome.idempotency_key == "generated-1"
    assert outcome.error is None
    assert outcome.is_error is False
    assert outcome.invocation_id is not None

    invocation = server.repositories.invocations.get(outcome.invocation_id)

    assert invocation is not None
    assert invocation.workflow_id == SUMMARIZE_ID
    assert invocation.idempotency is not None
    assert invocation.idempotency.key == "generated-1"


def test_the_server_resolves_no_references() -> None:
    assert INLINE_ONLY_POLICY.accepted_schemes == ()


def test_generated_keys_are_distinct_and_marked() -> None:
    first, second = generated_key(), generated_key()

    assert first != second
    assert first.startswith(GENERATED_KEY_PREFIX)
    assert UUID(first.removeprefix(GENERATED_KEY_PREFIX))


def test_every_call_without_a_key_runs_again(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    first = server.invoke("summarize", {"input": TICKET})
    second = server.invoke("summarize", {"input": TICKET})

    assert first.invocation_id != second.invocation_id
    assert second.replayed is False


def test_a_call_repeated_with_its_key_replays_without_running(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    first = server.invoke("summarize", {"input": TICKET, "idempotency_key": "ticket-42"})
    second = server.invoke("summarize", {"input": TICKET, "idempotency_key": "ticket-42"})

    assert second.status is JobStatus.SUCCEEDED
    assert second.replayed is True
    assert second.invocation_id == first.invocation_id
    assert second.result == first.result
    assert second.idempotency_key == "ticket-42"
    assert server.keys == 0
    assert len(server.repositories.runs.runs()) == 1


def test_a_key_used_for_another_input_is_a_conflict(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    server.invoke("summarize", {"input": TICKET, "idempotency_key": "ticket-42"})
    conflict = server.invoke(
        "summarize", {"input": {"ticket": "Other."}, "idempotency_key": "ticket-42"}
    )

    assert conflict.status is JobStatus.REJECTED
    assert conflict.is_error is True
    assert conflict.invocation_id is None
    assert conflict.error is not None
    assert conflict.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT


def test_a_key_another_caller_used_is_a_conflict_not_a_replay(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    server.invoke("summarize", {"input": TICKET, "idempotency_key": "ticket-42"}, caller=ALICE)
    other = server.invoke(
        "summarize", {"input": TICKET, "idempotency_key": "ticket-42"}, caller=BOB
    )

    assert other.status is JobStatus.REJECTED
    assert other.error is not None
    assert other.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT


def test_the_caller_is_recorded_with_the_invocation(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    local = server.invoke("summarize", {"input": TICKET})
    remote = server.invoke("summarize", {"input": TICKET}, caller=ALICE)

    assert local.invocation_id is not None
    assert remote.invocation_id is not None

    local_invocation = server.repositories.invocations.get(local.invocation_id)
    remote_invocation = server.repositories.invocations.get(remote.invocation_id)

    assert local_invocation is not None
    assert remote_invocation is not None
    assert local_invocation.caller_metadata == {"mcp": {"transport": "stdio", "tool": "summarize"}}
    assert remote_invocation.caller_metadata == {
        "mcp": {
            "transport": "http",
            "tool": "summarize",
            "subject": "alice",
            "client_id": "claude-desktop",
        }
    }


def test_an_input_that_looks_like_a_reference_is_only_a_value(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path, exposed=((HIDDEN_ID, "anything"),))
    reference: dict[str, JsonValue] = {"uri": "file:///etc/passwd", "media_type": "text/plain"}

    outcome = server.invoke("anything", {"input": reference})

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.invocation_id is not None

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=STDIO_CALLER
    )

    assert evidence.input == reference


def test_a_failed_invocation_is_an_error_outcome_with_its_code(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    outcome = server.invoke("broken", {"input": "x"}, caller=ALICE)

    assert outcome.status is JobStatus.FAILED
    assert outcome.is_error is True
    assert outcome.invocation_id is not None
    assert outcome.error is not None
    assert outcome.error.code is JobErrorCode.MODEL_UNAVAILABLE


def test_an_outcome_is_the_job_result_without_kind_or_version(
    tmp_path: Path,
) -> None:
    outcome = harness(tmp_path).invoke("summarize", {"input": TICKET})

    assert outcome.structured_content() == {
        "status": "succeeded",
        "replayed": False,
        "idempotency_key": "generated-1",
        "invocation_id": str(outcome.invocation_id),
        "result": outcome.result,
        "error": None,
    }


# Refusing calls


def test_an_unknown_tool_is_refused(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    for name in ("summarise", "get_invocation"):
        with pytest.raises(UnknownToolError) as raised:
            server.invoke(name, {"input": TICKET})

        assert str(raised.value) == f'There is no tool named "{name}".'


def test_a_caller_without_the_tools_scope_is_refused_before_its_arguments_are_read(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    with pytest.raises(ToolAccessError) as raised:
        server.invoke("broken", {"wrong": True}, caller=BOB)

    assert str(raised.value) == 'This call needs the scope "azathoth:invoke:broken".'
    assert server.repositories.invocations.invocation_for_idempotency_key("generated-1") is None


def test_arguments_must_hold_an_input(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        harness(tmp_path).invoke("summarize", {})

    assert str(raised.value) == (
        "The arguments of \"summarize\" are not valid: $: 'input' is a required property."
    )


def test_arguments_must_hold_nothing_else(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        harness(tmp_path).invoke("summarize", {"input": TICKET, "workflow_id": "x"})

    assert str(raised.value) == (
        'The arguments of "summarize" are not valid: '
        "$: Additional properties are not allowed ('workflow_id' was unexpected)."
    )


def test_a_key_the_job_envelope_would_refuse_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        harness(tmp_path).invoke("summarize", {"input": TICKET, "idempotency_key": ""})

    assert str(raised.value) == (
        "The arguments of \"summarize\" are not valid: $.idempotency_key: '' should be non-empty."
    )


def test_an_input_is_checked_against_the_operators_schema(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        harness(tmp_path).invoke("summarize", {"input": {"ticket": 5, "extra": 1}})

    assert str(raised.value) == (
        "The arguments of \"summarize\" are not valid: $.input.ticket: 5 is not of type 'string'."
    )


def test_every_input_problem_is_reported(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        harness(tmp_path).invoke("summarize", {"input": []})

    assert str(raised.value) == (
        "The arguments of \"summarize\" are not valid: $.input: [] is not of type 'object'."
    )


def test_a_refused_argument_records_nothing(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    with pytest.raises(ToolArgumentsError):
        server.invoke("summarize", {"input": {}, "idempotency_key": "ticket-42"})

    assert server.repositories.invocations.invocation_for_idempotency_key("ticket-42") is None
    assert server.loads == 0


def test_a_workflow_no_longer_active_is_refused_and_records_nothing(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path, exposed=((SUMMARIZE_ID, "summarize"), (UUID(int=7), "gone")))

    with pytest.raises(ToolUnavailableError) as raised:
        server.invoke("gone", {"input": 1, "idempotency_key": "gone-1"})

    assert str(raised.value) == (
        'The tool "gone" is not available: its workflow is no longer active in production.'
    )
    assert server.repositories.invocations.invocation_for_idempotency_key("gone-1") is None


# Runtimes and progress


def test_the_runtime_is_composed_once_while_production_stays_the_same(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    server.invoke("summarize", {"input": TICKET})
    server.invoke("summarize", {"input": TICKET})

    assert server.loads == 1


def test_a_workflow_promoted_again_is_served_at_its_new_state(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    server.invoke("summarize", {"input": TICKET})
    server.repositories.production_states.set(production_state(SUMMARIZE_ID, version="2.0.0"))
    outcome = server.invoke("summarize", {"input": TICKET})

    assert server.loads == 2
    assert outcome.invocation_id is not None

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=STDIO_CALLER
    )

    assert evidence.run is not None
    assert evidence.run.run_id is not None

    run = server.repositories.runs.get(evidence.run.run_id)

    assert run is not None
    assert run.workflow.version == "2.0.0"


def test_the_client_is_told_as_each_step_finishes(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    reports: list[tuple[float, float | None, str | None]] = []

    async def report(
        progress: float,
        total: float | None,
        message: str | None,
    ) -> None:
        await asyncio.sleep(0.01)
        reports.append((progress, total, message))

    async def call() -> tuple[ToolOutcome, list[tuple[float, float | None, str | None]]]:
        outcome = await server.service.invoke(
            "summarize", {"input": TICKET}, caller=STDIO_CALLER, report_progress=report
        )

        return outcome, list(reports)

    outcome, sent_before_returning = asyncio.run(call())

    assert outcome.status is JobStatus.SUCCEEDED
    assert sent_before_returning == [
        (1.0, 2.0, "1 of 2 steps finished."),
        (2.0, 2.0, "2 of 2 steps finished."),
    ]


def test_progress_that_cannot_be_sent_never_changes_the_outcome(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    async def report(
        progress: float,
        total: float | None,
        message: str | None,
    ) -> None:
        raise ConnectionError("The client went away.")

    outcome = asyncio.run(
        server.service.invoke(
            "summarize", {"input": TICKET}, caller=STDIO_CALLER, report_progress=report
        )
    )

    assert outcome.status is JobStatus.SUCCEEDED


# Reading invocations


def read(
    server: Harness,
    invocation_id: UUID | str | None,
    *,
    caller: McpCaller = STDIO_CALLER,
) -> object:
    """Read one invocation through `get_invocation`."""

    return server.service.get_invocation({"invocation_id": str(invocation_id)}, caller=caller)


def test_an_invocation_is_read_with_its_evidence(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET, "idempotency_key": "ticket-42"})

    assert outcome.invocation_id is not None

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=STDIO_CALLER
    )
    invocation = server.repositories.invocations.get(outcome.invocation_id)

    assert invocation is not None
    assert evidence.invocation_id == outcome.invocation_id
    assert evidence.workflow_id == SUMMARIZE_ID
    assert evidence.tool == "summarize"
    assert evidence.created_at == invocation.created_at
    assert evidence.status is InvocationStatus.SUCCEEDED
    assert evidence.result == outcome.result
    assert evidence.error is None
    assert evidence.idempotency_key == "ticket-42"
    assert evidence.input == TICKET
    assert evidence.caller == {"mcp": {"transport": "stdio", "tool": "summarize"}}
    assert evidence.run is not None
    assert evidence.run.finished is True
    assert evidence.run.resumes == 0
    assert evidence.run.halted is False
    assert evidence.run.started_at is not None
    assert evidence.run.completed_at is not None
    assert [step.step_id for step in evidence.run.steps] == [UUID(int=101), UUID(int=102)]
    assert {step.status for step in evidence.run.steps} == {WorkflowStepStatus.EXECUTED}
    assert {step.attempts for step in evidence.run.steps} == {1}


def test_a_failed_invocation_is_read_with_its_error(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("broken", {"input": "x"})

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=STDIO_CALLER
    )

    assert evidence.status is InvocationStatus.FAILED
    assert evidence.result is None
    assert evidence.error is not None
    assert evidence.error.code is JobErrorCode.MODEL_UNAVAILABLE
    assert outcome.error is not None
    assert evidence.error.message == outcome.error.message


def test_an_invocation_without_a_result_is_incomplete(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    invocation = create_production_invocation(
        workflow_id=SUMMARIZE_ID,
        payload=TICKET,
        idempotency=InvocationIdempotency(key="pending-1", request_digest="0" * 64),
    )
    server.repositories.invocations.save(invocation)

    evidence = server.service.get_invocation(
        {"invocation_id": str(invocation.id)}, caller=STDIO_CALLER
    )

    assert evidence.status is InvocationStatus.INCOMPLETE
    assert evidence.result is None
    assert evidence.error is None
    assert evidence.run is None
    assert evidence.idempotency_key == "pending-1"


def test_a_caller_reads_its_own_invocations(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET}, caller=ALICE)

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=ALICE
    )

    assert evidence.invocation_id == outcome.invocation_id


@pytest.mark.parametrize(
    "reader",
    [
        BOB,
        McpCaller(transport=Transport.HTTP, scopes=frozenset({READ_SCOPE})),
    ],
    ids=["another-subject", "no-subject"],
)
def test_another_callers_invocation_is_not_found(
    tmp_path: Path,
    reader: McpCaller,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET}, caller=ALICE)

    with pytest.raises(InvocationNotFoundError) as raised:
        read(server, outcome.invocation_id, caller=reader)

    assert str(raised.value) == f"No invocation {outcome.invocation_id} was found."


def test_a_local_invocation_is_not_found_by_a_remote_caller(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET})

    with pytest.raises(InvocationNotFoundError):
        read(server, outcome.invocation_id, caller=ALICE)


def test_reading_every_invocation_reads_another_callers(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET}, caller=ALICE)
    auditor = McpCaller(
        transport=Transport.HTTP, subject="carol", scopes=frozenset({READ_ALL_SCOPE})
    )

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=auditor
    )

    assert evidence.caller == {
        "mcp": {
            "transport": "http",
            "tool": "summarize",
            "subject": "alice",
            "client_id": "claude-desktop",
        }
    }


def test_the_local_caller_reads_every_invocation(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET}, caller=ALICE)

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)}, caller=STDIO_CALLER
    )

    assert evidence.invocation_id == outcome.invocation_id


def test_an_invocation_of_a_workflow_not_exposed_is_not_found(
    tmp_path: Path,
) -> None:
    outcome = harness(tmp_path).invoke("summarize", {"input": TICKET})
    other_server = harness(tmp_path, exposed=((BROKEN_ID, "broken"),))

    with pytest.raises(InvocationNotFoundError) as raised:
        read(other_server, outcome.invocation_id)

    assert str(raised.value) == f"No invocation {outcome.invocation_id} was found."


def test_an_invocation_that_does_not_exist_is_not_found(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvocationNotFoundError) as raised:
        read(harness(tmp_path), HIDDEN_ID)

    assert str(raised.value) == f"No invocation {HIDDEN_ID} was found."


def test_reading_needs_the_read_scope(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    caller = McpCaller(
        transport=Transport.HTTP, subject="alice", scopes=frozenset({invoke_scope("summarize")})
    )

    with pytest.raises(ToolAccessError) as raised:
        read(server, HIDDEN_ID, caller=caller)

    assert str(raised.value) == 'This call needs the scope "azathoth:read".'


def test_an_invocation_id_must_be_a_uuid(
    tmp_path: Path,
) -> None:
    with pytest.raises(ToolArgumentsError) as raised:
        read(harness(tmp_path), "ticket-42")

    assert str(raised.value) == 'The invocation ID must be a UUID; got "ticket-42".'


def test_get_invocation_arguments_must_name_only_an_invocation(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    with pytest.raises(ToolArgumentsError) as raised:
        server.service.get_invocation({}, caller=STDIO_CALLER)

    assert str(raised.value) == (
        'The arguments of "get_invocation" are not valid: '
        "$: 'invocation_id' is a required property."
    )

    with pytest.raises(ToolArgumentsError) as raised:
        server.service.get_invocation(
            {"invocation_id": str(HIDDEN_ID), "tool": "summarize"}, caller=STDIO_CALLER
        )

    assert str(raised.value) == (
        'The arguments of "get_invocation" are not valid: '
        "$: Additional properties are not allowed ('tool' was unexpected)."
    )


def test_the_service_offers_its_catalog(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    assert [tool.name for tool in server.service.catalog.tools()] == [
        "summarize",
        "broken",
        "get_invocation",
    ]


def test_evidence_names_how_often_a_run_was_resumed_and_each_steps_attempts(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)
    outcome = server.invoke("summarize", {"input": TICKET})

    assert outcome.invocation_id is not None

    invocation = server.repositories.invocations.get(outcome.invocation_id)
    association = server.repositories.invocation_runs.get(outcome.invocation_id)

    assert invocation is not None
    assert association is not None

    run = server.repositories.runs.get(association.run_id)

    assert run is not None

    retried = run.model_copy(
        update={
            "steps": tuple(
                step.model_copy(update={"attempts": step.attempts * 2}) for step in run.steps
            )
        }
    )

    evidence = invocation_evidence(
        invocation,
        tool="summarize",
        result=server.repositories.invocations.result(outcome.invocation_id),
        run_id=run.id,
        run=retried,
        resumes=3,
    )

    assert evidence.run is not None
    assert evidence.run.resumes == 3
    assert [step.attempts for step in evidence.run.steps] == [2, 2]
    assert evidence.run.workflow_revision == run.workflow_revision


def test_evidence_names_a_run_that_has_not_finished(
    tmp_path: Path,
) -> None:
    invocation = create_production_invocation(workflow_id=SUMMARIZE_ID, payload=TICKET)

    evidence = invocation_evidence(
        invocation,
        tool="summarize",
        result=None,
        run_id=HIDDEN_ID,
        run=None,
        resumes=1,
    )

    assert evidence.status is InvocationStatus.INCOMPLETE
    assert evidence.idempotency_key is None
    assert evidence.run == RunEvidence(run_id=HIDDEN_ID, finished=False, resumes=1)


def test_preloading_composes_the_runtime_before_any_call(
    tmp_path: Path,
) -> None:
    server = harness(tmp_path)

    server.service.preload()

    assert server.loads == 1

    server.invoke("summarize", {"input": TICKET})

    assert server.loads == 1
