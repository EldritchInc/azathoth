"""Tests for workflow benchmark candidate comparison."""

import asyncio
from collections.abc import Callable
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
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
    WorkflowBenchmarkComparator,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")
STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_IDENTIFIER = "deterministic/classifier"


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic two-case classification benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="sentiment-classification",
        description="Deterministic sentiment comparison benchmark.",
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
    *,
    response_text: str,
) -> WorkflowCandidate:
    """Create an executable classification candidate."""

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
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
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
                model="classifier",
                display_name="Deterministic Classifier",
                context_window_tokens=8_192,
            ),
        ),
    )

    registry = LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="deterministic",
                model="classifier",
                response_text=response_text,
            ),
        },
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
    )


def create_perfect_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate that returns the expected benchmark label."""

    expected = case.expected.value

    if not isinstance(expected, str):
        raise TypeError("Classification expectations must be strings.")

    return create_candidate(
        case,
        response_text=expected,
    )


def create_positive_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate that always returns positive."""

    return create_candidate(
        case,
        response_text="positive",
    )


def create_negative_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate that always returns negative."""

    return create_candidate(
        case,
        response_text="negative",
    )


def create_candidate_factories() -> dict[
    str,
    Callable[[BenchmarkCase], WorkflowCandidate],
]:
    """Create deterministic named benchmark candidates."""

    return {
        "perfect": create_perfect_candidate,
        "positive-only": create_positive_candidate,
        "negative-only": create_negative_candidate,
    }


def test_benchmark_comparator_executes_all_candidates() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    assert comparison.dataset_id == DATASET_ID
    assert tuple(candidate.name for candidate in comparison.candidates) == (
        "perfect",
        "positive-only",
        "negative-only",
    )


def test_benchmark_comparator_records_candidate_accuracy() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    perfect = comparison.get("perfect")
    positive_only = comparison.get("positive-only")
    negative_only = comparison.get("negative-only")

    assert perfect is not None
    assert positive_only is not None
    assert negative_only is not None

    assert perfect.accuracy == 1.0
    assert positive_only.accuracy == 0.5
    assert negative_only.accuracy == 0.5


def test_benchmark_comparator_records_usage_independently() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    for candidate in comparison.candidates:
        assert candidate.result.cases_run == 2
        assert candidate.result.total_tokens > 0
        assert candidate.result.total_cost_usd == 0.0
        assert candidate.result.total_latency_ms == 0


def test_benchmark_comparator_preserves_candidate_order() -> None:
    factories: dict[
        str,
        Callable[[BenchmarkCase], WorkflowCandidate],
    ] = {
        "negative-only": create_negative_candidate,
        "perfect": create_perfect_candidate,
        "positive-only": create_positive_candidate,
    }

    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            factories,
            output_name="classification",
        )
    )

    assert tuple(candidate.name for candidate in comparison.candidates) == (
        "negative-only",
        "perfect",
        "positive-only",
    )


def test_benchmark_comparison_returns_named_result() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    result = comparison.get("perfect")

    assert result is not None
    assert result.cases_passed == 2
    assert result.accuracy == 1.0


def test_benchmark_comparison_returns_none_for_unknown_candidate() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    assert comparison.get("unknown") is None


def test_benchmark_comparison_handles_no_candidates() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            {},
            output_name="classification",
        )
    )

    assert comparison.dataset_id == DATASET_ID
    assert comparison.candidates == ()


def test_benchmark_comparison_round_trips_through_json() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_candidate_factories(),
            output_name="classification",
        )
    )

    restored = type(comparison).model_validate_json(
        comparison.model_dump_json(),
    )

    assert restored == comparison
