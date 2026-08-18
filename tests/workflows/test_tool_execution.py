"""End-to-end workflow execution tests for tool-backed strategies."""

import asyncio
from uuid import UUID

from azathoth.context import Context
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.tools import (
    PythonToolExecutor,
    ToolImplementation,
    ToolStrategy,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
PRODUCER_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
TOOL_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
PRODUCER_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")
TOOL_ID = UUID("55555555-5555-5555-5555-555555555555")
IMPLEMENTATION_ID = UUID("66666666-6666-6666-6666-666666666666")


class TextProducerStrategy:
    """Produce deterministic text for a downstream tool."""

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return StrategyMetadata(
            id=PRODUCER_STRATEGY_ID,
            name="text-producer",
            description="Produce deterministic text.",
            version="1.0.0",
        )

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Produce deterministic text."""

        del context

        return StrategyOutcome(
            output={
                "text": "one two three four",
            },
        )


def create_tool_strategy() -> ToolStrategy:
    """Create a deterministic word-count tool strategy."""

    implementation = ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
    )

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID,
            name="word_count",
            description="Count words in supplied text.",
            version="1.0.0",
        ),
        implementation=implementation,
        executor=PythonToolExecutor(),
    )


def create_candidate() -> WorkflowCandidate:
    """Create a workflow that passes an upstream value into a tool."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Tool execution workflow",
            description="Pass workflow values into a deterministic tool.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=PRODUCER_STEP_ID,
                strategy=TextProducerStrategy(),
                outputs=(
                    WorkflowValueBinding(
                        name="text",
                        path=("text",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=TOOL_STEP_ID,
                strategy=create_tool_strategy(),
                depends_on=(PRODUCER_STEP_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowValueReference(
                            producer_step_id=PRODUCER_STEP_ID,
                            name="text",
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


def test_tool_step_consumes_bound_workflow_value() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            Context(),
        )
    )

    assert len(run.steps) == 2

    producer_step = run.steps[0]
    tool_step = run.steps[1]

    assert producer_step.execution is not None
    assert tool_step.execution is not None

    assert producer_step.execution.output == {
        "text": "one two three four",
    }

    assert tool_step.execution.output == {
        "word_count": 4,
    }


def test_tool_step_exports_structured_workflow_value() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            Context(),
        )
    )

    values = run.values_named(
        "word_count",
    )

    assert len(values) == 1
    assert values[0].producer_step_id == TOOL_STEP_ID
    assert values[0].value == 4


def test_tool_step_execution_records_bound_input_context() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            Context(),
        )
    )

    tool_step = run.steps[1]

    assert tool_step.execution is not None

    bound_inputs = tool_step.execution.initial_context.by_type(
        "workflow.input.bound",
    )

    assert len(bound_inputs) == 1

    assert bound_inputs[0].payload == {
        "name": "text",
        "value": "one two three four",
        "producer_step_id": str(PRODUCER_STEP_ID),
        "source_name": "text",
    }


def test_workflow_input_binding_does_not_leak_into_final_context() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            create_candidate(),
            Context(),
        )
    )

    assert (
        run.final_context.by_type(
            "workflow.input.bound",
        )
        == ()
    )
