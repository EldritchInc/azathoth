"""Tests for benchmark execution with semantically judged cases."""

import asyncio
from uuid import UUID

import pytest

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    JudgeRotation,
    OutcomeComparison,
    OutcomeEvaluator,
    SemanticEvaluator,
    SemanticJudgingError,
    default_comparison_evaluators,
    judge_calls_cost_usd,
)
from azathoth.workflows import (
    RUN_FAILURE_EVALUATOR_NAME,
    WorkflowBenchmarkComparisonEntry,
    WorkflowBenchmarkRunner,
    WorkflowBenchmarkScorer,
    WorkflowRunner,
    WorkflowScoringPolicy,
)
from tests.evaluation.test_semantic import (
    GAMMA,
    PASS_REPLY,
    ScriptedJudgeModel,
)
from tests.workflows.test_benchmark_run_failures import (
    FAILING_CASE_ID,
    SelectiveFailureExecutor,
    create_single_step_candidate,
    create_tolerant_candidate,
)

DATASET_ID = UUID("d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1")

EXACT_CASE_ID = UUID("a2222222-2222-4222-8222-222222222222")

SEMANTIC_CASE_ID = UUID("e3e3e3e3-e3e3-4e3e-8e3e-e3e3e3e3e3e3")

JUDGE_COST_USD = 0.5


def create_dataset(
    *,
    semantic_case_id: UUID = SEMANTIC_CASE_ID,
) -> BenchmarkDataset:
    """Create a benchmark with one exact case and one semantic case."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="semantic-benchmark",
        description="One exact and one semantic case.",
        cases=(
            BenchmarkCase(
                id=EXACT_CASE_ID,
                input="first",
                expected=ExpectedOutcome(
                    description="The answer.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            BenchmarkCase(
                id=semantic_case_id,
                input="second",
                expected=ExpectedOutcome(
                    description="A favorable sentiment label.",
                    value="good",
                    comparison=OutcomeComparison.SEMANTIC,
                ),
            ),
        ),
    )


def create_runner(
    judge: ScriptedJudgeModel,
) -> WorkflowBenchmarkRunner:
    """Create a benchmark runner with one semantic judge."""

    return WorkflowBenchmarkRunner(
        runner=WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ),
        evaluator=OutcomeEvaluator(
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
        ),
    )


def test_benchmark_judges_only_semantic_cases_with_the_judge() -> None:
    judge = ScriptedJudgeModel(
        PASS_REPLY,
        cost_usd=JUDGE_COST_USD,
    )

    result = asyncio.run(
        create_runner(judge).run(
            create_dataset(),
            create_tolerant_candidate,
        )
    )

    assert len(judge.prompts) == 1
    assert tuple(case.evaluation.evaluator_name for case in result.cases) == (
        "exact-match",
        "semantic-judge",
    )
    assert result.cases_passed == 2
    assert tuple(
        (tally.comparison, tally.cases_passed, tally.cases_run)
        for tally in result.comparison_tallies
    ) == (
        (OutcomeComparison.EXACT, 1, 1),
        (OutcomeComparison.SEMANTIC, 1, 1),
    )


def test_judge_cost_is_recorded_but_never_charged_to_the_candidate() -> None:
    result = asyncio.run(
        create_runner(
            ScriptedJudgeModel(
                PASS_REPLY,
                cost_usd=JUDGE_COST_USD,
            )
        ).run(
            create_dataset(),
            create_tolerant_candidate,
        )
    )

    semantic_case = result.cases[1]

    assert judge_calls_cost_usd(semantic_case.evaluation) == pytest.approx(JUDGE_COST_USD)
    assert result.total_cost_usd == 0.0

    scorecard = (
        WorkflowBenchmarkScorer(
            policy=WorkflowScoringPolicy(
                target_latency_seconds=10.0,
                target_cost_usd=0.01,
            ),
        )
        .score(
            WorkflowBenchmarkComparisonEntry(
                name="tolerant",
                result=result,
            )
        )
        .scorecard
    )

    assert scorecard.cost_score == 1.0


def test_failed_run_on_semantic_case_never_calls_the_judge() -> None:
    judge = ScriptedJudgeModel()

    result = asyncio.run(
        create_runner(judge).run(
            create_dataset(
                semantic_case_id=FAILING_CASE_ID,
            ),
            create_single_step_candidate,
        )
    )

    assert judge.prompts == []
    assert result.cases[1].evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME
    assert result.run_failures == 1


def test_judging_failure_aborts_the_benchmark() -> None:
    with pytest.raises(
        SemanticJudgingError,
        match="^Semantic judging failed with every judge: ",
    ):
        asyncio.run(
            create_runner(
                ScriptedJudgeModel(RuntimeError("down")),
            ).run(
                create_dataset(),
                create_tolerant_candidate,
            )
        )
