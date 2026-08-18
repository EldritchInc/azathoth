"""Tests for executable tool-backed strategies."""

import asyncio
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
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
        source=("def run():\n    return {'word_count': 3}\n"),
    )


def test_tool_strategy_exposes_metadata() -> None:
    strategy = ToolStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="word_count",
            description="Count words.",
            version="1.0.0",
        ),
        implementation=create_implementation(),
        executor=StubToolExecutor(),
    )

    assert strategy.metadata.id == STRATEGY_ID
    assert strategy.metadata.name == "word_count"
    assert strategy.metadata.version == "1.0.0"


def test_tool_strategy_exposes_resolved_implementation() -> None:
    implementation = create_implementation()

    strategy = ToolStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="word_count",
            description="Count words.",
            version="1.0.0",
        ),
        implementation=implementation,
        executor=StubToolExecutor(),
    )

    assert strategy.implementation is implementation


def test_tool_strategy_executes_resolved_implementation() -> None:
    implementation = create_implementation()
    executor = StubToolExecutor()

    strategy = ToolStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="word_count",
            description="Count words.",
            version="1.0.0",
        ),
        implementation=implementation,
        executor=executor,
        inputs={
            "text": "one two three",
        },
    )

    outcome = asyncio.run(
        strategy.run(
            Context(),
        )
    )

    assert executor.implementation is implementation
    assert executor.inputs == {
        "text": "one two three",
    }
    assert outcome.output == {
        "word_count": 3,
    }
