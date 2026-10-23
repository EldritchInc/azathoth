"""Tests for comparison-aware configured workflow optimization."""

import asyncio

import pytest

from azathoth.cli import optimize_configured_workflow
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
    UnsupportedComparisonError,
)
from azathoth.workflows import WorkflowScoringPolicy
from tests.cli.test_optimization import (
    WORKFLOW_ID,
    case_id,
    create_benchmark,
    create_runtime,
)

SCORING_POLICY = WorkflowScoringPolicy(
    target_latency_seconds=60.0,
    target_cost_usd=0.01,
)


def test_optimization_judges_normalized_expectations_after_normalization() -> None:
    session = asyncio.run(
        optimize_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success in any letter case.",
                    value="  SUCCESS ",
                    comparison=OutcomeComparison.NORMALIZED,
                ),
            ),
            scoring_policy=SCORING_POLICY,
            max_generations=1,
        )
    )

    evidence = session.generations[0].previous_experiment.evidence

    assert len(evidence) == 1
    assert evidence[0].scorecard.quality_score == 1.0


def test_optimization_still_judges_exact_expectations_exactly() -> None:
    session = asyncio.run(
        optimize_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns uppercase success.",
                    value="SUCCESS",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=SCORING_POLICY,
            max_generations=1,
        )
    )

    evidence = session.generations[0].previous_experiment.evidence

    assert evidence[0].scorecard.quality_score == 0.0


def test_optimization_rejects_unsupported_comparison_before_generating_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = create_runtime()

    def fail_generation(*args: object, **kwargs: object) -> object:
        raise AssertionError("Candidates must not be generated.")

    monkeypatch.setattr(
        runtime,
        "generate_workflow_candidate",
        fail_generation,
    )

    with pytest.raises(
        UnsupportedComparisonError,
        match=(
            f"^Benchmark case {case_id(1)} uses comparison 'semantic', which is not supported yet.$"
        ),
    ):
        asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
                dataset=create_benchmark(
                    ExpectedOutcome(
                        description="Workflow returns a success message.",
                        value="It worked.",
                        comparison=OutcomeComparison.SEMANTIC,
                    ),
                ),
                scoring_policy=SCORING_POLICY,
                max_generations=1,
            )
        )
