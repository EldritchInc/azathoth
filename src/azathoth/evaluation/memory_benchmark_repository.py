"""Deterministic in-memory persistence for benchmark datasets."""

from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_repository import BenchmarkRepository
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision
from azathoth.revisions import (
    Author,
    Lineage,
    LineageRecord,
    RevisionKind,
    SavedRevision,
    base_record,
    child_record,
    content_digest,
)


class InMemoryBenchmarkRepository:
    """Store revisioned benchmark datasets in import order."""

    def __init__(
        self,
    ) -> None:
        self._revisions: dict[
            UUID,
            list[BenchmarkDatasetRevision],
        ] = {}

        self._lineage: dict[
            UUID,
            list[LineageRecord],
        ] = {}

    def save(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision, and return it."""

        return self.save_revision(
            dataset,
            author=author,
            based_on=based_on,
        ).revision

    def save_revision(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[BenchmarkDatasetRevision]:
        """Append one dataset on the revision it builds on, unless it is identical to it.

        Raises:
            BaseRevisionError: No revision of the benchmark has the digest
                `based_on`.
        """

        lineage = Lineage(kind=RevisionKind.BENCHMARK, id=dataset.id)

        records = self._lineage.setdefault(dataset.id, [])
        history = self._revisions.setdefault(dataset.id, [])

        parent = base_record(records, lineage, based_on)

        if parent is not None:
            built_on = history[parent.number - 1]

            if built_on.content_digest == content_digest(dataset):
                return SavedRevision(revision=built_on, lineage=parent, created=False)

        revision = BenchmarkDatasetRevision.create(
            dataset,
            number=len(history) + 1,
        )

        record = child_record(
            lineage,
            number=revision.number,
            content_digest=revision.content_digest,
            parent=parent,
            author=author,
        )

        history.append(revision)
        records.append(record)

        return SavedRevision(revision=revision, lineage=record, created=True)

    def lineage(
        self,
        dataset_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a benchmark, oldest first."""

        return tuple(self._lineage.get(dataset_id, ()))

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return a benchmark's latest dataset."""

        revision = self.latest_revision(dataset_id)

        return revision.dataset if revision is not None else None

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return every benchmark's latest dataset in first-import order."""

        return tuple(history[-1].dataset for history in self._revisions.values())

    def latest_revision(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDatasetRevision | None:
        """Return a benchmark's latest revision."""

        history = self._revisions.get(dataset_id)

        return history[-1] if history else None

    def revision(
        self,
        dataset_id: UUID,
        number: int,
    ) -> BenchmarkDatasetRevision | None:
        """Return one numbered revision of a benchmark."""

        return next(
            (
                revision
                for revision in self._revisions.get(dataset_id, ())
                if revision.number == number
            ),
            None,
        )

    def revisions(
        self,
        dataset_id: UUID,
    ) -> tuple[BenchmarkDatasetRevision, ...]:
        """Return every revision of a benchmark, oldest first."""

        return tuple(self._revisions.get(dataset_id, ()))


def require_benchmark_repository(
    repository: BenchmarkRepository,
) -> BenchmarkRepository:
    """Return a repository after static protocol validation."""

    return repository
