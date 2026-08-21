"""Reconstruct benchmark catalogs from durable repositories."""

from azathoth.evaluation.benchmark_catalog import BenchmarkCatalog
from azathoth.evaluation.benchmark_repository import BenchmarkRepository


class BenchmarkCatalogLoader:
    """Load immutable benchmark catalogs from repository state."""

    def __init__(
        self,
        repository: BenchmarkRepository,
    ) -> None:
        self._repository = repository

    def load_catalog(
        self,
    ) -> BenchmarkCatalog:
        """Reconstruct the configured benchmark catalog."""

        return BenchmarkCatalog(datasets=self._repository.datasets())
