"""Evaluation domain models and interfaces."""

from azathoth.evaluation.benchmark import BenchmarkCase, BenchmarkDataset
from azathoth.evaluation.benchmark_catalog import BenchmarkCatalog
from azathoth.evaluation.benchmark_catalog_loader import BenchmarkCatalogLoader
from azathoth.evaluation.benchmark_repository import BenchmarkRepository
from azathoth.evaluation.exact import ExactMatchEvaluator
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
from azathoth.evaluation.protocols import Evaluator, EvaluatorMetadata

__all__ = [
    "BenchmarkCase",
    "BenchmarkCatalog",
    "BenchmarkCatalogLoader",
    "BenchmarkDataset",
    "BenchmarkRepository",
    "EvaluationEvidence",
    "EvaluationResult",
    "EvaluationStatus",
    "Evaluator",
    "EvaluatorMetadata",
    "ExactMatchEvaluator",
    "ExpectedOutcome",
    "InMemoryBenchmarkRepository",
    "OutcomeComparison",
    "require_benchmark_repository",
]
