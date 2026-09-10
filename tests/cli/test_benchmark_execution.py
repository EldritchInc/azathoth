"""Tests for executing configured workflows against benchmarks."""

import asyncio
from uuid import UUID

import pytest

from azathoth.cli import execute_configured_benchmark
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.runtime import (
    AzathothRuntime,
    WorkflowNotConfiguredError,
)
from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    ToolStepSpecification,
    WorkflowBenchmarkRunner,
    WorkflowCatalog,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import portfolio_for_catalog

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

TOOL_ID = UUID("66666666-6666-6666-6666-666666666666")

IMPLEMENTATION_ID = UUID("77777777-7777-7777-7777-777777777777")


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic word-count benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="word-count",
        description="Verify configured external-input tool execution.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input="one two",
                expected=ExpectedOutcome(
                    description="Two words",
                    value=2,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            BenchmarkCase(
                id=SECOND_CASE_ID,
                input="one two three four",
                expected=ExpectedOutcome(
                    description="Four words",
                    value=4,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create one configured workflow backed by a word-count tool."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Configured word count",
            description="Count words supplied through external workflow input.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowContextReference(
                            event_type=WORKFLOW_INPUT_EVENT_TYPE,
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


def create_tool_catalog() -> ToolCatalog:
    """Create the durable word-count capability."""

    return ToolCatalog(
        definitions=(
            ToolDefinition(
                id=TOOL_ID,
                name="word_count",
                description="Count whitespace-delimited words.",
                version="1.0.0",
                input_schema=ToolInputSchema(
                    json_schema={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "text",
                        ],
                        "additionalProperties": False,
                    },
                ),
                output_schema=ToolOutputSchema(
                    json_schema={
                        "type": "object",
                        "properties": {
                            "word_count": {
                                "type": "integer",
                            },
                        },
                        "required": [
                            "word_count",
                        ],
                    },
                ),
            ),
        ),
    )


def create_implementation_catalog() -> ToolImplementationCatalog:
    """Create one executable word-count implementation."""

    return ToolImplementationCatalog(
        implementations=(
            ToolImplementation(
                id=IMPLEMENTATION_ID,
                tool_id=TOOL_ID,
                tool_version="1.0.0",
                version="1.0.0",
                runtime="python",
                entrypoint="run",
                source=(
                    "def run(text: str) -> dict[str, int]:\n"
                    "    return {'word_count': len(text.split())}\n"
                ),
            ),
        ),
    )


def create_runtime() -> AzathothRuntime:
    """Create one executable configured benchmark runtime."""

    models = ModelCatalog()

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(create_workflow(),),
        ),
        models=models,
        portfolio=portfolio_for_catalog(
            models,
        ),
        language_models=LanguageModelRegistry(),
        tools=create_tool_catalog(),
        tool_implementations=create_implementation_catalog(),
    )


def test_configured_benchmark_executes_workflow_by_identifier() -> None:
    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            output_name="word_count",
        )
    )

    assert result.dataset_id == DATASET_ID
    assert result.cases_run == 2
    assert result.cases_passed == 2
    assert result.accuracy == 1.0


def test_configured_benchmark_uses_same_workflow_for_every_case() -> None:
    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            output_name="word_count",
        )
    )

    assert tuple(case.run.workflow.id for case in result.cases) == (
        WORKFLOW_ID,
        WORKFLOW_ID,
    )


def test_configured_benchmark_case_inputs_drive_execution() -> None:
    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            output_name="word_count",
        )
    )

    assert tuple(
        case.run.values_named(
            "word_count",
        )[0].value
        for case in result.cases
    ) == (
        2,
        4,
    )


def test_configured_benchmark_preserves_canonical_case_input_context() -> None:
    dataset = create_dataset()

    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=dataset,
            output_name="word_count",
        )
    )

    assert tuple(
        case.run.initial_context.latest(
            WORKFLOW_INPUT_EVENT_TYPE,
        ).payload["input"]
        for case in result.cases
        if case.run.initial_context.latest(
            WORKFLOW_INPUT_EVENT_TYPE,
        )
        is not None
    ) == tuple(case.input for case in dataset.cases)


def test_configured_benchmark_preserves_unknown_workflow_error() -> None:
    with pytest.raises(
        WorkflowNotConfiguredError,
        match=(f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured"),
    ):
        asyncio.run(
            execute_configured_benchmark(
                runtime=create_runtime(),
                workflow_id=UNKNOWN_WORKFLOW_ID,
                dataset=create_dataset(),
                output_name="word_count",
            )
        )


def test_configured_benchmark_accepts_explicit_runner() -> None:
    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            output_name="word_count",
            runner=WorkflowBenchmarkRunner(),
        )
    )

    assert result.cases_run == 2
    assert result.cases_passed == 2
