"""Tests for workflow benchmark scoring and ranking."""

import asyncio
from collections.abc import Callable
from uuid import UUID

import pytest

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
    WorkflowBenchmarkComparator,
    WorkflowBenchmarkRanker,
    WorkflowBenchmarkScorer,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowScoringPolicy,
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

MODEL_IDENTIFIER = "deterministic/classifier"


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic two-case classification benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="sentiment-classification",
        description="Deterministic sentiment ranking benchmark.",
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
    """Create a deterministic executable classification candidate."""

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
    """Create a candidate that always returns the expected label."""

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


def create_factories() -> dict[
    str,
    Callable[[BenchmarkCase], WorkflowCandidate],
]:
    """Create named deterministic benchmark candidates."""

    return {
        "perfect": create_perfect_candidate,
        "positive-only": create_positive_candidate,
        "negative-only": create_negative_candidate,
    }


def create_ranker() -> WorkflowBenchmarkRanker:
    """Create deterministic benchmark scoring and ranking."""

    scorer = WorkflowBenchmarkScorer(
        policy=WorkflowScoringPolicy(
            target_latency_seconds=1.0,
            target_cost_usd=0.01,
        ),
    )

    return WorkflowBenchmarkRanker(
        scorer=scorer,
    )


def test_benchmark_ranking_selects_highest_quality_candidate() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_factories(),
            output_name="classification",
        )
    )

    ranking = create_ranker().rank(comparison)

    assert ranking.winner.name == "perfect"
    assert ranking.winner.rank == 1
    assert ranking.winner.scorecard.quality_score == 1.0


def test_benchmark_ranking_preserves_existing_score_dimensions() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_factories(),
            output_name="classification",
        )
    )

    ranking = create_ranker().rank(comparison)

    perfect = ranking.entries[0]

    assert perfect.scorecard.quality_score == 1.0
    assert perfect.scorecard.reliability_score == 1.0
    assert perfect.scorecard.latency_score == 1.0
    assert perfect.scorecard.cost_score == 1.0
    assert perfect.scorecard.overall_score == 1.0


def test_benchmark_ranking_orders_lower_quality_candidates_after_winner() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_factories(),
            output_name="classification",
        )
    )

    ranking = create_ranker().rank(comparison)

    assert ranking.entries[0].name == "perfect"
    assert ranking.entries[0].rank == 1

    assert {
        ranking.entries[1].name,
        ranking.entries[2].name,
    } == {
        "positive-only",
        "negative-only",
    }

    assert ranking.entries[1].scorecard.quality_score == 0.5
    assert ranking.entries[2].scorecard.quality_score == 0.5


def test_benchmark_ranking_records_aggregate_rationale() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_factories(),
            output_name="classification",
        )
    )

    ranking = create_ranker().rank(comparison)

    assert "perfect" in ranking.winner.scorecard.rationale
    assert "2 cases" in ranking.winner.scorecard.rationale


def test_benchmark_ranking_rejects_empty_comparison() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            {},
            output_name="classification",
        )
    )

    with pytest.raises(
        ValueError,
        match="At least one benchmark candidate",
    ):
        create_ranker().rank(comparison)


def test_benchmark_ranking_round_trips_through_json() -> None:
    comparison = asyncio.run(
        WorkflowBenchmarkComparator().compare(
            create_dataset(),
            create_factories(),
            output_name="classification",
        )
    )

    ranking = create_ranker().rank(comparison)

    restored = type(ranking).model_validate_json(
        ranking.model_dump_json(),
    )

    assert restored == ranking
    assert restored.winner.name == "perfect"
