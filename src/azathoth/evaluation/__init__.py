"""Evaluation domain models and interfaces."""

from azathoth.evaluation.benchmark import (
    BenchmarkCase,
    BenchmarkCaseConflictError,
    BenchmarkDataset,
)
from azathoth.evaluation.benchmark_catalog import BenchmarkCatalog
from azathoth.evaluation.benchmark_catalog_loader import BenchmarkCatalogLoader
from azathoth.evaluation.benchmark_document import (
    BenchmarkDocumentError,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.evaluation.benchmark_repository import BenchmarkRepository
from azathoth.evaluation.benchmark_revision import (
    BenchmarkDatasetRevision,
    earliest_identical_benchmark_revision,
)
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
from azathoth.evaluation.semantic import (
    SEMANTIC_EVALUATOR_NAME,
    SEMANTIC_EVALUATOR_VERSION,
    InvalidJudgeResponseError,
    SemanticEvaluator,
    SemanticJudgingError,
    judge_call_count,
    judge_calls_cost_usd,
    parse_judge_verdict,
    semantic_judge_prompt,
)
from azathoth.evaluation.sql_benchmark_repository import (
    BENCHMARK_TABLES,
    SqlBenchmarkRepository,
)
from azathoth.evaluation.sql_judge_repository import (
    JUDGE_ROTATION_TABLES,
    SqlJudgeRotationRepository,
)
from azathoth.evaluation.sqlite_benchmark_repository import (
    SQLiteBenchmarkRepository,
)
from azathoth.evaluation.sqlite_judge_repository import (
    SQLiteJudgeRotationRepository,
)

__all__ = [
    "BENCHMARK_TABLES",
    "JUDGE_ROTATION_TABLES",
    "SqlBenchmarkRepository",
    "SqlJudgeRotationRepository",
    "SEMANTIC_EVALUATOR_NAME",
    "SEMANTIC_EVALUATOR_VERSION",
    "BenchmarkCase",
    "BenchmarkCaseConflictError",
    "BenchmarkCatalog",
    "BenchmarkCatalogLoader",
    "BenchmarkDataset",
    "BenchmarkDatasetRevision",
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
    "InvalidJudgeResponseError",
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
    "SemanticEvaluator",
    "SemanticJudgingError",
    "UnsupportedComparisonError",
    "decode_benchmark_document",
    "default_comparison_evaluators",
    "earliest_identical_benchmark_revision",
    "encode_benchmark_document",
    "expectation_hash",
    "first_json_difference",
    "json_schema_validator",
    "json_schema_violations",
    "json_type_name",
    "judge_call_count",
    "judge_calls_cost_usd",
    "json_values_equal",
    "normalize_json_value",
    "normalize_text",
    "parse_judge_verdict",
    "require_benchmark_repository",
    "require_judge_rotation_repository",
    "semantic_judge_prompt",
]
