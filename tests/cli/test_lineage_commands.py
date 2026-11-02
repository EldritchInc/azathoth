"""Tests that child runs record their lineage and are bounded by the engine (ADR 0104)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import configured_run_context, main
from azathoth.cli.execution import CONFIGURED_RUN_PRODUCER, WorkflowRunInput
from azathoth.cli.lineage import parent_lineage
from azathoth.cli.rendering.lineage import render_lineage_lines
from azathoth.context import (
    LINEAGE_EVENT_TYPE,
    Context,
    LineageError,
    LineageRun,
    LineageStep,
    StepLineage,
    WorkflowDepthError,
    WorkflowLineage,
    child_lineage,
    create_lineage_event,
    encode_step_lineage,
    lineage_of,
)
from azathoth.inputs import SQLiteContentStore, content_bytes_digest
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRunRepository,
    create_production_invocation,
)
from tests.examples.test_run_workflow_examples import (
    PARENT_WORKFLOW_ID,
    child_call,
    configure_child_walkthrough,
)
from tests.examples.test_word_count_benchmark_examples import run_cli
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_ID as CHILD_WORKFLOW_ID,
)

PARENT_STEP_ID = UUID("a1000000-0000-4000-8000-000000000031")

ROOT = LineageRun(
    workflow_id=UUID("b2000000-0000-4000-8000-000000000001"),
    run_id=UUID("b2000000-0000-4000-8000-000000000002"),
)


def calling_step(
    depth: int,
) -> StepLineage:
    """Return the lineage of a step, in a run at the given depth, that starts a child."""

    return StepLineage(
        step=LineageStep(
            workflow_id=UUID("b3000000-0000-4000-8000-000000000001"),
            run_id=UUID("b3000000-0000-4000-8000-000000000002"),
            step_id=UUID("b3000000-0000-4000-8000-000000000003"),
            attempt=2,
        ),
        depth=depth,
        root=ROOT,
    )


def expected_lineage(
    depth: int,
) -> WorkflowLineage:
    """Return the lineage a child of `calling_step(depth)` records."""

    return WorkflowLineage(depth=depth + 1, parent=calling_step(depth).step, root=ROOT)


def database(
    tmp_path: Path,
) -> Path:
    """Return the walkthrough's database."""

    return tmp_path / "azathoth.db"


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command, returning its status, stdout and stderr."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the child-workflow walkthrough and promote its child; return the database."""

    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    return database(tmp_path)


# Reading AZATHOTH_LINEAGE


def test_a_process_without_lineage_starts_a_root() -> None:
    assert parent_lineage(CHILD_WORKFLOW_ID, {}) is None


def test_empty_lineage_starts_a_root() -> None:
    assert parent_lineage(CHILD_WORKFLOW_ID, {LINEAGE_ENVIRONMENT_VARIABLE: ""}) is None


def test_a_process_with_lineage_starts_a_child_one_level_down() -> None:
    environ = {LINEAGE_ENVIRONMENT_VARIABLE: encode_step_lineage(calling_step(2))}

    assert parent_lineage(CHILD_WORKFLOW_ID, environ) == expected_lineage(2)


def test_lineage_that_is_not_a_steps_lineage_is_rejected() -> None:
    with pytest.raises(LineageError) as error:
        parent_lineage(CHILD_WORKFLOW_ID, {LINEAGE_ENVIRONMENT_VARIABLE: "{}"})

    assert str(error.value) == "AZATHOTH_LINEAGE is not valid lineage: step: Field required."


def test_a_child_beyond_the_depth_limit_is_refused() -> None:
    environ = {LINEAGE_ENVIRONMENT_VARIABLE: encode_step_lineage(calling_step(8))}

    with pytest.raises(WorkflowDepthError) as error:
        parent_lineage(CHILD_WORKFLOW_ID, environ)

    assert str(error.value) == (
        f"Workflow {CHILD_WORKFLOW_ID} would run at depth 9, "
        "beyond the limit of 8 nested workflows."
    )


# Initial contexts


