"""Tests for the output formats of workflow run and workflow invoke."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as cli_application
import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    invoke_workflow,
    main,
    run_workflow,
)
from azathoth.cli.output_format import (
    DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    WorkflowOutputFormat,
)
from azathoth.providers import LanguageModelRegistry
from azathoth.runtime import AzathothRuntime
from azathoth.workflows import (
    SQLiteProductionInvocationRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCatalog,
    WorkflowNamedValueReference,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.cli.test_production_invocation_lifecycle import (
    UNDEPLOYED_WORKFLOW_ID,
    configure_cli_runtime,
    create_state,
)
from tests.cli.test_production_invocation_lifecycle import (
    WORKFLOW_ID as PRODUCTION_WORKFLOW_ID,
)
from tests.cli.test_recorded_workflow_run_failures import (
    FailingLanguageModel,
)
from tests.cli.test_workflow_run import (
    MODEL_IDENTIFIER,
    STEP_ID,
    UNKNOWN_WORKFLOW_ID,
    WORKFLOW_ID,
    configure_database,
    create_runtime,
    create_workflow,
)
from tests.workflows.test_step_message_generation import (
    MESSAGE,
    announce_workflow,
)

NOT_DEPLOYED_MESSAGE = "The requested workflow is not deployed to production."

ANSWERING = "Answering the request"


def create_announced_workflow() -> WorkflowSpecification:
    """Return the CLI run workflow announced, emitting, and declaring `answer`."""

    return announce_workflow(create_workflow()).model_copy(
        update={
            "result": WorkflowNamedValueReference(
                name="answer",
            ),
        }
    )


def configure_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    specification: WorkflowSpecification,
    failing: bool = False,
) -> Path:
    """Point `workflow run` at an isolated database and one deterministic runtime."""

    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    base = create_runtime()

    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(specification,)),
        models=base.models,
        portfolio=base.portfolio,
        language_models=(
            LanguageModelRegistry(
                models={
                    MODEL_IDENTIFIER: FailingLanguageModel(),
                }
            )
            if failing
            else base.language_models
        ),
    )

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    return database


def configure_invoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Activate the announced production lifecycle state in an isolated database."""

    database = tmp_path / "azathoth.db"

    state = create_state()

    step = WorkflowStepSpecification.model_validate(
        {
            **state.specification.steps[0].model_dump(),
            "message": ANSWERING,
            "emit_values": True,
        }
    )

    SQLiteWorkflowProductionStateRepository(
        database,
    ).set(
        WorkflowProductionState.model_validate(
            {
                **state.model_dump(),
                "specification": {
                    **state.specification.model_dump(),
                    "steps": [step.model_dump()],
                },
            }
        )
    )

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    return database


def records(
    output: str,
) -> list[dict[str, JsonValue]]:
    """Parse JSON Lines output into its records."""

    return [json.loads(line) for line in output.splitlines()]


def only_run(
    database: Path,
) -> WorkflowRun:
    """Return the single run persisted for the CLI run workflow."""

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert len(runs) == 1

    return runs[0]


def only_invocation_id(
    database: Path,
) -> UUID:
    """Return the identifier of the single persisted production invocation."""

    invocations = SQLiteProductionInvocationRepository(database).invocations()

    assert len(invocations) == 1

    return invocations[0].id


def test_default_output_format_is_json_lines() -> None:
    assert DEFAULT_WORKFLOW_OUTPUT_FORMAT is WorkflowOutputFormat.JSONL
    assert tuple(WorkflowOutputFormat) == (
        WorkflowOutputFormat.JSONL,
        WorkflowOutputFormat.TEXT,
        WorkflowOutputFormat.RESULT,
    )


def test_workflow_run_streams_json_lines_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    run = only_run(database)

    assert result == 0
    assert captured.err == ""
    assert records(captured.out) == [
        {
            "type": "step",
            "step_id": str(STEP_ID),
            "message": MESSAGE,
        },
        {
            "type": "output",
            "step_id": str(STEP_ID),
            "values": {
                "answer": "success",
            },
        },
        {
            "type": "result",
            "run_id": str(run.id),
            "value": "success",
        },
    ]


def test_workflow_run_json_lines_ends_with_the_halting_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
        failing=True,
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    run = only_run(database)

    emitted = records(captured.out)

    assert result == 1
    assert captured.err == ""
    assert run.failed
    assert emitted[0] == {
        "type": "step",
        "step_id": str(STEP_ID),
        "message": MESSAGE,
    }
    assert len(emitted) == 2
    assert emitted[1]["type"] == "error"
    assert emitted[1]["run_id"] == str(run.id)
    assert emitted[1]["code"] == "workflow_execution_failed"
    assert emitted[1]["step_id"] == str(STEP_ID)
    assert "Model exploded." in str(emitted[1]["message"])


