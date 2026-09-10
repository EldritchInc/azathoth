"""Tests for comparing configured workflows against one benchmark."""

import asyncio
from uuid import UUID

import pytest

from azathoth.cli import compare_configured_benchmarks
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
from azathoth.runtime import AzathothRuntime
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
    WorkflowCatalog,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import portfolio_for_catalog

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

CORRECT_WORKFLOW_ID = UUID("44444444-4444-4444-8444-444444444444")

INCORRECT_WORKFLOW_ID = UUID("55555555-5555-4555-8555-555555555555")

CORRECT_STEP_ID = UUID("66666666-6666-4666-8666-666666666666")

INCORRECT_STEP_ID = UUID("77777777-7777-4777-8777-777777777777")

CORRECT_TOOL_ID = UUID("88888888-8888-4888-8888-888888888888")

INCORRECT_TOOL_ID = UUID("99999999-9999-4999-8999-999999999999")

CORRECT_IMPLEMENTATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

INCORRECT_IMPLEMENTATION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic word-count benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="word-count",
        description="Compare configured word-count workflows.",
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


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    tool_name: str,
) -> WorkflowSpecification:
    """Create one configured externally fed tool workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=tool_name,
            description=f"Execute {tool_name}.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name=tool_name,
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


def create_tool_definition(
    *,
    tool_id: UUID,
    name: str,
) -> ToolDefinition:
    """Create one deterministic word-count capability."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"Execute {name}.",
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
    )


def create_runtime() -> AzathothRuntime:
    """Create two differently performing configured workflows."""

    models = ModelCatalog()

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(
                create_workflow(
                    workflow_id=CORRECT_WORKFLOW_ID,
                    step_id=CORRECT_STEP_ID,
                    tool_name="correct_word_count",
                ),
                create_workflow(
                    workflow_id=INCORRECT_WORKFLOW_ID,
                    step_id=INCORRECT_STEP_ID,
                    tool_name="incorrect_word_count",
                ),
            ),
        ),
        models=models,
        portfolio=portfolio_for_catalog(
            models,
        ),
        language_models=LanguageModelRegistry(),
        tools=ToolCatalog(
            definitions=(
                create_tool_definition(
                    tool_id=CORRECT_TOOL_ID,
                    name="correct_word_count",
                ),
                create_tool_definition(
                    tool_id=INCORRECT_TOOL_ID,
                    name="incorrect_word_count",
                ),
            ),
        ),
        tool_implementations=ToolImplementationCatalog(
            implementations=(
                ToolImplementation(
                    id=CORRECT_IMPLEMENTATION_ID,
                    tool_id=CORRECT_TOOL_ID,
                    tool_version="1.0.0",
                    version="1.0.0",
                    runtime="python",
                    entrypoint="run",
                    source=(
                        "def run(text: str) -> dict[str, int]:\n"
                        "    return {'word_count': len(text.split())}\n"
                    ),
                ),
                ToolImplementation(
                    id=INCORRECT_IMPLEMENTATION_ID,
                    tool_id=INCORRECT_TOOL_ID,
                    tool_version="1.0.0",
                    version="1.0.0",
                    runtime="python",
                    entrypoint="run",
                    source=(
                        "def run(text: str) -> dict[str, int]:\n    return {'word_count': 0}\n"
                    ),
                ),
            ),
        ),
    )


def create_policy() -> WorkflowScoringPolicy:
    """Create deterministic benchmark scoring policy."""

    return WorkflowScoringPolicy(
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )


def test_configured_comparison_ranks_workflows() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="word_count",
            scoring_policy=create_policy(),
        )
    )

    assert len(ranking.entries) == 2

    assert ranking.winner.name == str(CORRECT_WORKFLOW_ID)

    assert ranking.entries[0].rank == 1

    assert ranking.entries[1].name == str(INCORRECT_WORKFLOW_ID)

    assert ranking.entries[1].rank == 2


def test_configured_comparison_preserves_score_dimensions() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="word_count",
            scoring_policy=create_policy(),
        )
    )

    winner = ranking.winner.scorecard

    assert winner.quality_score == 1.0
    assert winner.reliability_score == 1.0
    assert winner.latency_score == 1.0
    assert winner.cost_score == 1.0
    assert winner.overall_score == 1.0

    loser = ranking.entries[1].scorecard

    assert loser.quality_score == 0.0
    assert loser.overall_score < winner.overall_score


def test_configured_comparison_uses_workflow_identifiers_as_names() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="word_count",
            scoring_policy=create_policy(),
        )
    )

    assert {entry.name for entry in ranking.entries} == {
        str(CORRECT_WORKFLOW_ID),
        str(INCORRECT_WORKFLOW_ID),
    }


def test_configured_comparison_rejects_fewer_than_two_workflows() -> None:
    with pytest.raises(
        ValueError,
        match="At least two configured workflows",
    ):
        asyncio.run(
            compare_configured_benchmarks(
                runtime=create_runtime(),
                workflow_ids=(CORRECT_WORKFLOW_ID,),
                dataset=create_dataset(),
                output_name="word_count",
                scoring_policy=create_policy(),
            )
        )


def test_configured_comparison_rejects_duplicate_workflows() -> None:
    with pytest.raises(
        ValueError,
        match="Configured benchmark workflow identifiers must be unique",
    ):
        asyncio.run(
            compare_configured_benchmarks(
                runtime=create_runtime(),
                workflow_ids=(
                    CORRECT_WORKFLOW_ID,
                    CORRECT_WORKFLOW_ID,
                ),
                dataset=create_dataset(),
                output_name="word_count",
                scoring_policy=create_policy(),
            )
        )
