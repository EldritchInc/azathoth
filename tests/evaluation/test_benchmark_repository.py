"""Tests for reusable benchmark dataset repositories."""

from uuid import UUID

import pytest

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRepository,
    ExpectedOutcome,
    InMemoryBenchmarkRepository,
    OutcomeComparison,
    require_benchmark_repository,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_dataset() -> BenchmarkDataset:
    """Create one deterministic reusable benchmark dataset."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="classification benchmark",
        description="Verify deterministic classification behavior.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input="good",
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
                id=SECOND_CASE_ID,
                input="bad",
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


def test_in_memory_benchmark_repository_saves_and_gets_dataset() -> None:
    repository = InMemoryBenchmarkRepository()

    dataset = create_dataset()

    repository.save(dataset)

    assert repository.get(DATASET_ID) is dataset


def test_in_memory_benchmark_repository_returns_none_for_unknown_dataset() -> None:
    repository = InMemoryBenchmarkRepository()

    assert repository.get(DATASET_ID) is None


def test_in_memory_benchmark_repository_preserves_insertion_order() -> None:
    repository = InMemoryBenchmarkRepository()

    first = create_dataset()

    second = first.model_copy(
        update={
            "id": UUID("44444444-4444-4444-4444-444444444444"),
            "name": "second benchmark",
        }
    )

    repository.save(first)
    repository.save(second)

    assert repository.datasets() == (
        first,
        second,
    )


def test_in_memory_benchmark_repository_rejects_duplicate_dataset() -> None:
    repository = InMemoryBenchmarkRepository()

    dataset = create_dataset()

    repository.save(dataset)

    with pytest.raises(
        ValueError,
        match=(f"Benchmark dataset {DATASET_ID} already exists"),
    ):
        repository.save(dataset)


def test_benchmark_repository_satisfies_protocol() -> None:
    repository: BenchmarkRepository = require_benchmark_repository(InMemoryBenchmarkRepository())

    assert repository.datasets() == ()