def test_a_configured_run_records_its_lineage_after_its_input() -> None:
    context = configured_run_context(WorkflowRunInput(payload="a b"), lineage=expected_lineage(0))

    assert [event.event_type for event in context.events] == [
        "workflow.input.received",
        LINEAGE_EVENT_TYPE,
    ]
    assert context.events[0].producer == CONFIGURED_RUN_PRODUCER
    assert lineage_of(context) == expected_lineage(0)


def test_a_configured_run_without_input_records_only_its_lineage() -> None:
    context = configured_run_context(None, lineage=expected_lineage(0))

    assert [event.event_type for event in context.events] == [LINEAGE_EVENT_TYPE]


def test_a_root_configured_run_records_the_context_it_always_did() -> None:
    assert configured_run_context(None) == Context()
    assert [
        event.event_type for event in configured_run_context(WorkflowRunInput(payload=1)).events
    ] == ["workflow.input.received"]


def test_an_invocation_records_its_lineage_last_at_its_creation_time() -> None:
    invocation = create_production_invocation(
        workflow_id=CHILD_WORKFLOW_ID,
        payload={"text": "a b"},
        lineage=expected_lineage(1),
    )

    events = invocation.initial_context.events

    assert [event.event_type for event in events] == [
        "production.invocation.received",
        "workflow.input.received",
        LINEAGE_EVENT_TYPE,
    ]
    assert events[-1].occurred_at == invocation.created_at
    assert lineage_of(invocation.initial_context) == expected_lineage(1)


def test_a_root_invocation_records_no_lineage() -> None:
    invocation = create_production_invocation(workflow_id=CHILD_WORKFLOW_ID, payload=1)

    assert lineage_of(invocation.initial_context) is None


# Commands


def test_workflow_run_records_the_lineage_it_was_started_with(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(2)))

    status, _, _ = cli(
        capsys, "workflow", "run", str(CHILD_WORKFLOW_ID), "--input", '"a b"', "--output", "result"
    )

    assert status == 0

    (run,) = SQLiteWorkflowRunRepository(walkthrough).runs_for_workflow(CHILD_WORKFLOW_ID)

    assert lineage_of(run.initial_context) == expected_lineage(2)


def test_workflow_invoke_records_the_lineage_it_was_started_with(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(0)))

    status, _, _ = cli(
        capsys,
        "workflow",
        "invoke",
        str(CHILD_WORKFLOW_ID),
        "--input",
        '"a b"',
        "--output",
        "result",
    )

    assert status == 0

    (invocation,) = SQLiteProductionInvocationRepository(walkthrough).invocations_for_workflow(
        CHILD_WORKFLOW_ID
    )

    assert lineage_of(invocation.initial_context) == expected_lineage(0)

    association = SQLiteProductionInvocationRunRepository(walkthrough).get(invocation.id)

    assert association is not None

    run = SQLiteWorkflowRunRepository(walkthrough).get(association.run_id)

    assert run is not None
    assert lineage_of(run.initial_context) == expected_lineage(0)


def test_job_run_records_the_lineage_it_was_started_with(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "lineage-1",
                "workflow_id": str(CHILD_WORKFLOW_ID),
                "input": {"value": "a b"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(4)))

    status, out, _ = cli(capsys, "job", "run", str(request))

    assert status == 0
    assert json.loads(out)["status"] == "succeeded"

    (invocation,) = SQLiteProductionInvocationRepository(walkthrough).invocations_for_workflow(
        CHILD_WORKFLOW_ID
    )

    assert lineage_of(invocation.initial_context) == expected_lineage(4)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param(
            encode_step_lineage(calling_step(8)),
            f"Workflow {CHILD_WORKFLOW_ID} would run at depth 9, "
            "beyond the limit of 8 nested workflows.\n",
            id="too-deep",
        ),
        pytest.param(
            '{"step": {}}',
            "AZATHOTH_LINEAGE is not valid lineage: step.workflow_id: Field required.\n",
            id="invalid",
        ),
    ],
)
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(("workflow", "run"), id="run"),
        pytest.param(("workflow", "invoke"), id="invoke"),
    ],
)
def test_a_refused_child_records_nothing_and_says_why(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, str],
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, value)

    assert cli(
        capsys, *command, str(CHILD_WORKFLOW_ID), "--input", '"a b"', "--output", "jsonl"
    ) == (1, "", message)

    assert SQLiteProductionInvocationRepository(walkthrough).invocations() == ()
    assert SQLiteWorkflowRunRepository(walkthrough).runs() == ()


