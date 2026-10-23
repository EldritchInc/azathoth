"""Tests for routing semantic expectations to a semantic evaluator."""

import asyncio

import pytest

from azathoth.evaluation import (
    EvaluationResult,
    ExpectedOutcome,
    JudgeRotation,
    OutcomeComparison,
    OutcomeEvaluator,
    SemanticEvaluator,
    UnsupportedComparisonError,
    default_comparison_evaluators,
)
from tests.evaluation.test_semantic import (
    GAMMA,
    PASS_REPLY,
    ScriptedJudgeModel,
)


def create_outcome_evaluator(
    judge: ScriptedJudgeModel,
) -> OutcomeEvaluator:
    """Create an outcome evaluator whose semantic comparisons go to one judge."""

    return OutcomeEvaluator(
        default_comparison_evaluators(
            semantic=SemanticEvaluator(
                rotation=JudgeRotation(
                    entries=(GAMMA,),
                ),
                models={
                    GAMMA.identifier: judge,
                },
            ),
        )
    )


def evaluate(
    evaluator: OutcomeEvaluator,
    comparison: OutcomeComparison,
    expected: str,
    actual: str,
) -> EvaluationResult:
    """Evaluate one actual value through the outcome evaluator."""

    return asyncio.run(
        evaluator.evaluate(
            ExpectedOutcome(
                description="Routed expectation",
                value=expected,
                comparison=comparison,
            ),
            actual,
        )
    )


def test_defaults_include_semantic_only_when_supplied() -> None:
    semantic = SemanticEvaluator(
        rotation=JudgeRotation(
            entries=(GAMMA,),
        ),
        models={
            GAMMA.identifier: ScriptedJudgeModel(),
        },
    )

    evaluators = default_comparison_evaluators(
        semantic=semantic,
    )

    assert set(evaluators) == {
        OutcomeComparison.EXACT,
        OutcomeComparison.NORMALIZED,
        OutcomeComparison.SCHEMA,
        OutcomeComparison.SEMANTIC,
    }
    assert evaluators[OutcomeComparison.SEMANTIC] is semantic
    assert OutcomeComparison.SEMANTIC not in default_comparison_evaluators()


def test_outcome_evaluator_supports_semantic_with_judges() -> None:
    evaluator = create_outcome_evaluator(ScriptedJudgeModel())

    assert evaluator.supports(OutcomeComparison.SEMANTIC)

    evaluator.require_supported(
        OutcomeComparison.SEMANTIC,
        subject="Benchmark case",
    )


def test_outcome_evaluator_without_judges_still_rejects_semantic() -> None:
    with pytest.raises(
        UnsupportedComparisonError,
        match="^Expected outcome uses comparison 'semantic', which is not supported yet.$",
    ):
        evaluate(
            OutcomeEvaluator(),
            OutcomeComparison.SEMANTIC,
            "done",
            "It worked.",
        )


def test_semantic_expectation_is_judged_by_the_semantic_evaluator() -> None:
    judge = ScriptedJudgeModel(PASS_REPLY)

    evaluation = evaluate(
        create_outcome_evaluator(judge),
        OutcomeComparison.SEMANTIC,
        "done",
        "It worked.",
    )

    assert evaluation.evaluator_name == "semantic-judge"
    assert evaluation.passed
    assert len(judge.prompts) == 1


def test_deterministic_expectations_never_call_a_judge() -> None:
    judge = ScriptedJudgeModel()

    evaluator = create_outcome_evaluator(judge)

    exact = evaluate(
        evaluator,
        OutcomeComparison.EXACT,
        "done",
        "done",
    )
    normalized = evaluate(
        evaluator,
        OutcomeComparison.NORMALIZED,
        "DONE",
        " done ",
    )

    assert exact.evaluator_name == "exact-match"
    assert normalized.evaluator_name == "normalized-match"
    assert judge.prompts == []
