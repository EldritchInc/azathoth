"""Application services for optimizing configured workflows."""

from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    Evaluator,
    ExactMatchEvaluator,
    ExpectedOutcome,
)
from azathoth.optimization import (
    ModelSubstitutionWorkflowOptimizer,
    WorkflowOptimizationSession,
    WorkflowOptimizationSessionRunner,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
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
) -> WorkflowOptimizationSession:
    """Run empirical model-substitution optimization for one workflow."""

    initial_candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    experiment_runner = WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=scoring_policy,
        ),
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
        evaluator=evaluator if evaluator is not None else ExactMatchEvaluator(),
        expected_outcome=expected_outcome,
        max_generations=max_generations,
    )
