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
from azathoth.evaluation.judge_repository import JudgeRotationRepository
from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
    expectation_hash,
)
from azathoth.evaluation.memory_benchmark_repository import (
    InMemoryBenchmarkRepository,
    require_benchmark_repository,
)
from azathoth.evaluation.memory_judge_repository import (
    InMemoryJudgeRotationRepository,
    require_judge_rotation_repository,
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
from azathoth.evaluation.outcome import (
    OutcomeEvaluator,
    UnsupportedComparisonError,
    default_comparison_evaluators,
)
from azathoth.evaluation.protocols import Evaluator, EvaluatorMetadata
from azathoth.evaluation.schema import SchemaEvaluator
from azathoth.evaluation.sqlite_benchmark_repository import (
    SQLiteBenchmarkRepository,
)
from azathoth.evaluation.sqlite_judge_repository import (
    SQLiteJudgeRotationRepository,
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
    "InMemoryJudgeRotationRepository",
    "JsonDifference",
    "JsonSchemaViolation",
    "JudgeEntry",
    "JudgeRotation",
    "JudgeRotationRepository",
    "NormalizedMatchEvaluator",
    "OutcomeComparison",
    "OutcomeEvaluator",
    "SQLiteBenchmarkRepository",
    "SQLiteJudgeRotationRepository",
    "SchemaEvaluator",
    "UnsupportedComparisonError",
    "decode_benchmark_document",
    "default_comparison_evaluators",
    "encode_benchmark_document",
    "expectation_hash",
    "first_json_difference",
    "json_schema_validator",
    "json_schema_violations",
    "json_type_name",
    "json_values_equal",
    "normalize_json_value",
    "normalize_text",
    "require_benchmark_repository",
    "require_judge_rotation_repository",
]
