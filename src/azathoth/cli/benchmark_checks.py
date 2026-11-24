"""Pre-runtime checks shared by commands that execute durable benchmarks.

Each check reports its failure on standard error and returns a falsy result,
so commands can reject a benchmark before runtime bootstrap, without provider
credentials and without executing any case. Why each refuses is the service
API's (ADR 0130), so both refuse a benchmark alike.
"""

import sys
from uuid import UUID

from azathoth import api
from azathoth.api.benchmark_execution import (
    compared_workflows,
    missing_cases,
    scoring_policy,
    undeclared_result,
    unsupported_comparison,
)
from azathoth.api.optimization import GENERATIONS_MESSAGE
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.evaluation import BenchmarkDataset
from azathoth.workflows import WorkflowScoringPolicy


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


def comparison_policy(
    workflow_ids: tuple[UUID, ...],
    *,
    target_latency_seconds: float,
    target_cost_usd: float,
) -> WorkflowScoringPolicy | None:
    """Return the policy a comparison scores by, reporting why its arguments are refused.

    Two distinct workflows or more and targets above zero are checked
    first, as `benchmarks.compare` checks them, before the benchmark.
    """

    try:
        compared_workflows(workflow_ids)

        return scoring_policy(target_latency_seconds, target_cost_usd)
    except api.InvalidArgumentError as exc:
        _reported(str(exc))

        return None


def optimization_policy(
    generations: int,
    *,
    target_latency_seconds: float,
    target_cost_usd: float,
) -> WorkflowScoringPolicy | None:
    """Return the policy a session scores by, reporting why its arguments are refused.

    At least one generation and targets above zero are checked first, as
    `optimization.optimize` checks them, before the benchmark.
    """

    if generations < 1:
        _reported(GENERATIONS_MESSAGE)

        return None

    try:
        return scoring_policy(target_latency_seconds, target_cost_usd)
    except api.InvalidArgumentError as exc:
        _reported(str(exc))

        return None


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