def test_workflow_run_without_declared_result_omits_the_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        monkeypatch,
        tmp_path,
        specification=create_workflow(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert records(captured.out) == [
        {
            "type": "result",
            "run_id": str(only_run(database).id),
        },
    ]


def test_workflow_run_result_mode_prints_only_the_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.RESULT,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == '"success"\n'
    assert captured.err == ""


def test_workflow_run_result_mode_reports_failure_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
        failing=True,
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.RESULT,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "Model exploded." in captured.err


def test_workflow_run_result_mode_without_declared_result_prints_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        monkeypatch,
        tmp_path,
        specification=create_workflow(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.RESULT,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_workflow_run_text_mode_prints_messages_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.TEXT,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == f"{MESSAGE}\n"
    assert "Status: succeeded\n" in captured.out


def test_workflow_run_reports_unknown_workflow_as_text_in_every_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        monkeypatch,
        tmp_path,
        specification=create_announced_workflow(),
    )

    for output in WorkflowOutputFormat:
        result = run_workflow(
            UNKNOWN_WORKFLOW_ID,
            output=output,
        )

        captured = capsys.readouterr()

        assert result == 1
        assert captured.out == ""
        assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_workflow_invoke_streams_json_lines_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_invoke(
        monkeypatch,
        tmp_path,
    )

    result = main(
        (
            "workflow",
            "invoke",
            str(PRODUCTION_WORKFLOW_ID),
            "--input",
            '{"request":"execute production"}',
        )
    )

    captured = capsys.readouterr()

    emitted = records(captured.out)

    assert result == 0
    assert captured.err == ""
    assert [record["type"] for record in emitted] == [
        "step",
        "output",
        "result",
    ]
    assert emitted[0]["message"] == ANSWERING
    assert emitted[1]["values"] == {
        "answer": "production-success",
    }
    assert emitted[2] == {
        "type": "result",
        "invocation_id": str(only_invocation_id(database)),
        "value": {
            "public_answer": "production-success",
        },
    }


def test_workflow_invoke_json_lines_reports_production_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_invoke(
        monkeypatch,
        tmp_path,
    )

    result = invoke_workflow(
        workflow_id=UNDEPLOYED_WORKFLOW_ID,
        payload={},
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == ""
    assert records(captured.out) == [
        {
            "type": "error",
            "invocation_id": str(only_invocation_id(database)),
            "code": "workflow_not_deployed",
            "message": NOT_DEPLOYED_MESSAGE,
        },
    ]


def test_workflow_invoke_result_mode_prints_only_the_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_invoke(
        monkeypatch,
        tmp_path,
    )

    result = invoke_workflow(
        workflow_id=PRODUCTION_WORKFLOW_ID,
        payload={},
        output=WorkflowOutputFormat.RESULT,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == '{"public_answer": "production-success"}\n'
    assert captured.err == ""


def test_workflow_invoke_result_mode_reports_failure_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_invoke(
        monkeypatch,
        tmp_path,
    )

    result = invoke_workflow(
        workflow_id=UNDEPLOYED_WORKFLOW_ID,
        payload={},
        output=WorkflowOutputFormat.RESULT,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"{NOT_DEPLOYED_MESSAGE}\n"


def test_workflow_invoke_text_mode_prints_messages_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_invoke(
        monkeypatch,
        tmp_path,
    )

    result = invoke_workflow(
        workflow_id=PRODUCTION_WORKFLOW_ID,
        payload={},
        output=WorkflowOutputFormat.TEXT,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == f"{ANSWERING}\n"
    assert "Status: succeeded\n" in captured.out


def test_cli_passes_requested_output_format_to_run_and_invoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[tuple[str, WorkflowOutputFormat]] = []

    def fake_run_workflow(
        workflow_id: UUID,
        *,
        output: WorkflowOutputFormat,
    ) -> int:
        requested.append(("run", output))

        return 0

    def fake_invoke_workflow(
        *,
        workflow_id: UUID,
        payload: JsonValue,
        output: WorkflowOutputFormat,
    ) -> int:
        requested.append(("invoke", output))

        return 0

    monkeypatch.setattr(
        cli_application,
        "run_workflow",
        fake_run_workflow,
    )
    monkeypatch.setattr(
        cli_application,
        "invoke_workflow",
        fake_invoke_workflow,
    )

    assert (
        main(
            (
                "workflow",
                "run",
                str(WORKFLOW_ID),
                "--output",
                "result",
            )
        )
        == 0
    )

    assert (
        main(
            (
                "workflow",
                "invoke",
                str(WORKFLOW_ID),
                "--input",
                "{}",
                "--output",
                "text",
            )
        )
        == 0
    )

    assert requested == [
        ("run", WorkflowOutputFormat.RESULT),
        ("invoke", WorkflowOutputFormat.TEXT),
    ]


def test_cli_rejects_unknown_output_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "run",
                str(WORKFLOW_ID),
                "--output",
                "yaml",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert "invalid choice" in captured.err
