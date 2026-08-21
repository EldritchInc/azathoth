"""Persistence contracts for reusable benchmark datasets."""

from typing import Protocol
from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset


class BenchmarkRepository(Protocol):
    """Persist and retrieve reusable benchmark datasets."""

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> None:
        """Persist one benchmark dataset."""

        ...

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return one benchmark dataset by identifier."""

        ...

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return all benchmark datasets in insertion order."""

        ...
