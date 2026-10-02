"""Tests for human-readable workflow resource usage rendering."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import (
    render_model_usage_report,
    render_tool_usage_report,
)
from azathoth.workflows import (
    WorkflowHistoricalModelUsage,
    WorkflowHistoricalToolUsage,
    WorkflowMetadata,
    WorkflowModelUsageEntry,
    WorkflowModelUsageReport,
    WorkflowProductionModelUsage,
    WorkflowProductionModelUsageRole,
    WorkflowRunModelUsage,
    WorkflowRunToolUsage,
    WorkflowToolUsageEntry,
    WorkflowToolUsageReport,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

SECOND_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

IMPLEMENTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

MODEL_IDENTIFIER = "openrouter/example-model"

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
    name: str,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name=name,
        description=f"{name} description.",
        version="1.0.0",
    )


def test_render_empty_model_usage_report() -> None:
    report = WorkflowModelUsageReport(
        identifier=MODEL_IDENTIFIER,
    )

    assert render_model_usage_report(report) == (
        f"Model: {MODEL_IDENTIFIER}\nWorkflows: 0\nIn Production: no"
    )


def test_render_model_usage_report_with_configuration_production_and_history() -> None:
    report = WorkflowModelUsageReport(
        identifier=MODEL_IDENTIFIER,
        workflows=(
            WorkflowModelUsageEntry(
                workflow=create_metadata(
                    FIRST_WORKFLOW_ID,
                    "summarize",
                ),
                configured=True,
                production=(
                    WorkflowProductionModelUsage(
                        step_id=FIRST_STEP_ID,
                        role=WorkflowProductionModelUsageRole.PRIMARY,
                    ),
                    WorkflowProductionModelUsage(
                        step_id=SECOND_STEP_ID,
                        role=WorkflowProductionModelUsageRole.SUBSTITUTE,
                    ),
                ),
                runs=(
                    WorkflowRunModelUsage(
                        run_id=RUN_ID,
                        started_at=STARTED_AT,
                        usages=(
                            WorkflowHistoricalModelUsage(
                                step_id=FIRST_STEP_ID,
                                attempt_number=1,
                                identifier=MODEL_IDENTIFIER,
                            ),
                            WorkflowHistoricalModelUsage(
                                step_id=SECOND_STEP_ID,
                                attempt_number=2,
                                identifier=MODEL_IDENTIFIER,
                            ),
                        ),
                    ),
                ),
            ),
            WorkflowModelUsageEntry(
                workflow=create_metadata(
                    SECOND_WORKFLOW_ID,
                    "classify",
                ),
                configured=True,
            ),
        ),
    )

    assert render_model_usage_report(report) == "\n".join(
        (
            f"Model: {MODEL_IDENTIFIER}",
            "Workflows: 2",
            "In Production: yes",
            "",
            "Workflow 1",
            "Name: summarize",
            f"ID: {FIRST_WORKFLOW_ID}",
            "Configured: yes",
            f"Production: primary step {FIRST_STEP_ID}, substitute step {SECOND_STEP_ID}",
            "Runs: 1",
            (
                f"Run {RUN_ID} at 2026-10-02T12:00:00+00:00: "
                f"step {FIRST_STEP_ID} attempt 1, step {SECOND_STEP_ID} attempt 2"
            ),
            "",
            "Workflow 2",
            "Name: classify",
            f"ID: {SECOND_WORKFLOW_ID}",
            "Configured: yes",
            "Production: no",
            "Runs: 0",
        )
    )


def test_render_empty_tool_usage_report_with_unknown_names() -> None:
    report = WorkflowToolUsageReport(
        tool_id=TOOL_ID,
    )

    assert render_tool_usage_report(report) == (
        f"Tool ID: {TOOL_ID}\nNames: unknown\nWorkflows: 0\nIn Production: no"
    )


def test_render_tool_usage_report_with_configuration_production_and_history() -> None:
    report = WorkflowToolUsageReport(
        tool_id=TOOL_ID,
        tool_names=(
            "word_count",
            "word_counter",
        ),
        workflows=(
            WorkflowToolUsageEntry(
                workflow=create_metadata(
                    FIRST_WORKFLOW_ID,
                    "count words",
                ),
                configured=True,
                production=True,
            ),
            WorkflowToolUsageEntry(
                workflow=create_metadata(
                    SECOND_WORKFLOW_ID,
                    "retired counter",
                ),
                runs=(
                    WorkflowRunToolUsage(
                        run_id=RUN_ID,
                        started_at=STARTED_AT,
                        usages=(
                            WorkflowHistoricalToolUsage(
                                step_id=FIRST_STEP_ID,
                                attempt_number=1,
                                implementation_id=IMPLEMENTATION_ID,
                                tool_id=TOOL_ID,
                                tool_version="1.0.0",
                                runtime="python",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    assert render_tool_usage_report(report) == "\n".join(
        (
            f"Tool ID: {TOOL_ID}",
            "Names: word_count, word_counter",
            "Workflows: 2",
            "In Production: yes",
            "",
            "Workflow 1",
            "Name: count words",
            f"ID: {FIRST_WORKFLOW_ID}",
            "Configured: yes",
            "Production: yes",
            "Runs: 0",
            "",
            "Workflow 2",
            "Name: retired counter",
            f"ID: {SECOND_WORKFLOW_ID}",
            "Configured: no",
            "Production: no",
            "Runs: 1",
            (
                f"Run {RUN_ID} at 2026-10-02T12:00:00+00:00: "
                f"step {FIRST_STEP_ID} attempt 1 implementation {IMPLEMENTATION_ID} "
                "version 1.0.0 runtime python"
            ),
        )
    )
