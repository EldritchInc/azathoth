"""Tests for rendering step resource bindings in workflow runs."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import render_workflow_run
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.strategies import StrategyResourceBinding
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

IMPLEMENTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

MODEL_IDENTIFIER = "openrouter/example/model"

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    0,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    1,
    tzinfo=UTC,
)


def run_with_resources(
    *resources: StrategyResourceBinding,
) -> WorkflowRun:
    """Create one successful run whose single step bound the given resources."""

    context = Context()

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="resource strategy",
        strategy_version="1.0.0",
        output="success",
        resources=resources,
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    return WorkflowRun(
        id=RUN_ID,
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="resource workflow",
            description="Exercise resource binding rendering.",
            version="1.0.0",
        ),
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
                        completed_at=COMPLETED_AT,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def tool_binding() -> StrategyResourceBinding:
    """Create tool provenance matching tool strategy emission."""

    return StrategyResourceBinding(
        kind="tool",
        identifier=str(IMPLEMENTATION_ID),
        attributes={
            "tool_id": str(TOOL_ID),
            "tool_version": "1.0.0",
            "runtime": "python",
        },
    )


def test_run_rendering_includes_model_binding_before_output() -> None:
    rendered = render_workflow_run(
        run_with_resources(
            StrategyResourceBinding(
                kind="model",
                identifier=MODEL_IDENTIFIER,
            ),
        )
    )

    assert f"Resource: model {MODEL_IDENTIFIER}\n" in rendered
    assert rendered.index("Resource: model") < rendered.index("Output:")


def test_run_rendering_includes_tool_binding_with_sorted_attributes() -> None:
    rendered = render_workflow_run(run_with_resources(tool_binding()))

    assert (
        f"Resource: tool {IMPLEMENTATION_ID} "
        f"(runtime=python, tool_id={TOOL_ID}, tool_version=1.0.0)\n"
    ) in rendered


def test_run_rendering_preserves_binding_order() -> None:
    rendered = render_workflow_run(
        run_with_resources(
            tool_binding(),
            StrategyResourceBinding(
                kind="model",
                identifier=MODEL_IDENTIFIER,
            ),
        )
    )

    assert rendered.index("Resource: tool") < rendered.index("Resource: model")


def test_run_rendering_renders_structured_attributes_as_compact_json() -> None:
    rendered = render_workflow_run(
        run_with_resources(
            StrategyResourceBinding(
                kind="custom",
                identifier="resource-1",
                attributes={
                    "retries": 2,
                    "tags": [
                        "alpha",
                        "beta",
                    ],
                    "limits": {
                        "b": 2,
                        "a": 1,
                    },
                },
            ),
        )
    )

    assert (
        'Resource: custom resource-1 (limits={"a":1,"b":2}, retries=2, tags=["alpha","beta"])\n'
    ) in rendered


def test_run_rendering_omits_resources_when_none_were_bound() -> None:
    rendered = render_workflow_run(run_with_resources())

    assert "Resource:" not in rendered
