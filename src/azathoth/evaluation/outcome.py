"""Evaluator that routes each expected outcome by its comparison."""

from collections.abc import Mapping

from pydantic import JsonValue

from azathoth.evaluation.exact import ExactMatchEvaluator
from azathoth.evaluation.models import (
    EvaluationResult,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.evaluation.normalized import NormalizedMatchEvaluator
from azathoth.evaluation.protocols import Evaluator, EvaluatorMetadata
from azathoth.evaluation.schema import SchemaEvaluator


class UnsupportedComparisonError(ValueError):
    """Raised when no evaluator is available for an outcome comparison."""

    def __init__(
        self,
        comparison: OutcomeComparison,
        *,
        subject: str = "Expected outcome",
    ) -> None:
        self.comparison = comparison
        self.subject = subject

        super().__init__(
            f"{subject} uses comparison {comparison.value!r}, which is not supported yet."
        )


def default_comparison_evaluators(
    *,
    semantic: Evaluator | None = None,
) -> dict[OutcomeComparison, Evaluator]:
    """Return the built-in evaluator for every supported comparison.

    Exact, normalized, and schema comparisons are always supported. Semantic
    comparisons need language-model judges, so they are supported only when a
    semantic evaluator is supplied; without one they stay unsupported and are
    rejected before any work starts.
    """

    evaluators: dict[OutcomeComparison, Evaluator] = {
        OutcomeComparison.EXACT: ExactMatchEvaluator(),
        OutcomeComparison.NORMALIZED: NormalizedMatchEvaluator(),
        OutcomeComparison.SCHEMA: SchemaEvaluator(),
    }

    if semantic is not None:
        evaluators[OutcomeComparison.SEMANTIC] = semantic

    return evaluators


class OutcomeEvaluator:
    """Evaluate each expected outcome with the evaluator for its comparison.

    Results are produced by the delegated evaluator, so recorded evaluations
    name the evaluator that actually judged the output. Comparisons without an
    evaluator are rejected rather than judged by a substitute.
    """

    def __init__(
        self,
        evaluators: Mapping[OutcomeComparison, Evaluator] | None = None,
    ) -> None:
        self._evaluators = dict(
            evaluators if evaluators is not None else default_comparison_evaluators()
        )

        self._metadata = EvaluatorMetadata(
            name="outcome",
            description="Evaluate each expected outcome with the evaluator for its comparison.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    def supports(
        self,
        comparison: OutcomeComparison,
    ) -> bool:
        """Return whether an evaluator is available for one comparison."""

        return comparison in self._evaluators

    def require_supported(
        self,
        comparison: OutcomeComparison,
        *,
        subject: str = "Expected outcome",
    ) -> None:
        """Reject one comparison that has no evaluator.

        Raises:
            UnsupportedComparisonError: No evaluator handles the comparison.
        """

        if not self.supports(comparison):
            raise UnsupportedComparisonError(
                comparison,
                subject=subject,
            )

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Evaluate one actual value with the evaluator for its comparison."""

        self.require_supported(expected.comparison)

        return await self._evaluators[expected.comparison].evaluate(
            expected,
            actual,
        )
