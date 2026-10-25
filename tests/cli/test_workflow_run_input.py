"""Tests for supplying external input to configured workflow runs."""

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as cli_application
from azathoth.cli import (
    CONFIGURED_RUN_PRODUCER,
    WorkflowRunInput,
    configured_run_context,
    main,
    run_workflow,
)
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.context import ContextEvent
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    SQLiteWorkflowRunRepository,
    WorkflowRun,
)
from tests.cli.test_workflow_run import (
    WORKFLOW_ID,
    configure_runtime,
    create_runtime,
)

INPUT: JsonValue = {
    "text": "the old ones wait",
}


def only_run(
    database: Path,
) -> WorkflowRun:
    """Return the single run persisted for the CLI run workflow."""

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert len(runs) == 1

    return runs[0]


def only_input_event(
    run: WorkflowRun,
) -> ContextEvent:
    """Return the single event a run started with, requiring it to be workflow input."""

    assert len(run.initial_context.events) == 1

    event = run.initial_context.events[0]

    assert event.event_type == WORKFLOW_INPUT_EVENT_TYPE

    return event


def test_configured_run_producer_names_configured_execution() -> None:
    assert CONFIGURED_RUN_PRODUCER == "azathoth.configured"


def test_configured_run_context_without_input_is_empty() -> None:
    assert configured_run_context(None).events == ()


def test_configured_run_context_carries_one_workflow_input_event() -> None:
    context = configured_run_context(
        WorkflowRunInput(
            payload=INPUT,
        )
    )

    assert len(context.events) == 1

    event = context.events[0]

    assert event.event_type == WORKFLOW_INPUT_EVENT_TYPE
    assert event.payload == {"input": INPUT}
    assert event.producer == CONFIGURED_RUN_PRODUCER


def test_configured_run_context_keeps_supplied_null_as_input() -> None:
    context = configured_run_context(
        WorkflowRunInput(
            payload=None,
        )
    )

    assert len(context.events) == 1
    assert context.events[0].payload == {"input": None}


def test_workflow_run_records_supplied_input_as_the_workflow_input_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        workflow_input=WorkflowRunInput(
            payload=INPUT,
        ),
        output=WorkflowOutputFormat.RESULT,
    )

    capsys.readouterr()

    assert result == 0

    event = only_input_event(only_run(database))

    assert event.payload == {"input": INPUT}
    assert event.producer == CONFIGURED_RUN_PRODUCER


def test_workflow_run_records_supplied_null_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        workflow_input=WorkflowRunInput(
            payload=None,
        ),
        output=WorkflowOutputFormat.RESULT,
    )

    capsys.readouterr()

    assert result == 0

    assert only_input_event(only_run(database)).payload == {"input": None}


def test_workflow_run_without_input_starts_with_an_empty_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.RESULT,
    )

    capsys.readouterr()

    assert result == 0

    assert only_run(database).initial_context.events == ()


def test_cli_workflow_run_records_input_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = main(
        (
            "workflow",
            "run",
            str(WORKFLOW_ID),
            "--input",
            '"the old ones wait"',
            "--output",
            "result",
        )
    )

    capsys.readouterr()

    assert result == 0

    event = only_input_event(only_run(database))

    assert event.payload == {"input": "the old ones wait"}
    assert event.producer == CONFIGURED_RUN_PRODUCER


def capture_run_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> list[WorkflowRunInput | None]:
    """Replace the run handler with one that records the input it receives."""

    received: list[WorkflowRunInput | None] = []

    def fake_run_workflow(
        workflow_id: UUID,
        *,
        workflow_input: WorkflowRunInput | None,
        output: WorkflowOutputFormat,
    ) -> int:
        received.append(workflow_input)

        return 0

    monkeypatch.setattr(
        cli_application,
        "run_workflow",
        fake_run_workflow,
    )

    return received


def test_cli_workflow_run_dispatches_supplied_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = capture_run_inputs(monkeypatch)

    result = main(
        (
            "workflow",
            "run",
            str(WORKFLOW_ID),
            "--input",
            '{"text": "the old ones wait"}',
        )
    )

    assert result == 0

    assert received == [
        WorkflowRunInput(
            payload=INPUT,
        ),
    ]


def test_cli_workflow_run_dispatches_supplied_null_as_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = capture_run_inputs(monkeypatch)

    result = main(
        (
            "workflow",
            "run",
            str(WORKFLOW_ID),
            "--input",
            "null",
        )
    )

    assert result == 0

    assert received == [
        WorkflowRunInput(
            payload=None,
        ),
    ]


def test_cli_workflow_run_dispatches_no_input_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = capture_run_inputs(monkeypatch)

    result = main(
        (
            "workflow",
            "run",
            str(WORKFLOW_ID),
        )
    )

    assert result == 0

    assert received == [None]


def test_cli_workflow_run_rejects_invalid_input_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    received = capture_run_inputs(monkeypatch)

    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "run",
                str(WORKFLOW_ID),
                "--input",
                "{not json",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "must be valid JSON" in captured.err

    assert received == []


def test_cli_workflow_run_help_describes_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "run",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "--input JSON" in captured.out
