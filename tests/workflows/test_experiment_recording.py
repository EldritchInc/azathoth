"""Tests for durable recording of workflow experiment evidence."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.strategies import (
    Strategy,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    InMemoryWorkflowExperimentRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
)

WEAK_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STRONG_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

BROKEN_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

WEAK_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRONG_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

BROKEN_STEP_ID = UUID("66666666-6666-6666-6666-666666666666")

WEAK_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

STRONG_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

BROKEN_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")


class StaticStrategy:
    """Return one configured deterministic strategy outcome."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        output: str,
        estimated_cost_usd: float,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"strategy-{strategy_id}",
            description="Deterministic recorded experiment strategy.",
        )
        self._output = output
        self._estimated_cost_usd = estimated_cost_usd

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return the configured strategy outcome."""

        return StrategyOutcome(
            output=self._output,
            metrics=StrategyExecutionMetrics(
                provider="test-provider",
                model="test-model",
                prompt_tokens=10,
                completion_tokens=1,
                total_tokens=11,
                latency_ms=100,
                estimated_cost_usd=self._estimated_cost_usd,
            ),
        )


class FailingStrategy:
    """Raise one deterministic execution failure."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"failing-strategy-{strategy_id}",
            description="Deterministic failing recorded experiment strategy.",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Raise the configured execution failure."""

        raise RuntimeError("Recorded experiment failure.")


class ExactEvaluator:
    """Score exact expected matches."""

    @property
    def metadata(self) -> EvaluatorMetadata:
        """Return deterministic evaluator metadata."""

        return EvaluatorMetadata(
            name="exact-evaluator",
            description="Score exact recorded experiment matches.",
        )

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: object,
    ) -> EvaluationResult:
        """Evaluate one workflow output."""

        passed = actual == expected.value

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            score=1.0 if passed else 0.0,
            threshold=1.0,
            status=EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED,
            reason="Matched." if passed else "Did not match.",
        )


class Repositories:
    """Hold in-memory evidence repositories behind one recorder."""

    def __init__(self) -> None:
        self.runs = InMemoryWorkflowRunRepository()
        self.evaluations = InMemoryWorkflowRunEvaluationRepository()
        self.experiments = InMemoryWorkflowExperimentRepository()
        self.recorder = WorkflowExperimentEvidenceRecorder(
            runs=self.runs,
            evaluations=self.evaluations,
            experiments=self.experiments,
        )


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy: Strategy,
) -> WorkflowCandidate:
    """Create a deterministic one-step workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow-{workflow_id}",
            description="Workflow used for experiment recording tests.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=step_id,
                strategy=strategy,
            ),
        ),
    )


def weak_workflow() -> WorkflowCandidate:
    """Create a candidate that answers wrongly and expensively."""

    return create_workflow(
        workflow_id=WEAK_WORKFLOW_ID,
        step_id=WEAK_STEP_ID,
        strategy=StaticStrategy(
            strategy_id=WEAK_STRATEGY_ID,
            output="failure",
            estimated_cost_usd=0.40,
        ),
    )


def strong_workflow() -> WorkflowCandidate:
    """Create a candidate that answers correctly and cheaply."""

    return create_workflow(
        workflow_id=STRONG_WORKFLOW_ID,
        step_id=STRONG_STEP_ID,
        strategy=StaticStrategy(
            strategy_id=STRONG_STRATEGY_ID,
            output="success",
            estimated_cost_usd=0.05,
        ),
    )


def broken_workflow() -> WorkflowCandidate:
    """Create a candidate whose only step fails."""

    return create_workflow(
        workflow_id=BROKEN_WORKFLOW_ID,
        step_id=BROKEN_STEP_ID,
        strategy=FailingStrategy(
            strategy_id=BROKEN_STRATEGY_ID,
        ),
    )


