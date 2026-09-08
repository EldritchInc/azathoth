"""Tests for the checked-in portable benchmark example."""

from pathlib import Path
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

CLASSIFICATION_DOCUMENT = PROJECT_ROOT / "examples" / "benchmarks" / "classification.json"

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

POSITIVE_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

NEGATIVE_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_expected_dataset() -> BenchmarkDataset:
    """Create the dataset represented by the checked-in example."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="classification benchmark",
        description=("Verify deterministic positive and negative classification behavior."),
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=POSITIVE_CASE_ID,
                input={
                    "text": "This was excellent.",
                },
                expected=ExpectedOutcome(
                    description="Classify the input as positive.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "positive",
                },
            ),
            BenchmarkCase(
                id=NEGATIVE_CASE_ID,
                input={
                    "text": "This was terrible.",
                },
                expected=ExpectedOutcome(
                    description="Classify the input as negative.",
                    value="negative",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "negative",
                },
            ),
        ),
    )


def test_checked_in_benchmark_example_decodes_to_expected_dataset() -> None:
    encoded = CLASSIFICATION_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert (
        decode_benchmark_document(
            encoded,
        )
        == create_expected_dataset()
    )


def test_checked_in_benchmark_example_matches_canonical_encoding() -> None:
    encoded = CLASSIFICATION_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encoded.rstrip("\n") == encode_benchmark_document(
        create_expected_dataset(),
    )
