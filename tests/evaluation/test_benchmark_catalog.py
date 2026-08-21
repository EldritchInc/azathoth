"""Tests for immutable benchmark catalogs."""

from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCatalog,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)

FIRST_DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_DATASET_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_dataset(
    *,
    dataset_id: UUID,
    name: str,
) -> BenchmarkDataset:
    """Create one deterministic benchmark dataset."""

    return BenchmarkDataset(
        id=dataset_id,
        name=name,
        description=f"Execute {name}.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                input=name,
                expected=ExpectedOutcome(
                    description="Return the expected result.",
                    value=name,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def test_benchmark_catalog_preserves_dataset_order() -> None:
    first = create_dataset(
        dataset_id=FIRST_DATASET_ID,
        name="first benchmark",
    )

    second = create_dataset(
        dataset_id=SECOND_DATASET_ID,
        name="second benchmark",
    )

    catalog = BenchmarkCatalog(
        datasets=(
            first,
            second,
        )
    )

    assert catalog.datasets == (
        first,
        second,
    )

    assert catalog.identifiers == (
        FIRST_DATASET_ID,
        SECOND_DATASET_ID,
    )


def test_benchmark_catalog_gets_dataset_by_identifier() -> None:
    dataset = create_dataset(
        dataset_id=FIRST_DATASET_ID,
        name="first benchmark",
    )

    catalog = BenchmarkCatalog(datasets=(dataset,))

    assert catalog.get(FIRST_DATASET_ID) is dataset


def test_benchmark_catalog_returns_none_for_unknown_dataset() -> None:
    catalog = BenchmarkCatalog()

    assert catalog.get(FIRST_DATASET_ID) is None
