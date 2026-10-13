"""Tests for routing expected outcomes to comparison evaluators."""

import asyncio

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
    OutcomeEvaluator,
    UnsupportedComparisonError,
    default_comparison_evaluators,
)


def evaluate(
    comparison: OutcomeComparison,
    expected: JsonValue,
    actual: JsonValue,
    *,
    evaluator: OutcomeEvaluator | None = None,
) -> EvaluationResult:
    """Evaluate one actual value through the outcome evaluator."""

    return asyncio.run(
        (evaluator if evaluator is not None else OutcomeEvaluator()).evaluate(
            ExpectedOutcome(
                description="Routed expectation",
                value=expected,
                comparison=comparison,
            ),
            actual,
        )
    )


def test_default_evaluators_cover_deterministic_comparisons() -> None:
    assert set(default_comparison_evaluators()) == {
        OutcomeComparison.EXACT,
        OutcomeComparison.NORMALIZED,
        OutcomeComparison.SCHEMA,
    }


@pytest.mark.parametrize(
    ("comparison", "supported"),
    (
        (OutcomeComparison.EXACT, True),
        (OutcomeComparison.NORMALIZED, True),
        (OutcomeComparison.SCHEMA, True),
        (OutcomeComparison.SEMANTIC, False),
    ),
)
def test_outcome_evaluator_reports_supported_comparisons(
    comparison: OutcomeComparison,
    supported: bool,
) -> None:
    assert OutcomeEvaluator().supports(comparison) is supported


def test_exact_outcomes_are_judged_exactly() -> None:
    result = evaluate(OutcomeComparison.EXACT, "refund", "Refund")

    assert result.evaluator_name == "exact-match"
    assert not result.passed


def test_normalized_outcomes_are_judged_after_normalization() -> None:
    result = evaluate(OutcomeComparison.NORMALIZED, "refund", " Refund\n")

    assert result.evaluator_name == "normalized-match"
    assert result.passed


def test_schema_outcomes_are_judged_against_schema() -> None:
    result = evaluate(
        OutcomeComparison.SCHEMA,
        {"type": "string", "enum": ["refund", "billing"]},
        "refund",
    )

    assert result.evaluator_name == "json-schema"
    assert result.passed


def test_semantic_outcomes_are_rejected() -> None:
    with pytest.raises(
        UnsupportedComparisonError,
        match="^Expected outcome uses comparison 'semantic', which is not supported yet.$",
    ) as raised:
        evaluate(OutcomeComparison.SEMANTIC, "a refund request", "refund please")

    assert raised.value.comparison is OutcomeComparison.SEMANTIC


def test_unsupported_comparison_is_a_value_error() -> None:
    assert issubclass(UnsupportedComparisonError, ValueError)


def test_require_supported_names_subject() -> None:
    with pytest.raises(
        UnsupportedComparisonError,
        match="^Benchmark case 7 uses comparison 'semantic', which is not supported yet.$",
    ):
        OutcomeEvaluator().require_supported(
            OutcomeComparison.SEMANTIC,
            subject="Benchmark case 7",
        )


def test_require_supported_accepts_supported_comparison() -> None:
    OutcomeEvaluator().require_supported(OutcomeComparison.NORMALIZED)


class AlwaysPassingEvaluator:
    """Pass every output, recording the outcomes it judged."""

    def __init__(self) -> None:
        self.judged: list[ExpectedOutcome] = []

    @property
    def metadata(self) -> EvaluatorMetadata:
        return EvaluatorMetadata(
            name="always-pass",
            description="Pass every output.",
        )

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        self.judged.append(expected)

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            score=1.0,
            status=EvaluationStatus.PASSED,
            reason="Always passes.",
        )


def test_outcome_evaluator_accepts_custom_evaluators() -> None:
    semantic = AlwaysPassingEvaluator()

    evaluator = OutcomeEvaluator(
        {
            OutcomeComparison.SEMANTIC: semantic,
        }
    )

    result = evaluate(
        OutcomeComparison.SEMANTIC,
        "a refund request",
        "refund please",
        evaluator=evaluator,
    )

    assert result.evaluator_name == "always-pass"
    assert len(semantic.judged) == 1
    assert not evaluator.supports(OutcomeComparison.EXACT)


def test_outcome_evaluator_identity() -> None:
    assert OutcomeEvaluator().metadata.name == "outcome"
    assert OutcomeEvaluator().metadata.version == "1.0.0"
