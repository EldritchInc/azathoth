"""Deterministic in-memory persistence for benchmark datasets."""

from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_repository import BenchmarkRepository
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision


class InMemoryBenchmarkRepository:
    """Store revisioned benchmark datasets in import order."""

    def __init__(
        self,
    ) -> None:
        self._revisions: dict[
            UUID,
            list[BenchmarkDatasetRevision],
        ] = {}

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision."""

        history = self._revisions.setdefault(
            dataset.id,
            [],
        )

        revision = BenchmarkDatasetRevision.create(
            dataset,
            number=len(history) + 1,
        )

        history.append(revision)

        return revision

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
