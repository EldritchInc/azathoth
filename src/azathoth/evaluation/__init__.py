"""Evaluation domain models and interfaces."""

from azathoth.evaluation.benchmark import BenchmarkCase, BenchmarkDataset
from azathoth.evaluation.exact import ExactMatchEvaluator
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
    "BenchmarkDataset",
    "EvaluationEvidence",
    "EvaluationResult",
    "EvaluationStatus",
    "Evaluator",
    "EvaluatorMetadata",
    "ExactMatchEvaluator",
    "ExpectedOutcome",
    "OutcomeComparison",
]
