"""Tests for rejecting optimization of workflows without declared results."""

import asyncio

import pytest

from azathoth.cli import optimize_configured_workflow
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.runtime import AzathothRuntime
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowResultError,
    WorkflowScoringPolicy,
)
from tests.cli.test_optimization import (
    WORKFLOW_ID,
    create_models,
    create_portfolio,
    create_registry,
    create_workflow,
)


def test_optimization_rejects_workflow_without_result_before_generating_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(
                create_workflow().model_copy(
                    update={
                        "result": None,
                    }
                ),
            ),
        ),
        models=create_models(),
        portfolio=create_portfolio(),
        language_models=create_registry(),
    )

    def fail_generation(*args: object, **kwargs: object) -> object:
        raise AssertionError("Candidates must not be generated.")

    monkeypatch.setattr(
        runtime,
        "generate_workflow_candidate",
        fail_generation,
    )

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow {WORKFLOW_ID} does not declare a result.$",
    ):
        asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
                expected_outcome=ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.01,
                ),
                max_generations=1,
            )
        )
