"""Evaluation domain models and interfaces."""

from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.evaluation.protocols import Evaluator, EvaluatorMetadata

__all__ = [
    "EvaluationEvidence",
    "EvaluationResult",
    "EvaluationStatus",
    "Evaluator",
    "EvaluatorMetadata",
    "ExpectedOutcome",
    "OutcomeComparison",
]
