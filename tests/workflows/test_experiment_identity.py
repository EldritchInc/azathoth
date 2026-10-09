"""Tests for workflow experiment result identity."""

from uuid import UUID

from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidateSignature,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowRanking,
    WorkflowScorecard,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555555")


def create_experiment(
    experiment_id: UUID | None = None,
) -> WorkflowExperimentResult:
    """Create one deterministic single-candidate experiment."""

    scorecard = WorkflowScorecard(
        quality_score=1.0,
        reliability_score=1.0,
        latency_score=1.0,
        cost_score=1.0,
        overall_score=1.0,
    )

    evidence = (
        WorkflowExperimentEvidence(
            candidate_signature=WorkflowCandidateSignature(
                workflow_id=WORKFLOW_ID,
                strategy_ids=(STRATEGY_ID,),
            ),
            scorecard=scorecard,
        ),
    )

    ranking = WorkflowRanking(
        entries=(
            RankedWorkflow(
                rank=1,
                scorecard=scorecard,
            ),
        ),
    )

    if experiment_id is None:
        return WorkflowExperimentResult(
            evidence=evidence,
            ranking=ranking,
        )

    return WorkflowExperimentResult(
        id=experiment_id,
        evidence=evidence,
        ranking=ranking,
    )


def test_experiment_result_receives_identity_by_default() -> None:
    experiment = create_experiment()

    assert isinstance(experiment.id, UUID)


def test_separately_run_experiments_have_distinct_identities() -> None:
    first = create_experiment()
    second = create_experiment()

    assert first.id != second.id
    assert first.evidence == second.evidence
    assert first.ranking == second.ranking


def test_experiment_result_preserves_explicit_identity() -> None:
    assert create_experiment(EXPERIMENT_ID).id == EXPERIMENT_ID


def test_experiment_result_identity_survives_serialization() -> None:
    experiment = create_experiment(EXPERIMENT_ID)

    restored = WorkflowExperimentResult.model_validate_json(experiment.model_dump_json())

    assert restored == experiment
    assert restored.id == EXPERIMENT_ID
