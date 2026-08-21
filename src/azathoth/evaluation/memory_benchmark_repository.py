"""Deterministic in-memory persistence for benchmark datasets."""

from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_repository import BenchmarkRepository


class InMemoryBenchmarkRepository:
    """Store immutable benchmark datasets in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._datasets: dict[
            UUID,
            BenchmarkDataset,
        ] = {}

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> None:
        """Persist one dataset without replacing existing configuration."""

        if dataset.id in self._datasets:
            raise ValueError(f"Benchmark dataset {dataset.id} already exists.")

        self._datasets[dataset.id] = dataset

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return one dataset by identifier."""

        return self._datasets.get(dataset_id)

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return all datasets in insertion order."""

        return tuple(self._datasets.values())


def require_benchmark_repository(
    repository: BenchmarkRepository,
) -> BenchmarkRepository:
    """Return a repository after static protocol validation."""

    return repository
