"""Tests for evaluator protocols and metadata."""

import asyncio

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
)


class AlwaysPassEvaluator:
    """A test evaluator that always returns a passing result."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="always-pass",
            description="Return a passing result for protocol testing.",
            version="1.0.0",
        )
        self.received_expected: ExpectedOutcome | None = None
        self.received_actual: JsonValue = None

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        self.received_expected = expected
        self.received_actual = actual

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=1.0,
            threshold=1.0,
            status=EvaluationStatus.PASSED,
            reason="The test evaluator always passes.",
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


async def evaluate_output(
    evaluator: Evaluator,
    expected: ExpectedOutcome,
    actual: JsonValue,
) -> EvaluationResult:
    """Evaluate an output without depending on a concrete evaluator type."""

    return await evaluator.evaluate(expected, actual)


def test_evaluator_metadata_records_identity() -> None:
    metadata = EvaluatorMetadata(
        name="exact-match",
        description="Compare expected and actual values for equality.",
        version="1.0.0",
    )

    assert metadata.name == "exact-match"
    assert metadata.version == "1.0.0"


def test_evaluator_metadata_is_immutable() -> None:
    metadata = EvaluatorMetadata(
        name="exact-match",
        description="Compare expected and actual values for equality.",
    )

    with pytest.raises(ValidationError):
        metadata.version = "2.0.0"


def test_evaluator_metadata_rejects_empty_identity_fields() -> None:
    with pytest.raises(ValidationError):
        EvaluatorMetadata(
            name="",
            description="Compare values.",
        )

    with pytest.raises(ValidationError):
        EvaluatorMetadata(
            name="exact-match",
            description="",
        )


def test_evaluator_can_be_invoked_through_common_protocol() -> None:
    evaluator = AlwaysPassEvaluator()
    expected = ExpectedOutcome(
        description="The request has the expected category.",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluate_output(
            evaluator=evaluator,
            expected=expected,
            actual="duplicate_charge",
        )
    )

    assert result.passed is True
    assert result.evaluator_name == "always-pass"
    assert result.evaluator_version == "1.0.0"
    assert result.evidence == (
        EvaluationEvidence(
            label="expected",
            value="duplicate_charge",
        ),
        EvaluationEvidence(
            label="actual",
            value="duplicate_charge",
        ),
    )


def test_evaluator_receives_expected_outcome_and_actual_value() -> None:
    evaluator = AlwaysPassEvaluator()
    expected = ExpectedOutcome(
        description="The result contains a duplicate-charge category.",
        value={
            "category": "duplicate_charge",
        },
        comparison=OutcomeComparison.EXACT,
    )
    actual: JsonValue = {
        "category": "duplicate_charge",
    }

    asyncio.run(
        evaluate_output(
            evaluator=evaluator,
            expected=expected,
            actual=actual,
        )
    )

    assert evaluator.received_expected == expected
    assert evaluator.received_actual == actual
