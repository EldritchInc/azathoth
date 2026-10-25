"""Tests for rejecting unexecutable tool runtimes during generation."""

import asyncio

import pytest

from azathoth.context import Context
from azathoth.tools import (
    ToolStrategy,
    unsupported_runtime_message,
)
from azathoth.workflows import WorkflowGenerationError
from tests.workflows.test_tool_generation import (
    create_implementation,
    create_implementation_resolver,
    create_specification,
    create_tool_resolver,
    generate_candidate,
)


def test_generation_rejects_an_implementation_no_executor_supports() -> None:
    implementation = create_implementation(
        runtime="javascript",
    )

    with pytest.raises(
        WorkflowGenerationError,
        match=unsupported_runtime_message(implementation),
    ):
        generate_candidate(
            create_specification(
                runtime=None,
            ),
            tool_resolver=create_tool_resolver(),
            tool_implementation_resolver=create_implementation_resolver(
                implementation,
            ),
        )


def test_generated_tool_strategy_executes_through_runtime_dispatch() -> None:
    candidate = generate_candidate(
        create_specification(),
        tool_resolver=create_tool_resolver(),
        tool_implementation_resolver=create_implementation_resolver(
            create_implementation(),
        ),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ToolStrategy,
    )

    outcome = asyncio.run(
        strategy.run(
            Context(),
        )
    )

    assert outcome.output == {
        "word_count": 3,
    }
