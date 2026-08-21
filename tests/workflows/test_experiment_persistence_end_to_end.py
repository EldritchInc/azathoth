"""End-to-end persistence of workflow experiment evidence."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCatalogLoader,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowRanker,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowRunner,
    WorkflowScorecard,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_workflow_candidate,
)

EXPERIMENT_ID = UUID("11111111-1111-1111-1111-111111111111")

PASSING_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
FAILING_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

PASSING_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
FAILING_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

PASSING_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")
FAILING_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

PASSING_MODEL = "passing-model"
FAILING_MODEL = "failing-model"
MODEL_PROVIDER = "deterministic"

EVALUATED_AT = datetime(
    2026,
    8,
    20,
    20,
    0,
    tzinfo=UTC,
)

RECORDED_AT = datetime(
    2026,
    8,
    20,
    20,
    1,
    tzinfo=UTC,
)


def create_workflow(
    *,
    workflow_id: UUID,
    workflow_name: str,
    step_id: UUID,
    strategy_id: UUID,
) -> WorkflowSpecification:
    """Create one durable single-step workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=workflow_name,
            description=f"Execute {workflow_name}.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{workflow_name} strategy",
                        description=f"Execute the {workflow_name} strategy.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the request.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_passing_workflow() -> WorkflowSpecification:
    """Create the workflow whose output satisfies the expectation."""

    return create_workflow(
        workflow_id=PASSING_WORKFLOW_ID,
        workflow_name="passing workflow",
        step_id=PASSING_STEP_ID,
        strategy_id=PASSING_STRATEGY_ID,
    )


def create_failing_workflow() -> WorkflowSpecification:
    """Create the workflow whose output fails the expectation."""

    return create_workflow(
        workflow_id=FAILING_WORKFLOW_ID,
        workflow_name="failing workflow",
        step_id=FAILING_STEP_ID,
        strategy_id=FAILING_STRATEGY_ID,
    )


def create_model_catalog(
    model: str,
) -> ModelCatalog:
    """Create metadata for one deterministic executable model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL_PROVIDER,
                model=model,
                display_name=model,
                context_window_tokens=8_192,
            ),
        ),
    )


def create_model_registry(
    *,
    model: str,
    response_text: str,
) -> LanguageModelRegistry:
    """Create one deterministic executable model registry."""

    identifier = f"{MODEL_PROVIDER}/{model}"

    return LanguageModelRegistry(
        models={
            identifier: DeterministicLanguageModel(
                provider=MODEL_PROVIDER,
                model=model,
                response_text=response_text,
            ),
        },
    )


def create_expected_outcome() -> ExpectedOutcome:
    """Create the shared experiment expectation."""

    return ExpectedOutcome(
        description="The classification should be positive.",
        value="positive",
        comparison=OutcomeComparison.EXACT,
    )


def create_scorer() -> WorkflowScorer:
    """Create deterministic workflow scoring policy."""

    return WorkflowScorer(
        policy=WorkflowScoringPolicy(
            target_latency_seconds=1.0,
            target_cost_usd=0.01,
        ),
    )


def persist_workflows(
    database: Path,
) -> None:
    """Persist both workflow specifications."""

    repository = SQLiteWorkflowRepository(database)

    repository.save(create_passing_workflow())
    repository.save(create_failing_workflow())


def load_workflow(
    *,
    database: Path,
    workflow_id: UUID,
) -> WorkflowSpecification:
    """Reconstruct one persisted workflow."""

    catalog = WorkflowCatalogLoader(SQLiteWorkflowRepository(database)).load_catalog()

    specification = catalog.get(workflow_id)

    assert specification is not None

    return specification


def execute_workflow(
    *,
    workflow_database: Path,
    workflow_id: UUID,
    model: str,
    response_text: str,
) -> WorkflowRun:
    """Reconstruct and execute one persisted workflow."""

    specification = load_workflow(
        database=workflow_database,
        workflow_id=workflow_id,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_model_catalog(model),
        registry=create_model_registry(
            model=model,
            response_text=response_text,
        ),
    )

    return asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )


def evaluate_run(
    run: WorkflowRun,
) -> EvaluationResult:
    """Evaluate one workflow's classification output."""

    values = run.values_named("classification")

    assert len(values) == 1

    return asyncio.run(
        ExactMatchEvaluator().evaluate(
            expected=create_expected_outcome(),
            actual=values[0].value,
        )
    )


def create_run_evaluation(
    *,
    run: WorkflowRun,
    evaluation: EvaluationResult,
) -> WorkflowRunEvaluation:
    """Associate one evaluator judgment with its workflow run."""

    return WorkflowRunEvaluation(
        run_id=run.id,
        evaluation=evaluation,
        evaluated_at=EVALUATED_AT,
    )


def create_observation(
    *,
    run: WorkflowRun,
    evaluation: EvaluationResult,
    scorecard: WorkflowScorecard,
) -> WorkflowExperimentObservation:
    """Create durable experiment provenance for one execution."""

    return WorkflowExperimentObservation(
        workflow=run.workflow,
        run_id=run.id,
        evaluation_id=evaluation.id,
        scorecard=scorecard,
    )


