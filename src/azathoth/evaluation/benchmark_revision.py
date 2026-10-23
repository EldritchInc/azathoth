"""Immutable revisions of reusable benchmark datasets."""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
)


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class BenchmarkDatasetRevision(BaseModel):
    """Record one import of a benchmark dataset under its dataset ID.

    The dataset ID is the lineage; every import appends the next revision
    number and nothing is ever replaced. Re-importing an earlier document
    appends a revision whose digest matches the earlier one.

    Datasets imported before revisions existed become revision 1 with no
    import time, because it was never recorded.
    """

    model_config = ConfigDict(frozen=True)

    dataset_id: UUID

    number: int = Field(
        ge=1,
    )

    dataset: BenchmarkDataset

    content_digest: str = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    imported_at: datetime | None = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def validate_dataset_identity(
        self,
    ) -> "BenchmarkDatasetRevision":
        """Require the dataset to belong to the revision's lineage."""

        if self.dataset.id != self.dataset_id:
            raise ValueError("Benchmark revision dataset must belong to its benchmark.")

        return self

    @classmethod
    def create(
        cls,
        dataset: BenchmarkDataset,
        *,
        number: int,
        imported_at: datetime | None = None,
    ) -> "BenchmarkDatasetRevision":
        """Return the revision recording one import of a dataset."""

        return cls(
            dataset_id=dataset.id,
            number=number,
            dataset=dataset,
            content_digest=content_digest(dataset),
            imported_at=imported_at if imported_at is not None else utc_now(),
        )


def earliest_identical_benchmark_revision(
    history: Iterable[BenchmarkDatasetRevision],
    revision: BenchmarkDatasetRevision,
) -> BenchmarkDatasetRevision | None:
    """Return the earliest other revision of the same dataset with the same content."""

    matches = sorted(
        (
            candidate
            for candidate in history
            if candidate.dataset_id == revision.dataset_id
            and candidate.number < revision.number
            and candidate.content_digest == revision.content_digest
        ),
        key=lambda candidate: candidate.number,
    )

    return matches[0] if matches else None
