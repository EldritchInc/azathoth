"""Tests for resource usage discovery commands."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    model_usage,
    tool_usage,
)
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import (
    StrategyMetadata,
    StrategyResourceBinding,
)
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunRepository,
    ToolStepSpecification,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
)

PROMPT_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

RETIRED_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

UNKNOWN_TOOL_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

IMPLEMENTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

MODEL_IDENTIFIER = "openrouter/example-model"
UNUSED_MODEL_IDENTIFIER = "openrouter/unused-model"
TOOL_NAME = "word_count"

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an isolated durable database."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    return database


def create_metadata(
    workflow_id: UUID,
    name: str,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name=name,
        description=f"{name} description.",
        version="1.0.0",
    )


def create_prompt_workflow() -> WorkflowSpecification:
    """Create a workflow configured to one exact model."""

    return WorkflowSpecification(
        metadata=create_metadata(
            PROMPT_WORKFLOW_ID,
            "summarize",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Summarize prompt",
                        description="Summarize prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="openrouter",
                        model="example-model",
                    ),
                ),
            ),
        ),
    )


def create_tool_workflow() -> WorkflowSpecification:
    """Create a workflow requiring one tool capability."""

    return WorkflowSpecification(
        metadata=create_metadata(
            TOOL_WORKFLOW_ID,
            "count words",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name=TOOL_NAME,
                    ),
                ),
            ),
        ),
    )


def create_definition() -> ToolDefinition:
    """Create one durable tool definition version."""

    return ToolDefinition(
        id=TOOL_ID,
        name=TOOL_NAME,
        description="Count words.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={"type": "object"},
        ),
        output_schema=ToolOutputSchema(
            json_schema={"type": "object"},
        ),
    )


def create_run(
    *,
    workflow: WorkflowMetadata,
    resource: StrategyResourceBinding,
) -> WorkflowRun:
    """Create one workflow run whose single step bound one resource."""

    context = Context()
    completed_at = STARTED_AT + timedelta(seconds=1)

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Usage command step",
        strategy_version="1.0.0",
        output="OK",
        resources=(resource,),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )

    return WorkflowRun(
        id=RUN_ID,
        workflow=workflow,
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=STARTED_AT,
                        completed_at=completed_at,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )


def test_model_usage_reports_configured_production_and_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    workflow = create_prompt_workflow()

    SQLiteWorkflowRepository(database).save(workflow)

    SQLiteWorkflowProductionStateRepository(database).set(
        WorkflowProductionState(
            specification=workflow,
        )
    )

    SQLiteWorkflowRunRepository(database).save(
        create_run(
            workflow=workflow.metadata,
            resource=StrategyResourceBinding(
                kind="model",
                identifier=MODEL_IDENTIFIER,
            ),
        )
    )

    result = model_usage(MODEL_IDENTIFIER)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert lines[:3] == [
        f"Model: {MODEL_IDENTIFIER}",
        "Workflows: 1",
        "In Production: yes",
    ]
    assert f"ID: {PROMPT_WORKFLOW_ID}" in lines
    assert "Configured: yes" in lines
    assert f"Production: primary step {STEP_ID}" in lines
    assert "Runs: 1" in lines


def test_model_usage_reports_unused_model_without_failing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_prompt_workflow())

    result = model_usage(UNUSED_MODEL_IDENTIFIER)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (f"Model: {UNUSED_MODEL_IDENTIFIER}\nWorkflows: 0\nIn Production: no\n")
    assert captured.err == ""


def test_tool_usage_reports_configured_production_and_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    workflow = create_tool_workflow()

    SQLiteToolRepository(database).save_definition(create_definition())

    SQLiteWorkflowRepository(database).save(workflow)

    SQLiteWorkflowProductionStateRepository(database).set(
        WorkflowProductionState(
            specification=workflow,
        )
    )

    SQLiteWorkflowRunRepository(database).save(
        create_run(
            workflow=workflow.metadata,
            resource=StrategyResourceBinding(
                kind="tool",
                identifier=str(IMPLEMENTATION_ID),
                attributes={
                    "tool_id": str(TOOL_ID),
                    "tool_version": "1.0.0",
                    "runtime": "python",
                },
            ),
        )
    )

    result = tool_usage(TOOL_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert lines[:4] == [
        f"Tool ID: {TOOL_ID}",
        f"Names: {TOOL_NAME}",
        "Workflows: 1",
        "In Production: yes",
    ]
    assert f"ID: {TOOL_WORKFLOW_ID}" in lines
    assert "Configured: yes" in lines
    assert "Production: yes" in lines
    assert "Runs: 1" in lines


def test_tool_usage_reports_defined_but_unused_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteToolRepository(database).save_definition(create_definition())

    result = tool_usage(TOOL_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"Tool ID: {TOOL_ID}\nNames: {TOOL_NAME}\nWorkflows: 0\nIn Production: no\n"
    )
    assert captured.err == ""


def test_tool_usage_reports_history_of_undefined_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRunRepository(database).save(
        create_run(
            workflow=create_metadata(
                RETIRED_WORKFLOW_ID,
                "retired counter",
            ),
            resource=StrategyResourceBinding(
                kind="tool",
                identifier=str(IMPLEMENTATION_ID),
                attributes={
                    "tool_id": str(TOOL_ID),
                    "tool_version": "1.0.0",
                    "runtime": "python",
                },
            ),
        )
    )

    result = tool_usage(TOOL_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert "Names: unknown" in lines
    assert f"ID: {RETIRED_WORKFLOW_ID}" in lines
    assert "Configured: no" in lines
    assert "Runs: 1" in lines


def test_tool_usage_rejects_unknown_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteToolRepository(database).save_definition(create_definition())

    result = tool_usage(UNKNOWN_TOOL_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Tool {UNKNOWN_TOOL_ID} is not configured.\n"