def run_id_for_scorecard(
    *,
    scorecard: WorkflowScorecard,
    observations: tuple[
        WorkflowExperimentObservation,
        ...,
    ],
) -> UUID:
    """Return the unique run that produced one experiment scorecard."""

    matches = tuple(
        observation.run_id for observation in observations if observation.scorecard == scorecard
    )

    assert len(matches) == 1

    return matches[0]


def test_durable_experiment_reconstructs_complete_source_evidence(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflows(workflow_database)

    passing_run = execute_workflow(
        workflow_database=workflow_database,
        workflow_id=PASSING_WORKFLOW_ID,
        model=PASSING_MODEL,
        response_text="positive",
    )

    failing_run = execute_workflow(
        workflow_database=workflow_database,
        workflow_id=FAILING_WORKFLOW_ID,
        model=FAILING_MODEL,
        response_text="negative",
    )

    passing_evaluation = evaluate_run(passing_run)
    failing_evaluation = evaluate_run(failing_run)

    scorer = create_scorer()

    passing_scorecard = scorer.score(
        run=passing_run,
        evaluation=passing_evaluation,
    )

    failing_scorecard = scorer.score(
        run=failing_run,
        evaluation=failing_evaluation,
    )

    observations = (
        create_observation(
            run=passing_run,
            evaluation=passing_evaluation,
            scorecard=passing_scorecard,
        ),
        create_observation(
            run=failing_run,
            evaluation=failing_evaluation,
            scorecard=failing_scorecard,
        ),
    )

    ranking = WorkflowRanker().rank(
        (
            passing_scorecard,
            failing_scorecard,
        )
    )

    ranking_run_ids = tuple(
        run_id_for_scorecard(
            scorecard=entry.scorecard,
            observations=observations,
        )
        for entry in ranking.entries
    )

    experiment = WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        observations=observations,
        ranking=ranking_run_ids,
        recorded_at=RECORDED_AT,
    )

    run_repository = SQLiteWorkflowRunRepository(evidence_database)
    evaluation_repository = SQLiteWorkflowRunEvaluationRepository(evidence_database)
    experiment_repository = SQLiteWorkflowExperimentRepository(evidence_database)

    run_repository.save(passing_run)
    run_repository.save(failing_run)

    evaluation_repository.save(
        create_run_evaluation(
            run=passing_run,
            evaluation=passing_evaluation,
        )
    )
    evaluation_repository.save(
        create_run_evaluation(
            run=failing_run,
            evaluation=failing_evaluation,
        )
    )

    experiment_repository.save(experiment)

    restored_experiment = SQLiteWorkflowExperimentRepository(evidence_database).get(EXPERIMENT_ID)

    assert restored_experiment is not None

    assert restored_experiment == experiment
    assert restored_experiment is not experiment

    assert restored_experiment.winner.run_id == passing_run.id

    restored_passing_run = SQLiteWorkflowRunRepository(evidence_database).get(
        restored_experiment.winner.run_id
    )

    assert restored_passing_run == passing_run

    winner_evaluation_id = restored_experiment.winner.evaluation_id

    restored_passing_evaluation = SQLiteWorkflowRunEvaluationRepository(evidence_database).get(
        winner_evaluation_id
    )

    assert restored_passing_evaluation is not None

    assert restored_passing_evaluation.run_id == passing_run.id
    assert restored_passing_evaluation.evaluation == passing_evaluation


def test_experiment_ranking_preserves_empirical_winner(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflows(workflow_database)

    passing_run = execute_workflow(
        workflow_database=workflow_database,
        workflow_id=PASSING_WORKFLOW_ID,
        model=PASSING_MODEL,
        response_text="positive",
    )

    failing_run = execute_workflow(
        workflow_database=workflow_database,
        workflow_id=FAILING_WORKFLOW_ID,
        model=FAILING_MODEL,
        response_text="negative",
    )

    passing_evaluation = evaluate_run(passing_run)
    failing_evaluation = evaluate_run(failing_run)

    assert passing_evaluation.status is EvaluationStatus.PASSED
    assert failing_evaluation.status is EvaluationStatus.FAILED

    scorer = create_scorer()

    passing_scorecard = scorer.score(
        run=passing_run,
        evaluation=passing_evaluation,
    )

    failing_scorecard = scorer.score(
        run=failing_run,
        evaluation=failing_evaluation,
    )

    assert passing_scorecard.overall_score > failing_scorecard.overall_score

    observations = (
        create_observation(
            run=passing_run,
            evaluation=passing_evaluation,
            scorecard=passing_scorecard,
        ),
        create_observation(
            run=failing_run,
            evaluation=failing_evaluation,
            scorecard=failing_scorecard,
        ),
    )

    ranking = WorkflowRanker().rank(
        (
            passing_scorecard,
            failing_scorecard,
        )
    )

    experiment = WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        observations=observations,
        ranking=tuple(
            run_id_for_scorecard(
                scorecard=entry.scorecard,
                observations=observations,
            )
            for entry in ranking.entries
        ),
        recorded_at=RECORDED_AT,
    )

    SQLiteWorkflowExperimentRepository(evidence_database).save(experiment)

    restored = SQLiteWorkflowExperimentRepository(evidence_database).get(EXPERIMENT_ID)

    assert restored is not None

    assert restored.ranking == (
        passing_run.id,
        failing_run.id,
    )

    assert restored.winner.workflow.id == PASSING_WORKFLOW_ID

    failing_observation = restored.observation_for_run(failing_run.id)

    assert failing_observation is not None

    assert restored.winner.scorecard.overall_score > failing_observation.scorecard.overall_score


