"""Deterministic exact-value evaluator."""

from pydantic import JsonValue

from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.evaluation.protocols import EvaluatorMetadata


class ExactMatchEvaluator:
    """Evaluate outputs using strict equality."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="exact-match",
            description="Compare expected and actual values using equality.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Compare two JSON values for exact equality."""

        passed = expected.value == actual

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=1.0 if passed else 0.0,
            threshold=1.0,
            status=(EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED),
            reason=(
                "Actual value exactly matched expected value."
                if passed
                else "Actual value did not exactly match expected value."
            ),
            evidence=(
                EvaluationEvidence(
                    label="expected",
                    value=expected.value,
                ),
                EvaluationEvidence(
                    label="actual",
                    value=actual,
                ),
            ),
        )
