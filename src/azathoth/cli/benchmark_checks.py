"""Pre-runtime checks shared by commands that execute durable benchmarks.

Each check reports its failure on standard error and returns a falsy result,
so commands can reject a benchmark before runtime bootstrap, without provider
credentials and without executing any case. Why each refuses is the service
API's (ADR 0130), so both refuse a benchmark alike.
"""

import sys
from uuid import UUID

from azathoth.api.benchmark_execution import (
    missing_cases,
    undeclared_result,
    unsupported_comparison,
)
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.evaluation import BenchmarkDataset


def _reported(
    problem: str | None,
) -> bool:
    """Report a problem on standard error, and return whether there was none."""

    if problem is None:
        return True

    print(
        problem,
        file=sys.stderr,
    )

    return False


def configured_benchmark(
    configuration: CliRuntimeConfiguration,
    benchmark_id: UUID,
) -> BenchmarkDataset | None:
    """Return one durable benchmark, reporting it when it is not configured."""

    dataset = repositories(configuration).benchmarks.get(
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

    return _reported(missing_cases(dataset))


def comparisons_supported(
    configuration: CliRuntimeConfiguration,
    dataset: BenchmarkDataset,
) -> bool:
    """Report the first case whose comparison cannot be evaluated.

    A semantic case can be evaluated only when the durable judge rotation has
    at least one judge. Whether those judges are authorized and available is
    checked once the runtime is loaded.
    """

    problem = unsupported_comparison(repositories(configuration), dataset)

    return _reported(None if problem is None else problem.message)


def results_declared(
    configuration: CliRuntimeConfiguration,
    workflow_ids: tuple[UUID, ...],
) -> bool:
    """Report the first configured workflow that declares no result.

    Unconfigured identifiers are left for runtime bootstrap to report.
    """

    return _reported(undeclared_result(repositories(configuration), workflow_ids))
