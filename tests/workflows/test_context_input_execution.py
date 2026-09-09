"""End-to-end tests for workflow inputs sourced from execution context."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    PythonToolExecutor,
    ToolImplementation,
    ToolStrategy,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowValueBinding,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

TOOL_ID = UUID("33333333-3333-3333-3333-333333333333")

IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_tool_strategy() -> ToolStrategy:
    """Create one deterministic word-count tool strategy."""

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID,
            name="word_count",
            description="Count words in externally supplied text.",
            version="1.0.0",
        ),
        implementation=ToolImplementation(
            id=IMPLEMENTATION_ID,
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            version="1.0.0",
            runtime="python",
            source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
        ),
        executor=PythonToolExecutor(),
    )


def create_candidate() -> WorkflowCandidate:
    """Create a first-step tool consuming external execution context."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="External tool input",
            description="Pass execution context into a first-step tool.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=TOOL_STEP_ID,
                strategy=create_tool_strategy(),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowContextReference(
                            event_type="request.received",
                            field_name="input",
                        ),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="word_count",
                        path=("word_count",),
                    ),
                ),
            ),
        ),
    )


def create_context(
    value: str = "one two three four",
) -> Context:
    """Create execution context containing one external request."""

    return Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={
                    "input": value,
                },
                producer="request-api",
            ),
        )
    )


def test_first_step_tool_consumes_context_backed_input() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            create_context(),
        )
    )

    assert len(run.steps) == 1

    step = run.steps[0]

    assert step.execution is not None

    assert step.execution.output == {
        "word_count": 4,
    }

    values = run.values_named(
        "word_count",
    )

    assert len(values) == 1
    assert values[0].value == 4
    assert values[0].producer_step_id == TOOL_STEP_ID


def test_context_backed_input_uses_latest_matching_event() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={
                    "input": "one",
                },
                producer="request-api",
            ),
            ContextEvent(
                event_type="other.event",
                payload={
                    "input": "ignore this entirely",
                },
                producer="other-system",
            ),
            ContextEvent(
                event_type="request.received",
                payload={
                    "input": "one two three",
                },
                producer="request-api",
            ),
        )
    )

    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            context,
        )
    )

    step = run.steps[0]

    assert step.execution is not None

    assert step.execution.output == {
        "word_count": 3,
    }


def test_context_backed_input_records_trusted_bound_input() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            create_context(),
        )
    )

    step = run.steps[0]

    assert step.execution is not None

    bound_inputs = step.execution.initial_context.by_type(
        "workflow.input.bound",
    )

    assert len(bound_inputs) == 1

    assert bound_inputs[0].producer == "workflow-runner"

    assert bound_inputs[0].payload == {
        "name": "text",
        "value": "one two three four",
        "source_event_type": "request.received",
        "source_field_name": "input",
    }


def test_context_backed_input_does_not_leak_into_final_context() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            create_context(),
        )
    )

    assert (
        run.final_context.by_type(
            "workflow.input.bound",
        )
        == ()
    )


def test_context_backed_input_rejects_missing_event() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="other.event",
                payload={
                    "input": "one two three",
                },
                producer="other-system",
            ),
        )
    )

    with pytest.raises(
        RuntimeError,
        match=("Workflow context input 'text' could not resolve event type 'request.received'"),
    ):
        asyncio.run(
            WorkflowRunner().run(
                create_candidate(),
                context,
            )
        )


def test_context_backed_input_rejects_missing_field() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={
                    "other": "one two three",
                },
                producer="request-api",
            ),
        )
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Workflow context input 'text' could not resolve "
            "field 'input' from event type 'request.received'"
        ),
    ):
        asyncio.run(
            WorkflowRunner().run(
                create_candidate(),
                context,
            )
        )