def test_experiment_references_match_persisted_runs_and_evaluations(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflows(workflow_database)

    runs = (
        execute_workflow(
            workflow_database=workflow_database,
            workflow_id=PASSING_WORKFLOW_ID,
            model=PASSING_MODEL,
            response_text="positive",
        ),
        execute_workflow(
            workflow_database=workflow_database,
            workflow_id=FAILING_WORKFLOW_ID,
            model=FAILING_MODEL,
            response_text="negative",
        ),
    )

    evaluations = tuple(evaluate_run(run) for run in runs)

    scorer = create_scorer()

    scorecards = tuple(
        scorer.score(
            run=run,
            evaluation=evaluation,
        )
        for run, evaluation in zip(
            runs,
            evaluations,
            strict=True,
        )
    )

    observations = tuple(
        create_observation(
            run=run,
            evaluation=evaluation,
            scorecard=scorecard,
        )
        for run, evaluation, scorecard in zip(
            runs,
            evaluations,
            scorecards,
            strict=True,
        )
    )

    ranking = WorkflowRanker().rank(scorecards)

    experiment = WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        observations=observations,
        ranking=tuple(
            run_id_for_scorecard(
                scorecard=entry.scorecard,
                observations=observations,
            )
            for entry in ranking.entries
        ),
        recorded_at=RECORDED_AT,
    )

    run_repository = SQLiteWorkflowRunRepository(evidence_database)
    evaluation_repository = SQLiteWorkflowRunEvaluationRepository(evidence_database)

    for run, evaluation in zip(
        runs,
        evaluations,
        strict=True,
    ):
        run_repository.save(run)

        evaluation_repository.save(
            create_run_evaluation(
                run=run,
                evaluation=evaluation,
            )
        )

    SQLiteWorkflowExperimentRepository(evidence_database).save(experiment)

    restored = SQLiteWorkflowExperimentRepository(evidence_database).get(EXPERIMENT_ID)

    assert restored is not None

    for observation in restored.observations:
        persisted_run = SQLiteWorkflowRunRepository(evidence_database).get(observation.run_id)

        persisted_evaluation = SQLiteWorkflowRunEvaluationRepository(evidence_database).get(
            observation.evaluation_id
        )

        assert persisted_run is not None
        assert persisted_evaluation is not None

        assert persisted_run.id == observation.run_id
        assert persisted_run.workflow == observation.workflow

        assert persisted_evaluation.id == observation.evaluation_id
        assert persisted_evaluation.run_id == observation.run_id


def test_experiment_can_be_discovered_from_workflow_identity(
    tmp_path: Path,
) -> None:
    evidence_database = tmp_path / "evidence.db"

    passing_observation = WorkflowExperimentObservation(
        workflow=create_passing_workflow().metadata,
        run_id=UUID("88888888-8888-8888-8888-888888888888"),
        evaluation_id=UUID("99999999-9999-9999-9999-999999999999"),
        scorecard=WorkflowScorecard(
            quality_score=1.0,
            reliability_score=1.0,
            latency_score=1.0,
            cost_score=1.0,
            overall_score=1.0,
            rationale="Winning experiment observation.",
        ),
    )

    failing_observation = WorkflowExperimentObservation(
        workflow=create_failing_workflow().metadata,
        run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        evaluation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        scorecard=WorkflowScorecard(
            quality_score=0.0,
            reliability_score=1.0,
            latency_score=1.0,
            cost_score=1.0,
            overall_score=0.75,
            rationale="Losing experiment observation.",
        ),
    )

    experiment = WorkflowExperimentRecord(
        id=EXPERIMENT_ID,
        observations=(
            passing_observation,
            failing_observation,
        ),
        ranking=(
            passing_observation.run_id,
            failing_observation.run_id,
        ),
        recorded_at=RECORDED_AT,
    )

    repository = SQLiteWorkflowExperimentRepository(evidence_database)

    repository.save(experiment)

    assert repository.experiments_for_workflow(PASSING_WORKFLOW_ID) == (experiment,)

    assert repository.experiments_for_workflow(FAILING_WORKFLOW_ID) == (experiment,)
