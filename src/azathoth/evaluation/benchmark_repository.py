"""Persistence contracts for reusable benchmark datasets."""

from typing import Protocol
from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision


class BenchmarkRepository(Protocol):
    """Persist and retrieve revisioned benchmark datasets.

    The dataset ID is a lineage. Saving never replaces anything: each save
    appends the next revision under the dataset's ID, and the latest
    revision is the benchmark's current dataset.
    """

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision."""

        ...

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return a benchmark's latest dataset."""

        ...

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return every benchmark's latest dataset in first-import order."""

        ...

    def latest_revision(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDatasetRevision | None:
        """Return a benchmark's latest revision."""

        ...

    def revision(
        self,
        dataset_id: UUID,
        number: int,
    ) -> BenchmarkDatasetRevision | None:
        """Return one numbered revision of a benchmark."""

        ...

    def revisions(
        self,
        dataset_id: UUID,
    ) -> tuple[BenchmarkDatasetRevision, ...]:
        """Return every revision of a benchmark, oldest first."""

        ...
