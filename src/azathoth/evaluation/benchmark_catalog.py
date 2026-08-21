"""Immutable catalogs of reusable benchmark datasets."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.evaluation.benchmark import BenchmarkDataset


class BenchmarkCatalog(BaseModel):
    """Immutable inventory of configured benchmark datasets."""

    model_config = ConfigDict(
        frozen=True,
    )

    datasets: tuple[
        BenchmarkDataset,
        ...,
    ] = ()

    @property
    def identifiers(
        self,
    ) -> tuple[UUID, ...]:
        """Return dataset identifiers in catalog order."""

        return tuple(dataset.id for dataset in self.datasets)

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return one benchmark dataset by identifier."""

        return next(
            (dataset for dataset in self.datasets if dataset.id == dataset_id),
            None,
        )
