"""Tests for experiments judging declared workflow results."""

import asyncio
from dataclasses import replace

import pytest

from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowResultError,
    WorkflowValueBinding,
    WorkflowValueReference,
)
from tests.workflows.test_experiment_runner import (
    STEP_ID_A,
    STEP_ID_B,
    STRATEGY_ID_A,
    STRATEGY_ID_B,
    WORKFLOW_ID_A,
    WORKFLOW_ID_B,
    RecordingEvaluator,
    StaticStrategy,
    create_dataset,
    create_outcome_evaluator,
    create_scorer,
    create_workflow,
)


def test_experiment_judges_declared_result_rather_than_last_step() -> None:
    answer = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.01,
    )

    audit = StaticStrategy(
        strategy_id=STRATEGY_ID_B,
        output="audit-log",
        estimated_cost_usd=0.01,
    )

    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID_A,
            name="answer then audit",
            description="Answer first, then record an audit entry.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID_A,
                strategy=answer,
                outputs=(WorkflowValueBinding(name="answer"),),
            ),
            WorkflowCandidateStep(
                id=STEP_ID_B,
                strategy=audit,
                depends_on=(STEP_ID_A,),
                outputs=(WorkflowValueBinding(name="audit"),),
            ),
        ),
        result=WorkflowValueReference(
            producer_step_id=STEP_ID_A,
            name="answer",
        ),
    )

    evaluator = RecordingEvaluator()

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
        ).run(
            workflows=(candidate,),
            dataset=create_dataset(),
        )
    )

    assert audit.calls == 1
    assert evaluator.actual_values == ["success"]
    assert result.winner.quality_score == 1.0


def test_experiment_rejects_candidate_without_result_before_executing_any() -> None:
    first = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.01,
    )

    second = StaticStrategy(
        strategy_id=STRATEGY_ID_B,
        output="success",
        estimated_cost_usd=0.01,
    )

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=first,
            name="declared",
        ),
        replace(
            create_workflow(
                workflow_id=WORKFLOW_ID_B,
                step_id=STEP_ID_B,
                strategy=second,
                name="undeclared",
            ),
            result=None,
        ),
    )

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow {WORKFLOW_ID_B} does not declare a result.$",
    ):
        asyncio.run(
            WorkflowExperimentRunner(
                scorer=create_scorer(),
                evaluator=create_outcome_evaluator(RecordingEvaluator()),
            ).run(
                workflows=workflows,
                dataset=create_dataset(),
            )
        )

    assert first.calls == 0
    assert second.calls == 0
