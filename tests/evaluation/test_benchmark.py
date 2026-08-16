"""Tests for reusable benchmark dataset models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_expected_outcome(
    value: str = "positive",
) -> ExpectedOutcome:
    """Create a deterministic expected benchmark outcome."""

    return ExpectedOutcome(
        description="Sentiment classification",
        value=value,
        comparison=OutcomeComparison.EXACT,
    )


def create_case(
    *,
    case_id: UUID = FIRST_CASE_ID,
    text: str = "I absolutely loved this.",
    expected: str = "positive",
) -> BenchmarkCase:
    """Create a deterministic benchmark case."""

    return BenchmarkCase(
        id=case_id,
        input=text,
        expected=create_expected_outcome(expected),
        metadata={
            "difficulty": "easy",
            "domain": "sentiment",
        },
    )


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic benchmark dataset."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="sentiment-classification",
        description="Small sentiment classification benchmark.",
        version="1.0.0",
        cases=(
            create_case(),
            create_case(
                case_id=SECOND_CASE_ID,
                text="Everything about this was terrible.",
                expected="negative",
            ),
        ),
    )


def test_benchmark_case_records_input_and_expected_outcome() -> None:
    case = create_case()

    assert case.id == FIRST_CASE_ID
    assert case.input == "I absolutely loved this."
    assert case.expected == create_expected_outcome()
    assert case.metadata == {
        "difficulty": "easy",
        "domain": "sentiment",
    }


def test_benchmark_case_generates_identifier() -> None:
    case = BenchmarkCase(
        input="I absolutely loved this.",
        expected=create_expected_outcome(),
    )

    assert isinstance(case.id, UUID)


def test_benchmark_case_supports_structured_input() -> None:
    case = BenchmarkCase(
        input={
            "text": "I absolutely loved this.",
            "language": "en",
        },
        expected=create_expected_outcome(),
    )

    assert case.input == {
        "text": "I absolutely loved this.",
        "language": "en",
    }


def test_benchmark_case_defaults_metadata_to_empty() -> None:
    case = BenchmarkCase(
        input="I absolutely loved this.",
        expected=create_expected_outcome(),
    )

    assert case.metadata == {}


def test_benchmark_case_is_immutable() -> None:
    case = create_case()

    with pytest.raises(ValidationError):
        case.input = "Changed"


def test_benchmark_case_round_trips_through_json() -> None:
    case = create_case()

    restored = BenchmarkCase.model_validate_json(
        case.model_dump_json(),
    )

    assert restored == case


def test_benchmark_dataset_records_cases() -> None:
    dataset = create_dataset()

    assert dataset.id == DATASET_ID
    assert dataset.name == "sentiment-classification"
    assert dataset.description == ("Small sentiment classification benchmark.")
    assert dataset.version == "1.0.0"
    assert len(dataset.cases) == 2
    assert dataset.cases[0].id == FIRST_CASE_ID
    assert dataset.cases[1].id == SECOND_CASE_ID


def test_benchmark_dataset_generates_identifier() -> None:
    dataset = BenchmarkDataset(
        name="sentiment-classification",
        description="Small sentiment classification benchmark.",
    )

    assert isinstance(dataset.id, UUID)


def test_benchmark_dataset_defaults_version() -> None:
    dataset = BenchmarkDataset(
        name="sentiment-classification",
        description="Small sentiment classification benchmark.",
    )

    assert dataset.version == "1.0.0"


def test_benchmark_dataset_defaults_cases_to_empty() -> None:
    dataset = BenchmarkDataset(
        name="sentiment-classification",
        description="Small sentiment classification benchmark.",
    )

    assert dataset.cases == ()


def test_benchmark_dataset_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        BenchmarkDataset(
            name="",
            description="Small sentiment classification benchmark.",
        )


def test_benchmark_dataset_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        BenchmarkDataset(
            name="sentiment-classification",
            description="",
        )


def test_benchmark_dataset_rejects_empty_version() -> None:
    with pytest.raises(ValidationError):
        BenchmarkDataset(
            name="sentiment-classification",
            description="Small sentiment classification benchmark.",
            version="",
        )


def test_benchmark_dataset_rejects_duplicate_case_identifiers() -> None:
    first = create_case()
    duplicate = create_case(
        text="Different text.",
        expected="negative",
    )

    with pytest.raises(
        ValidationError,
        match="duplicate case identifiers",
    ):
        BenchmarkDataset(
            name="sentiment-classification",
            description="Small sentiment classification benchmark.",
            cases=(
                first,
                duplicate,
            ),
        )


def test_benchmark_dataset_is_immutable() -> None:
    dataset = create_dataset()

    with pytest.raises(ValidationError):
        dataset.version = "2.0.0"


def test_benchmark_dataset_round_trips_through_json() -> None:
    dataset = create_dataset()

    restored = BenchmarkDataset.model_validate_json(
        dataset.model_dump_json(),
    )

    assert restored == dataset
