"""Evaluation domain models and interfaces."""

from azathoth.evaluation.benchmark import BenchmarkCase, BenchmarkDataset
from azathoth.evaluation.benchmark_catalog import BenchmarkCatalog
from azathoth.evaluation.benchmark_catalog_loader import BenchmarkCatalogLoader
from azathoth.evaluation.benchmark_document import (
    BenchmarkDocumentError,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.evaluation.benchmark_repository import BenchmarkRepository
from azathoth.evaluation.exact import ExactMatchEvaluator
from azathoth.evaluation.json_equality import (
    JsonDifference,
    first_json_difference,
    json_type_name,
    json_values_equal,
)
from azathoth.evaluation.json_schema import (
    JsonSchemaViolation,
    json_schema_validator,
    json_schema_violations,
)
from azathoth.evaluation.memory_benchmark_repository import (
    InMemoryBenchmarkRepository,
    require_benchmark_repository,
)
from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.evaluation.normalized import (
    NormalizedMatchEvaluator,
    normalize_json_value,
    normalize_text,
)
from azathoth.evaluation.protocols import Evaluator, EvaluatorMetadata
from azathoth.evaluation.schema import SchemaEvaluator
from azathoth.evaluation.sqlite_benchmark_repository import (
    SQLiteBenchmarkRepository,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkCatalog",
    "BenchmarkCatalogLoader",
    "BenchmarkDataset",
    "BenchmarkDocumentError",
    "BenchmarkRepository",
    "EvaluationEvidence",
    "EvaluationResult",
    "EvaluationStatus",
    "Evaluator",
    "EvaluatorMetadata",
    "ExactMatchEvaluator",
    "ExpectedOutcome",
    "InMemoryBenchmarkRepository",
    "JsonDifference",
    "JsonSchemaViolation",
    "NormalizedMatchEvaluator",
    "OutcomeComparison",
    "SQLiteBenchmarkRepository",
    "SchemaEvaluator",
    "decode_benchmark_document",
    "encode_benchmark_document",
    "first_json_difference",
    "json_schema_validator",
    "json_schema_violations",
    "json_type_name",
    "json_values_equal",
    "normalize_json_value",
    "normalize_text",
    "require_benchmark_repository",
]
