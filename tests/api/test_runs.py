"""Contract tests for running workflows and watching them run (ADR 0120)."""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.persistence.repositories import open_repositories

EXAMPLES = Path(__file__).parents[2] / "examples"

COUNT_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000001")

COUNT_STEP_ID = UUID("c0000000-0000-4000-8000-000000000011")

SLEEP_TOOL_ID = UUID("c0000000-0000-4000-8000-000000000002")

SLEEP_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000003")

SLEEP_STEP_ID = UUID("c0000000-0000-4000-8000-000000000031")

FAIL_TOOL_ID = UUID("c0000000-0000-4000-8000-000000000004")

FAIL_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000005")

FAIL_STEP_ID = UUID("c0000000-0000-4000-8000-000000000051")

FAIL_IMPLEMENTATION_ID = UUID("c0000000-0000-4000-8000-000000000005")

TOLERATED_STEP_ID = UUID("c0000000-0000-4000-8000-000000000052")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def tool_step(
    step_id: UUID,
    tool: str,
    *,
    runtime: str = "python",
    message: str | None = None,
) -> dict[str, JsonValue]:
    """Return one step calling a tool with the run's input as its `text`."""

    return {
        "id": str(step_id),
        "specification": {
            "requirement": {"name": tool, "version": "1.0.0", "runtime": runtime},
        },
        "inputs": [
            {
                "name": "text",
                "source": {"event_type": "workflow.input.received", "field_name": "input"},
            }
        ],
        "outputs": [{"name": "count", "path": ["count"]}],
        "message": message,
    }