def test_a_refused_job_prints_no_envelope_and_records_nothing(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "lineage-too-deep",
                "workflow_id": str(CHILD_WORKFLOW_ID),
                "input": {"value": "a b"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(8)))

    assert cli(capsys, "job", "run", str(request)) == (
        1,
        "",
        f"Workflow {CHILD_WORKFLOW_ID} would run at depth 9, "
        "beyond the limit of 8 nested workflows.\n",
    )
    assert SQLiteProductionInvocationRepository(walkthrough).invocations() == ()


def test_a_refused_child_does_not_store_its_input_file(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    words = tmp_path / "words.txt"
    words.write_text("a b", encoding="utf-8")

    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(8)))

    status, _, _ = cli(
        capsys, "workflow", "invoke", str(CHILD_WORKFLOW_ID), "--input-file", str(words)
    )

    assert status == 1

    assert SQLiteContentStore(walkthrough).get(content_bytes_digest(b"a b")) is None


# A real parent and child


def test_a_child_invoked_by_a_tool_records_the_step_and_run_that_started_it(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, _ = cli(
        capsys,
        "workflow",
        "run",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "result",
    )

    assert status == 0

    (parent,) = SQLiteWorkflowRunRepository(walkthrough).runs_for_workflow(PARENT_WORKFLOW_ID)
    (child,) = SQLiteProductionInvocationRepository(walkthrough).invocations_for_workflow(
        CHILD_WORKFLOW_ID
    )

    assert lineage_of(parent.initial_context) is None
    assert lineage_of(child.initial_context) == WorkflowLineage(
        depth=1,
        parent=LineageStep(
            workflow_id=PARENT_WORKFLOW_ID,
            run_id=parent.id,
            step_id=PARENT_STEP_ID,
            attempt=1,
        ),
        root=LineageRun(workflow_id=PARENT_WORKFLOW_ID, run_id=parent.id),
    )


def test_a_grandchild_keeps_the_root_and_goes_one_level_deeper(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(PARENT_WORKFLOW_ID))

    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(3)))

    status, _, _ = cli(
        capsys,
        "workflow",
        "invoke",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "result",
    )

    assert status == 0

    invocations = SQLiteProductionInvocationRepository(walkthrough)

    (parent,) = invocations.invocations_for_workflow(PARENT_WORKFLOW_ID)
    (child,) = invocations.invocations_for_workflow(CHILD_WORKFLOW_ID)

    parent_association = SQLiteProductionInvocationRunRepository(walkthrough).get(parent.id)

    assert parent_association is not None
    assert lineage_of(parent.initial_context) == expected_lineage(3)

    child_lineage_recorded = lineage_of(child.initial_context)

    assert child_lineage_recorded is not None
    assert child_lineage_recorded.depth == 5
    assert child_lineage_recorded.root == ROOT
    assert child_lineage_recorded.parent.run_id == parent_association.run_id


def test_a_tool_at_the_depth_limit_cannot_start_a_child(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(PARENT_WORKFLOW_ID))

    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(7)))

    status, out, _ = cli(
        capsys,
        "workflow",
        "invoke",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "jsonl",
    )

    assert status == 1
    assert json.loads(out.splitlines()[-1])["code"] == "workflow_execution_failed"
    assert (
        SQLiteProductionInvocationRepository(walkthrough).invocations_for_workflow(
            CHILD_WORKFLOW_ID
        )
        == ()
    )

    (parent,) = SQLiteWorkflowRunRepository(walkthrough).runs_for_workflow(PARENT_WORKFLOW_ID)
    (step,) = parent.steps
    failure = step.attempts[-1].failure

    assert failure is not None
    assert failure.message.endswith(
        f"Workflow {CHILD_WORKFLOW_ID} would run at depth 9, "
        "beyond the limit of 8 nested workflows."
    )


