"""Deterministic exact-value evaluator."""

from pydantic import JsonValue

from azathoth.evaluation.json_equality import first_json_difference
from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.evaluation.protocols import EvaluatorMetadata


class ExactMatchEvaluator:
    """Evaluate outputs using type-strict JSON equality."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="exact-match",
            description="Compare expected and actual values using type-strict JSON equality.",
            version="2.0.0",
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Compare two JSON values for type-strict equality.

        Booleans never equal numbers, numbers compare by value, arrays compare
        in order, and objects require identical keys. A failure records where
        the values first differ and the JSON types found there.
        """

        difference = first_json_difference(
            expected.value,
            actual,
        )

        evidence = [
            EvaluationEvidence(
                label="expected",
                value=expected.value,
            ),
            EvaluationEvidence(
                label="actual",
                value=actual,
            ),
        ]

        if difference is None:
            return EvaluationResult(
                evaluator_name=self.metadata.name,
                evaluator_version=self.metadata.version,
                score=1.0,
                threshold=1.0,
                status=EvaluationStatus.PASSED,
                reason="Actual value exactly matched expected value.",
                evidence=tuple(evidence),
            )

        evidence.append(
            EvaluationEvidence(
                label="difference_path",
                value=difference.path,
            )
        )

        if difference.expected_type != difference.actual_type:
            evidence.extend(
                (
                    EvaluationEvidence(
                        label="expected_type",
                        value=difference.expected_type,
                    ),
                    EvaluationEvidence(
                        label="actual_type",
                        value=difference.actual_type,
                    ),
                )
            )

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=0.0,
            threshold=1.0,
            status=EvaluationStatus.FAILED,
            reason=f"Actual value did not exactly match expected value at {difference.path}.",
            evidence=tuple(evidence),
        )
