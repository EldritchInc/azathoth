"""Application services for executing configured workflow benchmarks."""

from collections.abc import Callable
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    OutcomeEvaluator,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowBenchmarkComparator,
    WorkflowBenchmarkRanker,
    WorkflowBenchmarkRanking,
    WorkflowBenchmarkResult,
    WorkflowBenchmarkRunner,
    WorkflowBenchmarkScorer,
    WorkflowCandidate,
    WorkflowScoringPolicy,
)


async def execute_configured_benchmark(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    dataset: BenchmarkDataset,
    runner: WorkflowBenchmarkRunner | None = None,
) -> WorkflowBenchmarkResult:
    """Execute one configured workflow against a benchmark dataset.

    Without an explicit runner, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes.

    Raises:
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
    """

    benchmark_runner = (
        runner
        if runner is not None
        else WorkflowBenchmarkRunner(
            evaluator=_outcome_evaluator(
                runtime,
                dataset,
            ),
        )
    )

    def candidate_factory(
        _case: BenchmarkCase,
    ) -> WorkflowCandidate:
        """Generate the configured workflow candidate for one case."""

        return runtime.generate_workflow_candidate(
            workflow_id,
        )

    return await benchmark_runner.run(
        dataset,
        candidate_factory,
    )


async def compare_configured_benchmarks(
    *,
    runtime: RuntimeEnvironment,
    workflow_ids: tuple[UUID, ...],
    dataset: BenchmarkDataset,
    scoring_policy: WorkflowScoringPolicy,
    comparator: WorkflowBenchmarkComparator | None = None,
) -> WorkflowBenchmarkRanking:
    """Compare configured workflows against one benchmark dataset.

    Without an explicit comparator, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes.

    Raises:
        ValueError: Fewer than two workflows, or duplicate workflows.
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
    """

    if len(workflow_ids) < 2:
        raise ValueError("At least two configured workflows are required for benchmark comparison.")

    if len(workflow_ids) != len(set(workflow_ids)):
        raise ValueError("Configured benchmark workflow identifiers must be unique.")

    benchmark_comparator = (
        comparator
        if comparator is not None
        else WorkflowBenchmarkComparator(
            runner=WorkflowBenchmarkRunner(
                evaluator=_outcome_evaluator(
                    runtime,
                    dataset,
                ),
            ),
        )
    )

    def configured_candidate_factory(
        workflow_id: UUID,
    ) -> Callable[[BenchmarkCase], WorkflowCandidate]:
        """Create a case-independent candidate factory for one workflow."""

        def candidate_factory(
            _case: BenchmarkCase,
        ) -> WorkflowCandidate:
            """Generate the configured workflow candidate."""

            return runtime.generate_workflow_candidate(
                workflow_id,
            )

        return candidate_factory

    candidate_factories = {
        str(workflow_id): configured_candidate_factory(
            workflow_id,
        )
        for workflow_id in workflow_ids
    }

    comparison = await benchmark_comparator.compare(
        dataset,
        candidate_factories,
    )

    scorer = WorkflowBenchmarkScorer(
        policy=scoring_policy,
    )

    ranker = WorkflowBenchmarkRanker(
        scorer=scorer,
    )

    return ranker.rank(
        comparison,
    )


def _outcome_evaluator(
    runtime: RuntimeEnvironment,
    dataset: BenchmarkDataset,
) -> OutcomeEvaluator:
    """Return the runtime evaluator, with judges only when the dataset needs them.

    Raises:
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
    """

    return runtime.outcome_evaluator(
        semantic=dataset.uses_comparison(OutcomeComparison.SEMANTIC),
    )


__all__ = [
    "compare_configured_benchmarks",
    "execute_configured_benchmark",
]