# Rendering


def test_invocation_show_names_the_lineage(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(1)))

    cli(capsys, "workflow", "invoke", str(CHILD_WORKFLOW_ID), "--input", '"a b"')

    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE)

    (invocation,) = SQLiteProductionInvocationRepository(walkthrough).invocations()
    step = calling_step(1).step

    status, out, _ = cli(capsys, "invocation", "show", str(invocation.id))

    assert status == 0
    assert (
        f"Depth: 2\n"
        f"Parent Workflow ID: {step.workflow_id}\n"
        f"Parent Run ID: {step.run_id}\n"
        f"Parent Step ID: {step.step_id} (attempt 2)\n"
        f"Root Workflow ID: {ROOT.workflow_id}\n"
        f"Root Run ID: {ROOT.run_id}\n"
        "Input:\n"
    ) in out


def test_run_show_names_the_lineage_after_the_run_id(
    walkthrough: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, encode_step_lineage(calling_step(0)))

    cli(capsys, "workflow", "run", str(CHILD_WORKFLOW_ID), "--input", '"a b"')

    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE)

    (run,) = SQLiteWorkflowRunRepository(walkthrough).runs()

    status, out, _ = cli(capsys, "run", "show", str(run.id))

    assert status == 0
    assert f"Run ID: {run.id}\nDepth: 1\nParent Workflow ID: " in out


def test_a_root_run_and_invocation_show_no_lineage(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli(capsys, "workflow", "invoke", str(CHILD_WORKFLOW_ID), "--input", '"a b"')

    (invocation,) = SQLiteProductionInvocationRepository(walkthrough).invocations()
    (run,) = SQLiteWorkflowRunRepository(walkthrough).runs()

    for arguments in (("invocation", "show", str(invocation.id)), ("run", "show", str(run.id))):
        status, out, _ = cli(capsys, *arguments)

        assert status == 0
        assert "Depth:" not in out
        assert "Parent Run ID:" not in out


def test_a_child_lineage_helper_matches_what_commands_record() -> None:
    assert child_lineage(calling_step(5), workflow_id=CHILD_WORKFLOW_ID) == expected_lineage(5)


# Documentation

CLI_README = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"


def test_the_cli_readme_quotes_the_real_refusals() -> None:
    with pytest.raises(WorkflowDepthError) as too_deep:
        parent_lineage(
            CHILD_WORKFLOW_ID,
            {LINEAGE_ENVIRONMENT_VARIABLE: encode_step_lineage(calling_step(8))},
        )

    with pytest.raises(LineageError) as invalid:
        parent_lineage(CHILD_WORKFLOW_ID, {LINEAGE_ENVIRONMENT_VARIABLE: "{}"})

    documented = (
        "```text\n"
        f"{str(too_deep.value).replace(str(CHILD_WORKFLOW_ID), '<WORKFLOW_ID>')}\n"
        f"{invalid.value}\n"
        "```"
    )

    assert documented in CLI_README.read_text(encoding="utf-8")


def test_the_cli_readme_shows_the_real_lineage_lines() -> None:
    lineage = WorkflowLineage(
        depth=1,
        parent=LineageStep(
            workflow_id=UUID(int=1),
            run_id=UUID(int=2),
            step_id=UUID(int=3),
            attempt=1,
        ),
        root=LineageRun(workflow_id=UUID(int=1), run_id=UUID(int=2)),
    )

    lines = render_lineage_lines(Context(events=(create_lineage_event(lineage),)))

    placeholders = {
        str(UUID(int=1)): "<WORKFLOW_ID>",
        str(UUID(int=2)): "<RUN_ID>",
        str(UUID(int=3)): "<STEP_ID>",
    }

    documented = "\n".join(lines)

    for value, placeholder in placeholders.items():
        documented = documented.replace(value, placeholder)

    assert f"Run ID: <RUN_ID>\n{documented}\n```" in CLI_README.read_text(encoding="utf-8")
