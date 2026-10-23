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
    WorkflowBenchmarkEvidenceRecorder,
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
    recorder: WorkflowBenchmarkEvidenceRecorder | None = None,
) -> WorkflowBenchmarkResult:
    """Execute one configured workflow against a benchmark dataset.

    Without an explicit runner, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes. The workflow candidate
    is generated once, before any case executes, and runs every case, so the
    whole benchmark judges one resolved configuration.

    With a recorder, every case run, every evaluation, and one execution
    record sharing the result's identity are saved.

    Raises:
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
        WorkflowNotConfiguredError: The workflow is not configured.
        WorkflowGenerationError: The workflow cannot be generated.
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

    candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    result = await benchmark_runner.run(
        dataset,
        _every_case(candidate),
    )

    if recorder is not None:
        recorder.record_run(
            result,
            candidate=candidate,
        )

    return result


async def compare_configured_benchmarks(
    *,
    runtime: RuntimeEnvironment,
    workflow_ids: tuple[UUID, ...],
    dataset: BenchmarkDataset,
    scoring_policy: WorkflowScoringPolicy,
    comparator: WorkflowBenchmarkComparator | None = None,
    recorder: WorkflowBenchmarkEvidenceRecorder | None = None,
) -> WorkflowBenchmarkRanking:
    """Compare configured workflows against one benchmark dataset.

    Without an explicit comparator, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes. Every workflow
    candidate is generated once, before any case executes.

    With a recorder, every case run, every evaluation, and one execution
    record sharing the ranking's identity are saved, together with the
    scoring policy that produced the ranking.

    Raises:
        ValueError: Fewer than two workflows, or duplicate workflows.
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
        WorkflowNotConfiguredError: A workflow is not configured.
        WorkflowGenerationError: A workflow cannot be generated.
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

    candidates = {
        str(workflow_id): runtime.generate_workflow_candidate(
            workflow_id,
        )
        for workflow_id in workflow_ids
    }

    comparison = await benchmark_comparator.compare(
        dataset,
        {name: _every_case(candidate) for name, candidate in candidates.items()},
    )

    scorer = WorkflowBenchmarkScorer(
        policy=scoring_policy,
    )

    ranker = WorkflowBenchmarkRanker(
        scorer=scorer,
    )

    ranking = ranker.rank(
        comparison,
    )

    if recorder is not None:
        recorder.record_comparison(
            comparison,
            ranking,
            candidates=candidates,
            scoring_policy=scoring_policy,
        )

    return ranking


def _every_case(
    candidate: WorkflowCandidate,
) -> Callable[[BenchmarkCase], WorkflowCandidate]:
    """Return a candidate factory that runs one candidate for every case."""

    def factory(
        _case: BenchmarkCase,
    ) -> WorkflowCandidate:
        """Return the pre-generated candidate."""

        return candidate

    return factory


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
