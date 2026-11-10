"""Persistence contracts for reusable benchmark datasets."""

from typing import Protocol
from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision
from azathoth.revisions import Author, LineageRecord, SavedRevision


class BenchmarkRepository(Protocol):
    """Persist and retrieve revisioned benchmark datasets.

    The dataset ID is a lineage. Saving never replaces anything: each save
    appends the next revision under the dataset's ID, and the latest
    revision is the benchmark's current dataset. A save identical to the
    revision it builds on appends nothing.
    """

    def save(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision, and return it."""

        ...

    def save_revision(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[BenchmarkDatasetRevision]:
        """Append one dataset on the revision it builds on, unless it is identical to it.

        It builds on the revision whose revision digest is `based_on`, or on
        the latest without one (ADR 0122).

        Raises:
            BaseRevisionError: No revision of the benchmark has that digest.
        """

        ...

    def lineage(
        self,
        dataset_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a benchmark, oldest first."""

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
