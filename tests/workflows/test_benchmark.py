"""Tests for workflow benchmark execution."""

import asyncio
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_workflow_candidate,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")
STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_IDENTIFIER = "deterministic/classifier-small"


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic classification benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="sentiment-classification",
        description="Deterministic sentiment benchmark.",
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input="I absolutely loved this.",
                expected=ExpectedOutcome(
                    description="Positive sentiment",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            BenchmarkCase(
                id=SECOND_CASE_ID,
                input="Everything about this was terrible.",
                expected=ExpectedOutcome(
                    description="Negative sentiment",
                    value="negative",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def create_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create one executable workflow candidate for a benchmark case."""

    expected = case.expected.value

    if not isinstance(expected, str):
        raise TypeError("Classification benchmark expectations must be strings.")

    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Sentiment classification",
            description="Classify benchmark sentiment.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify sentiment",
                        description="Return a sentiment label.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=(f"Classify this text as positive or negative.\n\nText: {case.input}"),
                    ),
                    model_requirements=ModelRequirements(),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )

    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="deterministic",
                model="classifier-small",
                display_name="Deterministic Classifier",
                context_window_tokens=8_192,
            ),
        ),
    )

    registry = LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="deterministic",
                model="classifier-small",
                response_text=expected,
            ),
        },
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
    )


def create_failing_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate that intentionally fails one benchmark case."""

    candidate = create_candidate(case)

    if case.id != SECOND_CASE_ID:
        return candidate

    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Sentiment classification",
            description="Classify benchmark sentiment.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify sentiment",
                        description="Return a sentiment label.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=(f"Classify this text as positive or negative.\n\nText: {case.input}"),
                    ),
                    model_requirements=ModelRequirements(),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )

    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="deterministic",
                model="classifier-small",
                display_name="Deterministic Classifier",
                context_window_tokens=8_192,
            ),
        ),
    )

    registry = LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="deterministic",
                model="classifier-small",
                response_text="positive",
            ),
        },
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
    )


def test_workflow_benchmark_executes_all_cases() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    assert result.dataset_id == DATASET_ID
    assert result.cases_run == 2
    assert tuple(case.case_id for case in result.cases) == (
        FIRST_CASE_ID,
        SECOND_CASE_ID,
    )


def test_workflow_benchmark_evaluates_all_cases() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    assert result.cases_passed == 2
    assert result.accuracy == 1.0
    assert all(case.evaluation.passed for case in result.cases)


def test_workflow_benchmark_records_failed_evaluation() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_failing_candidate,
            output_name="classification",
        )
    )

    assert result.cases_run == 2
    assert result.cases_passed == 1
    assert result.accuracy == 0.5

    assert result.cases[0].evaluation.passed is True
    assert result.cases[1].evaluation.passed is False


def test_workflow_benchmark_records_execution_runs() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    assert all(case.run.succeeded for case in result.cases)
    assert tuple(case.run.values_named("classification")[0].value for case in result.cases) == (
        "positive",
        "negative",
    )


def test_workflow_benchmark_aggregates_usage() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    assert result.total_tokens > 0
    assert result.total_cost_usd == 0.0
    assert result.total_latency_ms == 0


def test_workflow_benchmark_handles_empty_dataset() -> None:
    dataset = BenchmarkDataset(
        name="empty",
        description="Empty benchmark.",
    )

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            dataset,
            create_candidate,
            output_name="classification",
        )
    )

    assert result.cases_run == 0
    assert result.cases_passed == 0
    assert result.accuracy == 0.0
    assert result.total_tokens == 0
    assert result.total_cost_usd == 0.0
    assert result.total_latency_ms == 0


def test_workflow_benchmark_round_trips_through_json() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    restored = type(result).model_validate_json(
        result.model_dump_json(),
    )

    assert restored == result
