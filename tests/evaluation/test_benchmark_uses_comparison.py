"""Tests for asking which comparisons a benchmark dataset uses."""

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)


def create_case(
    comparison: OutcomeComparison,
) -> BenchmarkCase:
    """Create one case judged with one comparison."""

    return BenchmarkCase(
        input="request",
        expected=ExpectedOutcome(
            description="Expected answer.",
            value="answer",
            comparison=comparison,
        ),
    )


def test_dataset_reports_comparisons_its_cases_use() -> None:
    dataset = BenchmarkDataset(
        name="mixed",
        description="Exact and semantic cases.",
        cases=(
            create_case(OutcomeComparison.EXACT),
            create_case(OutcomeComparison.SEMANTIC),
        ),
    )

    assert dataset.uses_comparison(OutcomeComparison.EXACT)
    assert dataset.uses_comparison(OutcomeComparison.SEMANTIC)
    assert not dataset.uses_comparison(OutcomeComparison.NORMALIZED)
    assert not dataset.uses_comparison(OutcomeComparison.SCHEMA)


def test_empty_dataset_uses_no_comparison() -> None:
    dataset = BenchmarkDataset(
        name="empty",
        description="No cases.",
    )

    assert not any(dataset.uses_comparison(comparison) for comparison in OutcomeComparison)
