"""Tests for aggregated workflow tool usage reports."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.strategies import StrategyResourceBinding
from azathoth.tools import (
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowToolUsageEntry,
    WorkflowToolUsageReport,
    tool_usage_report,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

THIRD_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

THIRD_RUN_ID = UUID("99999999-9999-4999-8999-999999999993")

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

OTHER_TOOL_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

IMPLEMENTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

TOOL_NAME = "word_count"
RENAMED_TOOL_NAME = "word_counter"
OTHER_TOOL_NAME = "sentiment"

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)


def create_metadata(
    workflow_id: UUID,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name=f"Workflow {workflow_id}",
        description="Workflow used to test tool usage reports.",
        version="1.0.0",
    )


def create_definition(
    *,
    tool_id: UUID = TOOL_ID,
    name: str = TOOL_NAME,
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create one durable tool definition version."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"{name} description.",
        version=version,
        input_schema=ToolInputSchema(
            json_schema={"type": "object"},
        ),
        output_schema=ToolOutputSchema(
            json_schema={"type": "object"},
        ),
    )


def create_tool_workflow(
    workflow_id: UUID,
    *,
    tool_name: str = TOOL_NAME,
    tool_version: str | None = None,
) -> WorkflowSpecification:
    """Create a one-step workflow requiring one tool capability."""

    return WorkflowSpecification(
        metadata=create_metadata(workflow_id),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name=tool_name,
                        version=tool_version,
                    ),
                ),
            ),
        ),
    )


def create_production_state(
    workflow_id: UUID,
    *,
    tool_name: str = TOOL_NAME,
) -> WorkflowProductionState:
    """Create active production state requiring one tool capability."""

    return WorkflowProductionState(
        specification=create_tool_workflow(
            workflow_id,
            tool_name=tool_name,
        ),
    )


def create_run(
    workflow_id: UUID,
    *,
    run_id: UUID,
    executed_tool_id: UUID = TOOL_ID,
    started_at: datetime = STARTED_AT,
) -> WorkflowRun:
    """Create one workflow run whose single step executed one tool implementation."""

    context = Context()
    completed_at = started_at + timedelta(seconds=1)

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Tool step",
        strategy_version="1.0.0",
        output="OK",
        resources=(
            StrategyResourceBinding(
                kind="tool",
                identifier=str(IMPLEMENTATION_ID),
                attributes={
                    "tool_id": str(executed_tool_id),
                    "tool_version": "1.0.0",
                    "runtime": "python",
                },
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )

    return WorkflowRun(
        id=run_id,
        workflow=create_metadata(workflow_id),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )


def test_report_is_empty_when_nothing_uses_tool() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(
            create_definition(),
            create_definition(
                tool_id=OTHER_TOOL_ID,
                name=OTHER_TOOL_NAME,
            ),
        ),
        specifications=(
            create_tool_workflow(
                FIRST_WORKFLOW_ID,
                tool_name=OTHER_TOOL_NAME,
            ),
        ),
        production_states=(
            create_production_state(
                SECOND_WORKFLOW_ID,
                tool_name=OTHER_TOOL_NAME,
            ),
        ),
        runs=(
            create_run(
                THIRD_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
                executed_tool_id=OTHER_TOOL_ID,
            ),
        ),
    )

    assert report.tool_id == TOOL_ID
    assert report.tool_names == (TOOL_NAME,)
    assert report.workflows == ()
    assert not report.used
    assert not report.in_production
    assert report.production_workflows == ()


def test_report_records_configured_workflow_by_resolved_name() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(create_definition(),),
        specifications=(create_tool_workflow(FIRST_WORKFLOW_ID),),
        production_states=(),
        runs=(),
    )

    assert report.used
    assert not report.in_production
    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert entry.workflow.id == FIRST_WORKFLOW_ID
    assert entry.configured
    assert not entry.in_production
    assert entry.runs == ()


def test_report_ignores_requirement_version_constraints() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(create_definition(),),
        specifications=(
            create_tool_workflow(
                FIRST_WORKFLOW_ID,
                tool_version="9.9.9",
            ),
        ),
        production_states=(),
        runs=(),
    )

    assert tuple(entry.workflow.id for entry in report.workflows) == (FIRST_WORKFLOW_ID,)


def test_report_resolves_names_across_definition_versions() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(
            create_definition(
                name=TOOL_NAME,
                version="1.0.0",
            ),
            create_definition(
                name=RENAMED_TOOL_NAME,
                version="2.0.0",
            ),
            create_definition(
                name=TOOL_NAME,
                version="2.1.0",
            ),
        ),
        specifications=(
            create_tool_workflow(
                FIRST_WORKFLOW_ID,
                tool_name=TOOL_NAME,
            ),
            create_tool_workflow(
                SECOND_WORKFLOW_ID,
                tool_name=RENAMED_TOOL_NAME,
            ),
        ),
        production_states=(),
        runs=(),
    )

    assert report.tool_names == (
        TOOL_NAME,
        RENAMED_TOOL_NAME,
    )
    assert tuple(entry.workflow.id for entry in report.workflows) == (
        FIRST_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )


def test_report_records_production_usage() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(create_definition(),),
        specifications=(create_tool_workflow(FIRST_WORKFLOW_ID),),
        production_states=(create_production_state(FIRST_WORKFLOW_ID),),
        runs=(),
    )

    assert report.in_production
    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert entry.configured
    assert entry.in_production


def test_report_groups_matching_history_by_run() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(create_definition(),),
        specifications=(),
        production_states=(),
        runs=(
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=SECOND_RUN_ID,
                executed_tool_id=OTHER_TOOL_ID,
            ),
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=THIRD_RUN_ID,
                started_at=STARTED_AT + timedelta(minutes=5),
            ),
        ),
    )

    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert not entry.configured
    assert not entry.in_production
    assert tuple(run.run_id for run in entry.runs) == (
        FIRST_RUN_ID,
        THIRD_RUN_ID,
    )
    assert entry.runs[1].started_at == STARTED_AT + timedelta(minutes=5)
    assert entry.runs[0].usages[0].implementation_id == IMPLEMENTATION_ID
    assert entry.runs[0].usages[0].tool_id == TOOL_ID


def test_report_without_definitions_reports_history_only() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(),
        specifications=(create_tool_workflow(FIRST_WORKFLOW_ID),),
        production_states=(create_production_state(FIRST_WORKFLOW_ID),),
        runs=(
            create_run(
                SECOND_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
        ),
    )

    assert report.tool_names == ()
    assert tuple(
        (
            entry.workflow.id,
            entry.configured,
            entry.in_production,
            len(entry.runs),
        )
        for entry in report.workflows
    ) == ((SECOND_WORKFLOW_ID, False, False, 1),)


def test_report_does_not_borrow_names_from_other_tools() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(
            create_definition(),
            create_definition(
                tool_id=OTHER_TOOL_ID,
                name=OTHER_TOOL_NAME,
            ),
        ),
        specifications=(
            create_tool_workflow(
                FIRST_WORKFLOW_ID,
                tool_name=OTHER_TOOL_NAME,
            ),
            create_tool_workflow(SECOND_WORKFLOW_ID),
        ),
        production_states=(),
        runs=(),
    )

    assert report.tool_names == (TOOL_NAME,)
    assert tuple(entry.workflow.id for entry in report.workflows) == (SECOND_WORKFLOW_ID,)


def test_report_orders_workflows_by_discovery_source() -> None:
    report = tool_usage_report(
        TOOL_ID,
        definitions=(create_definition(),),
        specifications=(
            create_tool_workflow(SECOND_WORKFLOW_ID),
            create_tool_workflow(FIRST_WORKFLOW_ID),
        ),
        production_states=(create_production_state(THIRD_WORKFLOW_ID),),
        runs=(
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
        ),
    )

    assert tuple(entry.workflow.id for entry in report.workflows) == (
        SECOND_WORKFLOW_ID,
        FIRST_WORKFLOW_ID,
        THIRD_WORKFLOW_ID,
    )
    assert tuple(entry.workflow.id for entry in report.production_workflows) == (THIRD_WORKFLOW_ID,)


def test_usage_entry_requires_at_least_one_usage() -> None:
    with pytest.raises(ValidationError):
        WorkflowToolUsageEntry(
            workflow=create_metadata(FIRST_WORKFLOW_ID),
        )


def test_report_rejects_duplicate_workflows() -> None:
    entry = WorkflowToolUsageEntry(
        workflow=create_metadata(FIRST_WORKFLOW_ID),
        configured=True,
    )

    with pytest.raises(ValidationError):
        WorkflowToolUsageReport(
            tool_id=TOOL_ID,
            workflows=(
                entry,
                entry,
            ),
        )
