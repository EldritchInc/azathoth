"""Application services for optimizing configured workflows."""

from uuid import UUID

from azathoth.evaluation import (
    BenchmarkDataset,
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
    WorkflowResultError,
    WorkflowScorer,
    WorkflowScoringPolicy,
)


async def optimize_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    dataset: BenchmarkDataset,
    scoring_policy: WorkflowScoringPolicy,
    max_generations: int,
    recorder: WorkflowExperimentEvidenceRecorder | None = None,
) -> WorkflowOptimizationSession:
    """Run empirical model-substitution optimization for one workflow.

    Every generation runs each candidate against every benchmark case and
    judges the workflow's declared result with each case's own comparison. A
    workflow without a declared result, an empty benchmark, and an
    unsupported comparison are all rejected before any candidate is generated
    or executed.

    When a recorder is supplied, every generation's candidate runs,
    evaluations, and experiment record are persisted as durable evidence.

    Raises:
        ValueError: The benchmark contains no cases.
        UnsupportedComparisonError: A benchmark case uses a comparison with
            no evaluator.
        WorkflowResultError: The configured workflow declares no result.
    """

    specification = runtime.workflows.get(
        workflow_id,
    )

    if specification is not None and specification.result is None:
        raise WorkflowResultError(f"Workflow {workflow_id} does not declare a result.")

    if not dataset.cases:
        raise ValueError(f"Benchmark {dataset.id} has no cases.")

    evaluator = OutcomeEvaluator()

    for case in dataset.cases:
        evaluator.require_supported(
            case.expected.comparison,
            subject=f"Benchmark case {case.id}",
        )

    initial_candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    experiment_runner = WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=scoring_policy,
        ),
        evaluator=evaluator,
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
        dataset=dataset,
        max_generations=max_generations,
    )
