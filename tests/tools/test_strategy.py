"""Tests for executable tool-backed strategies."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    ToolExecutionError,
    ToolImplementation,
    ToolStrategy,
)

STRATEGY_ID = UUID("11111111-1111-1111-1111-111111111111")
TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")
IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")


class StubToolExecutor:
    """Record execution of one tool implementation."""

    def __init__(self) -> None:
        self.implementation: ToolImplementation | None = None
        self.inputs: dict[str, JsonValue] | None = None

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Record the execution request and return deterministic output."""

        self.implementation = implementation
        self.inputs = inputs

        return {
            "word_count": 3,
        }


def create_implementation() -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
    )


def create_strategy(
    executor: StubToolExecutor,
) -> ToolStrategy:
    """Create a deterministic tool-backed strategy."""

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="word_count",
            description="Count words.",
            version="1.0.0",
        ),
        implementation=create_implementation(),
        executor=executor,
    )


def create_bound_input_context() -> Context:
    """Create context containing one workflow-bound tool input."""

    return Context().append(
        ContextEvent(
            event_type="workflow.input.bound",
            payload={
                "name": "text",
                "value": "one two three",
                "producer_step_id": ("44444444-4444-4444-4444-444444444444"),
                "source_name": "text",
            },
            producer="workflow-runner",
        )
    )


def test_tool_strategy_exposes_metadata() -> None:
    strategy = create_strategy(
        StubToolExecutor(),
    )

    assert strategy.metadata.id == STRATEGY_ID
    assert strategy.metadata.name == "word_count"
    assert strategy.metadata.version == "1.0.0"


def test_tool_strategy_exposes_resolved_implementation() -> None:
    strategy = create_strategy(
        StubToolExecutor(),
    )

    assert strategy.implementation == create_implementation()


def test_tool_strategy_executes_with_workflow_bound_inputs() -> None:
    executor = StubToolExecutor()
    strategy = create_strategy(executor)

    outcome = asyncio.run(
        strategy.run(
            create_bound_input_context(),
        )
    )

    assert executor.implementation == create_implementation()
    assert executor.inputs == {
        "text": "one two three",
    }
    assert outcome.output == {
        "word_count": 3,
    }


def test_tool_strategy_executes_without_bound_inputs() -> None:
    executor = StubToolExecutor()
    strategy = create_strategy(executor)

    asyncio.run(
        strategy.run(
            Context(),
        )
    )

    assert executor.inputs == {}


def test_tool_strategy_ignores_non_workflow_input_events() -> None:
    executor = StubToolExecutor()
    strategy = create_strategy(executor)

    context = Context().append(
        ContextEvent(
            event_type="request.received",
            payload={
                "name": "text",
                "value": "do not bind this",
            },
            producer="test",
        )
    )

    asyncio.run(strategy.run(context))

    assert executor.inputs == {}


def test_tool_strategy_ignores_spoofed_workflow_input_producer() -> None:
    executor = StubToolExecutor()
    strategy = create_strategy(executor)

    context = Context().append(
        ContextEvent(
            event_type="workflow.input.bound",
            payload={
                "name": "text",
                "value": "do not bind this",
            },
            producer="test",
        )
    )

    asyncio.run(strategy.run(context))

    assert executor.inputs == {}


def test_tool_strategy_rejects_missing_input_name() -> None:
    strategy = create_strategy(
        StubToolExecutor(),
    )

    context = Context().append(
        ContextEvent(
            event_type="workflow.input.bound",
            payload={
                "value": "one two three",
            },
            producer="workflow-runner",
        )
    )

    with pytest.raises(
        ToolExecutionError,
        match="require a non-empty string name",
    ):
        asyncio.run(strategy.run(context))


def test_tool_strategy_rejects_missing_input_value() -> None:
    strategy = create_strategy(
        StubToolExecutor(),
    )

    context = Context().append(
        ContextEvent(
            event_type="workflow.input.bound",
            payload={
                "name": "text",
            },
            producer="workflow-runner",
        )
    )

    with pytest.raises(
        ToolExecutionError,
        match="is missing its value",
    ):
        asyncio.run(strategy.run(context))


def test_tool_strategy_rejects_duplicate_bound_input_names() -> None:
    strategy = create_strategy(
        StubToolExecutor(),
    )

    context = Context()

    for value in (
        "one",
        "two",
    ):
        context = context.append(
            ContextEvent(
                event_type="workflow.input.bound",
                payload={
                    "name": "text",
                    "value": value,
                },
                producer="workflow-runner",
            )
        )

    with pytest.raises(
        ToolExecutionError,
        match="was bound more than once",
    ):
        asyncio.run(strategy.run(context))
