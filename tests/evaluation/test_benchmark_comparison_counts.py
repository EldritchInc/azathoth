"""Tests for counting benchmark cases by comparison."""

from uuid import UUID

from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)


def create_case(
    index: int,
    comparison: OutcomeComparison,
    expected: JsonValue = "label",
) -> BenchmarkCase:
    """Create one benchmark case judged by one comparison."""

    return BenchmarkCase(
        id=UUID(int=index),
        input=f"input {index}",
        expected=ExpectedOutcome(
            description=f"Case {index}",
            value=expected,
            comparison=comparison,
        ),
    )


def test_comparison_counts_follow_comparison_declaration_order() -> None:
    dataset = BenchmarkDataset(
        name="mixed",
        description="Mixed comparisons.",
        cases=(
            create_case(1, OutcomeComparison.SCHEMA, {"type": "string"}),
            create_case(2, OutcomeComparison.NORMALIZED),
            create_case(3, OutcomeComparison.EXACT),
            create_case(4, OutcomeComparison.NORMALIZED),
            create_case(5, OutcomeComparison.SEMANTIC),
        ),
    )

    assert list(dataset.comparison_counts().items()) == [
        (OutcomeComparison.EXACT, 1),
        (OutcomeComparison.NORMALIZED, 2),
        (OutcomeComparison.SEMANTIC, 1),
        (OutcomeComparison.SCHEMA, 1),
    ]


def test_comparison_counts_omit_unused_comparisons() -> None:
    dataset = BenchmarkDataset(
        name="exact",
        description="Exact comparisons only.",
        cases=(
            create_case(1, OutcomeComparison.EXACT),
            create_case(2, OutcomeComparison.EXACT),
        ),
    )

    assert dataset.comparison_counts() == {
        OutcomeComparison.EXACT: 2,
    }


def test_comparison_counts_of_empty_dataset_are_empty() -> None:
    dataset = BenchmarkDataset(
        name="empty",
        description="No cases.",
    )

    assert dataset.comparison_counts() == {}
