import asyncio

from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
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
    assert result.evaluator_version == "1.0.0"
