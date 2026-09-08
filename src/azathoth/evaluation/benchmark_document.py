"""JSON document serialization for durable benchmark datasets."""

from pydantic import ValidationError

from azathoth.evaluation.benchmark import BenchmarkDataset


class BenchmarkDocumentError(ValueError):
    """Raised when a benchmark document cannot be reconstructed."""


def encode_benchmark_document(
    dataset: BenchmarkDataset,
) -> str:
    """Serialize one benchmark dataset as a readable JSON document."""

    return dataset.model_dump_json(
        indent=2,
    )


def decode_benchmark_document(
    document: str,
) -> BenchmarkDataset:
    """Reconstruct one benchmark dataset from a JSON document."""

    try:
        return BenchmarkDataset.model_validate_json(
            document,
        )
    except ValidationError as exc:
        raise BenchmarkDocumentError("Benchmark document is not a valid BenchmarkDataset.") from exc
