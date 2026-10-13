"""Deterministic evaluator checking outputs against a JSON Schema."""

from pydantic import JsonValue

from azathoth.evaluation.json_schema import (
    json_schema_validator,
    json_schema_violations,
)
from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.evaluation.protocols import EvaluatorMetadata

MAX_RECORDED_VIOLATIONS = 10


class SchemaEvaluator:
    """Evaluate outputs by validating them against the expected JSON Schema."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="json-schema",
            description="Validate actual values against the expected JSON Schema.",
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
        """Validate one actual value against the expected outcome's schema.

        The expected value is the schema. Failures record the total violation
        count and up to ten violations, each with its JSON path and message,
        ordered by path and then message.
        """

        violations = json_schema_violations(
            json_schema_validator(expected.value),
            actual,
        )

        evidence = [
            EvaluationEvidence(
                label="schema",
                value=expected.value,
            ),
            EvaluationEvidence(
                label="actual",
                value=actual,
            ),
        ]

        if not violations:
            return EvaluationResult(
                evaluator_name=self.metadata.name,
                evaluator_version=self.metadata.version,
                score=1.0,
                threshold=1.0,
                status=EvaluationStatus.PASSED,
                reason="Actual value conformed to the expected schema.",
                evidence=tuple(evidence),
            )

        evidence.extend(
            (
                EvaluationEvidence(
                    label="violation_count",
                    value=len(violations),
                ),
                EvaluationEvidence(
                    label="violations",
                    value=[
                        {
                            "path": violation.path,
                            "message": violation.message,
                        }
                        for violation in violations[:MAX_RECORDED_VIOLATIONS]
                    ],
                ),
            )
        )

        noun = "violation" if len(violations) == 1 else "violations"

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=0.0,
            threshold=1.0,
            status=EvaluationStatus.FAILED,
            reason=(
                f"Actual value did not conform to the expected schema ({len(violations)} {noun})."
            ),
            evidence=tuple(evidence),
        )
