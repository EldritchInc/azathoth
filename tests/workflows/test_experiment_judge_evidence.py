"""Tests for judge calls and cost recorded beside workflow experiment evidence."""

import asyncio

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluatorMetadata,
    ExpectedOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
)
from tests.workflows.test_experiment_runner import (
    CASE_ID_A,
    CASE_ID_B,
    STEP_ID_A,
    STEP_ID_B,
    STRATEGY_ID_A,
    STRATEGY_ID_B,
    WORKFLOW_ID_A,
    WORKFLOW_ID_B,
    RecordingEvaluator,
    StaticStrategy,
    create_case,
    create_multi_case_dataset,
    create_outcome_evaluator,
    create_scorer,
    create_workflow,
)

JUDGE_COST_USD = 5.0


class JudgingEvaluator(RecordingEvaluator):
    """Score exact matches and record judge calls as a semantic judge would."""

    def __init__(
        self,
        *,
        calls_per_evaluation: int,
        cost_usd_per_call: float,
    ) -> None:
        super().__init__()
        self._metadata = EvaluatorMetadata(
            name="judging-evaluator",
            description="Record judge calls beside each evaluation.",
        )
        self._calls_per_evaluation = calls_per_evaluation
        self._cost_usd_per_call = cost_usd_per_call

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: object,
    ) -> EvaluationResult:
        """Evaluate one output and attach the judge calls it cost."""

        evaluation = await super().evaluate(
            expected,
            actual,
        )

        return EvaluationResult.model_validate(
            {
                **evaluation.model_dump(),
                "evidence": [
                    EvaluationEvidence(
                        label="judge_calls",
                        value=[
                            {
                                "status": "replied",
                                "usage": {
                                    "estimated_cost_usd": self._cost_usd_per_call,
                                },
                            }
                            for _ in range(self._calls_per_evaluation)
                        ],
                    ).model_dump(),
                ],
            }
        )


def create_workflows() -> tuple[WorkflowCandidate, ...]:
    """Create one cheap and one expensive candidate that both succeed."""

    return (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.01,
            ),
            name="cheap",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="success",
                estimated_cost_usd=0.20,
            ),
            name="expensive",
        ),
    )


def run_experiment(
    evaluator: RecordingEvaluator,
) -> WorkflowExperimentResult:
    """Run both candidates over two cases with one evaluator."""

    return asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
        ).run(
            workflows=create_workflows(),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="first",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="second",
                    expected_value="success",
                ),
            ),
        )
    )


def judged_experiment() -> WorkflowExperimentResult:
    """Run the experiment with two judge calls per evaluation."""

    return run_experiment(
        JudgingEvaluator(
            calls_per_evaluation=2,
            cost_usd_per_call=JUDGE_COST_USD,
        )
    )


def test_experiment_evidence_records_no_judging_by_default() -> None:
    result = run_experiment(RecordingEvaluator())

    for observation in result.evidence:
        assert observation.judge_calls == 0
        assert observation.judge_cost_usd == 0.0

    assert result.judge_calls == 0
    assert result.judge_cost_usd == 0.0


def test_experiment_evidence_records_each_candidates_judge_calls_and_cost() -> None:
    result = judged_experiment()

    for observation in result.evidence:
        assert observation.judge_calls == 4
        assert observation.judge_cost_usd == pytest.approx(4 * JUDGE_COST_USD)


def test_experiment_result_totals_judging_over_every_candidate() -> None:
    result = judged_experiment()

    assert result.judge_calls == 8
    assert result.judge_cost_usd == pytest.approx(8 * JUDGE_COST_USD)


def test_judge_cost_never_changes_candidate_scorecards() -> None:
    unjudged = run_experiment(RecordingEvaluator())
    judged = judged_experiment()

    assert tuple(observation.scorecard for observation in judged.evidence) == tuple(
        observation.scorecard for observation in unjudged.evidence
    )


def test_judge_cost_never_changes_candidate_ranking() -> None:
    unjudged = run_experiment(RecordingEvaluator())
    judged = judged_experiment()

    assert tuple(entry.scorecard for entry in judged.ranking.entries) == tuple(
        entry.scorecard for entry in unjudged.ranking.entries
    )


def test_judge_cost_far_above_target_leaves_the_cheap_candidate_full_cost_credit() -> None:
    judged = judged_experiment()

    cheap, expensive = judged.evidence

    assert cheap.judge_cost_usd > create_scorer().policy.target_cost_usd
    assert cheap.scorecard.cost_score == 1.0
    assert expensive.scorecard.cost_score == pytest.approx(0.5)


def test_experiment_evidence_rejects_negative_judge_calls() -> None:
    observation = judged_experiment().evidence[0]

    with pytest.raises(ValidationError):
        WorkflowExperimentEvidence(
            candidate_signature=observation.candidate_signature,
            scorecard=observation.scorecard,
            judge_calls=-1,
        )


def test_experiment_evidence_rejects_negative_judge_cost() -> None:
    observation = judged_experiment().evidence[0]

    with pytest.raises(ValidationError):
        WorkflowExperimentEvidence(
            candidate_signature=observation.candidate_signature,
            scorecard=observation.scorecard,
            judge_cost_usd=-0.01,
        )


def test_experiment_evidence_decodes_without_judge_fields() -> None:
    observation = judged_experiment().evidence[0]

    dumped = observation.model_dump(mode="json")

    del dumped["judge_calls"]
    del dumped["judge_cost_usd"]

    decoded = WorkflowExperimentEvidence.model_validate(dumped)

    assert decoded.judge_calls == 0
    assert decoded.judge_cost_usd == 0.0
