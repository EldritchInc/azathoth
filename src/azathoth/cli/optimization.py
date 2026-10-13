"""Application services for optimizing configured workflows."""

from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    Evaluator,
    ExpectedOutcome,
    OutcomeEvaluator,
)
from azathoth.optimization import (
    ModelSubstitutionWorkflowOptimizer,
    WorkflowOptimizationSession,
    WorkflowOptimizationSessionRunner,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentRunner,
    WorkflowScorer,
    WorkflowScoringPolicy,
)


async def optimize_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    expected_outcome: ExpectedOutcome,
    scoring_policy: WorkflowScoringPolicy,
    max_generations: int,
    context: Context | None = None,
    evaluator: Evaluator | None = None,
    recorder: WorkflowExperimentEvidenceRecorder | None = None,
) -> WorkflowOptimizationSession:
    """Run empirical model-substitution optimization for one workflow.

    Without an explicit evaluator, the expected outcome is judged by the
    evaluator for its comparison, and an unsupported comparison is rejected
    before any candidate is generated or executed.

    When a recorder is supplied, every generation's candidate runs,
    evaluations, and experiment record are persisted as durable evidence.

    Raises:
        UnsupportedComparisonError: The default evaluator cannot judge the
            expected outcome's comparison.
    """

    if evaluator is None:
        outcome_evaluator = OutcomeEvaluator()

        outcome_evaluator.require_supported(
            expected_outcome.comparison,
        )

        evaluator = outcome_evaluator

    initial_candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    experiment_runner = WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=scoring_policy,
        ),
        recorder=recorder,
    )

    optimizer = ModelSubstitutionWorkflowOptimizer(
        workflows=runtime.workflows,
        models=runtime.models,
        portfolio=runtime.portfolio,
        registry=runtime.language_models,
    )

    session_runner = WorkflowOptimizationSessionRunner(
        experiment_runner=experiment_runner,
        optimizer=optimizer,
    )

    return await session_runner.run(
        initial_candidates=(initial_candidate,),
        context=context if context is not None else Context(),
        evaluator=evaluator,
        expected_outcome=expected_outcome,
        max_generations=max_generations,
    )
