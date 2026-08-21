"""Tests for reconstruction of benchmark catalogs."""

from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCatalogLoader,
    BenchmarkDataset,
    ExpectedOutcome,
    InMemoryBenchmarkRepository,
    OutcomeComparison,
)

FIRST_DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_DATASET_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_dataset(
    *,
    dataset_id: UUID,
    name: str,
) -> BenchmarkDataset:
    """Create deterministic benchmark data."""

    return BenchmarkDataset(
        id=dataset_id,
        name=name,
        description=f"Execute {name}.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                input=name,
                expected=ExpectedOutcome(
                    description="Return the expected value.",
                    value=name,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def test_benchmark_catalog_loader_reconstructs_repository_datasets() -> None:
    repository = InMemoryBenchmarkRepository()

    first = create_dataset(
        dataset_id=FIRST_DATASET_ID,
        name="first benchmark",
    )

    second = create_dataset(
        dataset_id=SECOND_DATASET_ID,
        name="second benchmark",
    )

    repository.save(first)
    repository.save(second)

    catalog = BenchmarkCatalogLoader(repository).load_catalog()

    assert catalog.datasets == (
        first,
        second,
    )


def test_benchmark_catalog_loader_preserves_repository_order() -> None:
    repository = InMemoryBenchmarkRepository()

    repository.save(
        create_dataset(
            dataset_id=SECOND_DATASET_ID,
            name="second benchmark",
        )
    )

    repository.save(
        create_dataset(
            dataset_id=FIRST_DATASET_ID,
            name="first benchmark",
        )
    )

    catalog = BenchmarkCatalogLoader(repository).load_catalog()

    assert catalog.identifiers == (
        SECOND_DATASET_ID,
        FIRST_DATASET_ID,
    )


def test_benchmark_catalog_loader_returns_empty_catalog() -> None:
    catalog = BenchmarkCatalogLoader(InMemoryBenchmarkRepository()).load_catalog()

    assert catalog.datasets == ()
