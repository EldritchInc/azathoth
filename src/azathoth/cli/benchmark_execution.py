"""Application services for executing configured workflow benchmarks."""

from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowBenchmarkResult,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
)


async def execute_configured_benchmark(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    dataset: BenchmarkDataset,
    output_name: str,
    runner: WorkflowBenchmarkRunner | None = None,
) -> WorkflowBenchmarkResult:
    """Execute one configured workflow against a benchmark dataset."""

    benchmark_runner = runner if runner is not None else WorkflowBenchmarkRunner()

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
        output_name=output_name,
    )


__all__ = [
    "execute_configured_benchmark",
]
