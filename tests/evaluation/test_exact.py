import asyncio

from pydantic import JsonValue

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)


def evaluate(
    expected: JsonValue,
    actual: JsonValue,
) -> EvaluationResult:
    """Evaluate one actual value against one exact expectation."""

    return asyncio.run(
        ExactMatchEvaluator().evaluate(
            ExpectedOutcome(
                description="Exact expectation",
                value=expected,
                comparison=OutcomeComparison.EXACT,
            ),
            actual,
        )
    )


def test_exact_match_passes() -> None:
    evaluator = ExactMatchEvaluator()

    expected = ExpectedOutcome(
        description="Intent classification",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluator.evaluate(
            expected,
            "duplicate_charge",
        )
    )

    assert result.passed
    assert result.score == 1.0


def test_exact_match_fails() -> None:
    evaluator = ExactMatchEvaluator()

    expected = ExpectedOutcome(
        description="Intent classification",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluator.evaluate(
            expected,
            "refund",
        )
    )

    assert not result.passed
    assert result.score == 0.0


def test_exact_match_handles_nested_json() -> None:
    evaluator = ExactMatchEvaluator()

    expected = ExpectedOutcome(
        description="Nested response",
        value={
            "intent": "duplicate_charge",
            "confidence": 0.97,
        },
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluator.evaluate(
            expected,
            {
                "intent": "duplicate_charge",
                "confidence": 0.97,
            },
        )
    )

    assert result.passed


def test_exact_match_detects_nested_difference() -> None:
    evaluator = ExactMatchEvaluator()

    expected = ExpectedOutcome(
        description="Nested response",
        value={
            "intent": "duplicate_charge",
            "confidence": 0.97,
        },
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluator.evaluate(
            expected,
            {
                "intent": "refund",
                "confidence": 0.97,
            },
        )
    )

    assert not result.passed


def test_exact_match_records_evaluator_identity() -> None:
    evaluator = ExactMatchEvaluator()

    expected = ExpectedOutcome(
        description="Identity",
        value="x",
        comparison=OutcomeComparison.EXACT,
    )

    result = asyncio.run(
        evaluator.evaluate(
            expected,
            "x",
        )
    )

    assert result.evaluator_name == "exact-match"
    assert result.evaluator_version == "2.0.0"


def test_exact_match_rejects_boolean_for_number() -> None:
    result = evaluate(1, True)

    assert not result.passed
    assert result.reason == "Actual value did not exactly match expected value at $."
    assert result.evidence == (
        EvaluationEvidence(label="expected", value=1),
        EvaluationEvidence(label="actual", value=True),
        EvaluationEvidence(label="difference_path", value="$"),
        EvaluationEvidence(label="expected_type", value="number"),
        EvaluationEvidence(label="actual_type", value="boolean"),
    )


def test_exact_match_rejects_number_for_boolean() -> None:
    assert not evaluate(False, 0).passed


def test_exact_match_accepts_integer_and_decimal_forms_of_one_number() -> None:
    result = evaluate(1, 1.0)

    assert result.passed
    assert result.evidence == (
        EvaluationEvidence(label="expected", value=1),
        EvaluationEvidence(label="actual", value=1.0),
    )


def test_exact_match_reports_nested_difference_path_without_types() -> None:
    result = evaluate(
        {"intent": "duplicate_charge"},
        {"intent": "refund"},
    )

    assert result.reason == ("Actual value did not exactly match expected value at $.intent.")
    assert result.evidence[2:] == (EvaluationEvidence(label="difference_path", value="$.intent"),)


def test_exact_match_reports_nested_type_mismatch() -> None:
    result = evaluate(
        {"approved": True},
        {"approved": "true"},
    )

    assert not result.passed
    assert result.evidence[2:] == (
        EvaluationEvidence(label="difference_path", value="$.approved"),
        EvaluationEvidence(label="expected_type", value="boolean"),
        EvaluationEvidence(label="actual_type", value="string"),
    )
