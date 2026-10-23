"""Pre-runtime checks shared by commands that execute durable benchmarks.

Each check reports its failure on standard error and returns a falsy result,
so commands can reject a benchmark before runtime bootstrap, without provider
credentials and without executing any case.
"""

import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.evaluation import (
    BenchmarkDataset,
    OutcomeEvaluator,
    SQLiteBenchmarkRepository,
    UnsupportedComparisonError,
)
from azathoth.workflows import SQLiteWorkflowRepository


def configured_benchmark(
    configuration: CliRuntimeConfiguration,
    benchmark_id: UUID,
) -> BenchmarkDataset | None:
    """Return one durable benchmark, reporting it when it is not configured."""

    dataset = SQLiteBenchmarkRepository(
        configuration.database,
    ).get(
        benchmark_id,
    )

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

    return dataset


def benchmark_has_cases(
    dataset: BenchmarkDataset,
) -> bool:
    """Report a benchmark that contains no cases."""

    if dataset.cases:
        return True

    print(
        f"Benchmark {dataset.id} has no cases.",
        file=sys.stderr,
    )

    return False


def comparisons_supported(
    dataset: BenchmarkDataset,
) -> bool:
    """Report the first case whose comparison cannot be evaluated yet."""

    evaluator = OutcomeEvaluator()

    for case in dataset.cases:
        try:
            evaluator.require_supported(
                case.expected.comparison,
                subject=f"Benchmark case {case.id}",
            )
        except UnsupportedComparisonError as exc:
            print(
                str(exc),
                file=sys.stderr,
            )

            return False

    return True


def results_declared(
    configuration: CliRuntimeConfiguration,
    workflow_ids: tuple[UUID, ...],
) -> bool:
    """Report the first configured workflow that declares no result.

    Unconfigured identifiers are left for runtime bootstrap to report.
    """

    repository = SQLiteWorkflowRepository(
        configuration.database,
    )

    for workflow_id in workflow_ids:
        specification = repository.get(workflow_id)

        if specification is not None and specification.result is None:
            print(
                f"Workflow {workflow_id} does not declare a result.",
                file=sys.stderr,
            )

            return False

    return True