def run_experiment(
    repositories: Repositories,
    *workflows: WorkflowCandidate,
) -> WorkflowExperimentResult:
    """Run one recorded experiment over the given candidates."""

    return asyncio.run(
        WorkflowExperimentRunner(
            scorer=WorkflowScorer(
                policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.10,
                ),
            ),
            recorder=repositories.recorder,
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=ExactEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Workflow should return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
        )
    )


def run_id_for(
    repositories: Repositories,
    workflow_id: UUID,
) -> UUID:
    """Return the single persisted run identifier for one workflow."""

    runs = repositories.runs.runs_for_workflow(workflow_id)

    assert len(runs) == 1

    return runs[0].id


def test_recorded_experiment_persists_every_candidate_run() -> None:
    repositories = Repositories()

    run_experiment(
        repositories,
        weak_workflow(),
        broken_workflow(),
        strong_workflow(),
    )

    runs = repositories.runs.runs()

    assert tuple(run.workflow.id for run in runs) == (
        WEAK_WORKFLOW_ID,
        BROKEN_WORKFLOW_ID,
        STRONG_WORKFLOW_ID,
    )
    assert tuple(run.failed for run in runs) == (
        False,
        True,
        False,
    )


def test_recorded_experiment_persists_evaluations_of_successful_runs_only() -> None:
    repositories = Repositories()

    run_experiment(
        repositories,
        weak_workflow(),
        broken_workflow(),
        strong_workflow(),
    )

    evaluations = repositories.evaluations.evaluations()

    assert tuple(evaluation.run_id for evaluation in evaluations) == (
        run_id_for(repositories, WEAK_WORKFLOW_ID),
        run_id_for(repositories, STRONG_WORKFLOW_ID),
    )
    assert tuple(evaluation.evaluation.status for evaluation in evaluations) == (
        EvaluationStatus.FAILED,
        EvaluationStatus.PASSED,
    )


def test_recorded_experiment_shares_result_identity() -> None:
    repositories = Repositories()

    result = run_experiment(
        repositories,
        weak_workflow(),
        strong_workflow(),
    )

    experiments = repositories.experiments.experiments()

    assert len(experiments) == 1
    assert experiments[0].id == result.id


def test_recorded_experiment_observations_reference_persisted_evidence() -> None:
    repositories = Repositories()

    run_experiment(
        repositories,
        weak_workflow(),
        broken_workflow(),
        strong_workflow(),
    )

    record = repositories.experiments.experiments()[0]
    weak_run_id = run_id_for(repositories, WEAK_WORKFLOW_ID)
    strong_run_id = run_id_for(repositories, STRONG_WORKFLOW_ID)

    assert tuple(observation.run_id for observation in record.observations) == (
        weak_run_id,
        strong_run_id,
    )

    for observation in record.observations:
        evaluation = repositories.evaluations.get(observation.evaluation_id)

        assert evaluation is not None
        assert evaluation.run_id == observation.run_id
        assert observation.candidate_signature.workflow_id == observation.workflow.id


def test_recorded_experiment_ranks_runs_like_the_result() -> None:
    repositories = Repositories()

    result = run_experiment(
        repositories,
        weak_workflow(),
        strong_workflow(),
    )

    record = repositories.experiments.experiments()[0]

    assert record.ranking == (
        run_id_for(repositories, STRONG_WORKFLOW_ID),
        run_id_for(repositories, WEAK_WORKFLOW_ID),
    )
    assert record.winner.workflow.id == STRONG_WORKFLOW_ID
    assert record.winner.scorecard == result.winner


def test_failed_population_persists_runs_without_experiment_record() -> None:
    repositories = Repositories()

    with pytest.raises(ValueError):
        run_experiment(
            repositories,
            broken_workflow(),
        )

    assert tuple(run.workflow.id for run in repositories.runs.runs()) == (BROKEN_WORKFLOW_ID,)
    assert repositories.evaluations.evaluations() == ()
    assert repositories.experiments.experiments() == ()
