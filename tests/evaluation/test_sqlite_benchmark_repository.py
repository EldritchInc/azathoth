"""Tests for SQLite benchmark dataset persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRepository,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
    require_benchmark_repository,
)

FIRST_DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_DATASET_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_dataset(
    *,
    dataset_id: UUID = FIRST_DATASET_ID,
    name: str = "classification benchmark",
    version: str = "1.0.0",
) -> BenchmarkDataset:
    """Create one deterministic reusable benchmark dataset."""

    return BenchmarkDataset(
        id=dataset_id,
        name=name,
        description="Verify deterministic classification behavior.",
        version=version,
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
                    "difficulty": "easy",
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
                    "difficulty": "easy",
                },
            ),
        ),
    )


def test_sqlite_benchmark_repository_saves_and_gets_dataset(
    tmp_path: Path,
) -> None:
    repository = SQLiteBenchmarkRepository(tmp_path / "benchmarks.db")

    dataset = create_dataset()

    repository.save(dataset)

    restored = repository.get(FIRST_DATASET_ID)

    assert restored == dataset
    assert restored is not dataset


def test_sqlite_benchmark_repository_returns_none_for_unknown_dataset(
    tmp_path: Path,
) -> None:
    repository = SQLiteBenchmarkRepository(tmp_path / "benchmarks.db")

    assert repository.get(FIRST_DATASET_ID) is None


def test_sqlite_benchmark_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteBenchmarkRepository(tmp_path / "benchmarks.db")

    first = create_dataset()

    second = create_dataset(
        dataset_id=SECOND_DATASET_ID,
        name="second benchmark",
        version="2.0.0",
    )

    repository.save(first)
    repository.save(second)

    assert repository.datasets() == (
        first,
        second,
    )


def test_sqlite_benchmark_repository_rejects_duplicate_dataset(
    tmp_path: Path,
) -> None:
    repository = SQLiteBenchmarkRepository(tmp_path / "benchmarks.db")

    dataset = create_dataset()

    repository.save(dataset)

    with pytest.raises(
        ValueError,
        match=(f"Benchmark dataset {FIRST_DATASET_ID} already exists"),
    ):
        repository.save(dataset)


def test_sqlite_benchmark_repository_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "benchmarks.db"

    dataset = create_dataset()

    SQLiteBenchmarkRepository(database).save(dataset)

    restored = SQLiteBenchmarkRepository(database).get(FIRST_DATASET_ID)

    assert restored == dataset
    assert restored is not dataset


def test_sqlite_benchmark_repository_preserves_complete_dataset(
    tmp_path: Path,
) -> None:
    database = tmp_path / "benchmarks.db"

    dataset = create_dataset()

    SQLiteBenchmarkRepository(database).save(dataset)

    restored = SQLiteBenchmarkRepository(database).get(FIRST_DATASET_ID)

    assert restored is not None

    assert restored.id == FIRST_DATASET_ID
    assert restored.name == "classification benchmark"
    assert restored.version == "1.0.0"
    assert len(restored.cases) == 2

    first_case = restored.cases[0]
    second_case = restored.cases[1]

    assert first_case.id == FIRST_CASE_ID
    assert first_case.input == "good"
    assert first_case.expected.value == "positive"
    assert first_case.expected.comparison is OutcomeComparison.EXACT
    assert first_case.metadata == {
        "category": "positive",
        "difficulty": "easy",
    }

    assert second_case.id == SECOND_CASE_ID
    assert second_case.input == "bad"
    assert second_case.expected.value == "negative"
    assert second_case.expected.comparison is OutcomeComparison.EXACT
    assert second_case.metadata == {
        "category": "negative",
        "difficulty": "easy",
    }


def test_sqlite_benchmark_repository_preserves_dataset_version(
    tmp_path: Path,
) -> None:
    database = tmp_path / "benchmarks.db"

    dataset = create_dataset(version="3.2.1")

    SQLiteBenchmarkRepository(database).save(dataset)

    restored = SQLiteBenchmarkRepository(database).get(FIRST_DATASET_ID)

    assert restored is not None
    assert restored.version == "3.2.1"


def test_sqlite_benchmark_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: BenchmarkRepository = require_benchmark_repository(
        SQLiteBenchmarkRepository(tmp_path / "benchmarks.db")
    )

    assert repository.datasets() == ()