def workflow(
    workflow_id: UUID,
    step: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Return a one-step workflow whose result is the step's `count`."""

    return {
        "metadata": {
            "id": str(workflow_id),
            "name": f"workflow {workflow_id}",
            "description": "One tool step.",
            "version": "1.0.0",
        },
        "steps": [step],
        "result": {"name": "count"},
    }


def tool_document(
    tool_id: UUID,
    name: str,
    implementation: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Return a tool document taking `text` and returning `count`, with one implementation."""

    return {
        "definition": {
            "id": str(tool_id),
            "name": name,
            "description": f"The {name} tool.",
            "version": "1.0.0",
            "input_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                }
            },
            "output_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                }
            },
        },
        "implementations": [
            {
                "id": str(UUID(int=tool_id.int + 1)),
                "tool_id": str(tool_id),
                "tool_version": "1.0.0",
                "version": "1.0.0",
                **implementation,
            }
        ],
    }


def stock(
    instance: api.Azathoth,
) -> None:
    """Import a word count workflow, a slow one and one whose tool always fails."""

    instance.tools.import_document((EXAMPLES / "tools" / "word-count.json").read_text())
    instance.tools.import_document(
        tool_document(
            SLEEP_TOOL_ID,
            "slow_count",
            {
                "runtime": "process",
                "command": [sys.executable],
                "source": "import time\n\ntime.sleep(30)\n",
                "timeout_seconds": 60.0,
            },
        )
    )
    instance.tools.import_document(
        tool_document(
            FAIL_TOOL_ID,
            "explode",
            {
                "runtime": "python",
                "entrypoint": "run",
                "source": "def run(text):\n    raise ValueError('boom')\n",
            },
        )
    )
    instance.workflows.import_document(
        workflow(COUNT_WORKFLOW_ID, tool_step(COUNT_STEP_ID, "word_count", message="Counting"))
    )
    instance.workflows.import_document(
        workflow(SLEEP_WORKFLOW_ID, tool_step(SLEEP_STEP_ID, "slow_count", runtime="process"))
    )
    instance.workflows.import_document(
        workflow(FAIL_WORKFLOW_ID, tool_step(FAIL_STEP_ID, "explode"))
    )


#
# Results
#


def test_a_run_returns_its_result_and_is_kept(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    result = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="one two three"))

    assert result.succeeded
    assert result.workflow_id == COUNT_WORKFLOW_ID
    assert result.workflow_revision == 1
    assert result.has_result
    assert result.result == 3
    assert result.error is None
    assert result.warnings == ()
    assert result.started_at <= result.completed_at
    assert result.command == f"azathoth run show {result.run_id}"
    assert open_repositories(location).runs.get(result.run_id) is not None


def test_a_run_given_no_input_starts_with_an_empty_context(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    result = instance.runs.run(COUNT_WORKFLOW_ID)

    assert not result.succeeded
    assert result.error is not None


def test_a_failed_run_names_the_step_and_its_failure(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    result = instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="anything"))

    assert not result.succeeded
    assert not result.has_result
    assert result.result is None
    assert result.error == api.RunError(
        code="workflow_execution_failed",
        step_id=FAIL_STEP_ID,
        exception_type="ToolExecutionError",
        message=f"Tool implementation {FAIL_IMPLEMENTATION_ID} failed during execution.",
    )
    assert open_repositories(location).runs.get(result.run_id) is not None


def test_a_run_halted_after_a_tolerated_failure_names_the_step_that_halted_it(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    tolerated = {**tool_step(TOLERATED_STEP_ID, "explode"), "failure_policy": "continue"}
    halting = tool_step(FAIL_STEP_ID, "explode")
    document = workflow(FAIL_WORKFLOW_ID, tolerated)
    document["steps"] = [tolerated, halting]
    instance.workflows.import_document(document)

    result = instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x"))

    assert result.error is not None
    assert result.error.step_id == FAIL_STEP_ID


def test_running_an_unknown_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.runs.run(MISSING_ID)

    assert str(raised.value) == f"Workflow {MISSING_ID} is not configured."


def test_a_run_whose_tool_is_missing_never_starts(
    instance: api.Azathoth,
) -> None:
    missing_tool = tool_step(COUNT_STEP_ID, "nope")
    instance.workflows.import_document(workflow(COUNT_WORKFLOW_ID, missing_tool))

    with pytest.raises(api.RunNotStartedError) as raised:
        instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="x"))

    assert raised.value.code == "run_not_started"


#
# Events
#


def test_events_arrive_in_the_order_the_run_makes_them(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    events: list[api.RunEvent] = []

    result = instance.runs.run(
        COUNT_WORKFLOW_ID,
        input=api.RunInput(payload="one two"),
        on_event=events.append,
    )

    assert tuple(event.type for event in events) == (
        "run_started",
        "step_started",
        "step_finished",
        "context_changed",
        "run_finished",
    )
    assert events[0] == api.RunStarted(workflow_id=COUNT_WORKFLOW_ID)
    assert events[1] == api.StepStarted(step_id=COUNT_STEP_ID, layer=0, message="Counting")
    assert events[2] == api.StepFinished(
        step_id=COUNT_STEP_ID,
        layer=0,
        status="executed",
        failure=None,
        confidence=None,
    )
    assert events[3] == api.ContextChanged(step_id=COUNT_STEP_ID, values={"count": 2})
    assert events[4] == api.RunFinished(run_id=result.run_id, succeeded=True)


def test_a_failed_step_reports_its_failure_and_changes_no_context(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    events: list[api.RunEvent] = []

    instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x"), on_event=events.append)

    finished = next(event for event in events if isinstance(event, api.StepFinished))

    assert finished.status == "failed"
    assert finished.failure == (
        f"Tool implementation {FAIL_IMPLEMENTATION_ID} failed during execution."
    )
    assert not any(isinstance(event, api.ContextChanged) for event in events)
    last = events[-1]

    assert isinstance(last, api.RunFinished)
    assert not last.succeeded


def test_events_are_their_own_json(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    events: list[api.RunEvent] = []

    instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="a"), on_event=events.append)

    for event in events:
        assert api.parse_run_event(event.model_dump_json()) == event


def test_a_callback_that_raises_is_detached_and_named_in_a_warning(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    seen: list[str] = []

    def fragile(event: api.RunEvent) -> None:
        seen.append(event.type)

        if event.type == "step_started":
            raise RuntimeError("display broke")

    result = instance.runs.run(
        COUNT_WORKFLOW_ID,
        input=api.RunInput(payload="a b"),
        on_event=fragile,
    )

    assert result.succeeded
    assert result.result == 2
    assert seen == ["run_started", "step_started"]
    assert result.warnings == (
        "The event callback raised RuntimeError: display broke, and was detached.",
    )


#
# Cancellation
#


def test_a_cancelled_run_stops_and_raises(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)
    token = api.CancellationToken()
    events: list[api.RunEvent] = []

    def cancel_when_started(event: api.RunEvent) -> None:
        events.append(event)

        if event.type == "step_started":
            token.cancel()

    with pytest.raises(api.RunCancelledError) as raised:
        instance.runs.run(
            SLEEP_WORKFLOW_ID,
            input=api.RunInput(payload="x"),
            on_event=cancel_when_started,
            cancel=token,
        )

    assert str(raised.value) == "The run was cancelled."
    assert raised.value.code == "run_cancelled"
    assert not any(isinstance(event, api.StepFinished | api.RunFinished) for event in events)
    assert open_repositories(location).runs.runs() == ()


def test_a_token_cancelled_beforehand_starts_nothing(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    token = api.CancellationToken()
    token.cancel()
    events: list[api.RunEvent] = []

    with pytest.raises(api.RunCancelledError):
        instance.runs.run(COUNT_WORKFLOW_ID, on_event=events.append, cancel=token)

    assert events == []
    assert token.cancelled


def test_a_closed_instance_runs_nothing(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.runs.run(COUNT_WORKFLOW_ID)
