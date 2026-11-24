"""Running benchmarks and optimizing workflows on a remote, reported as here (ADR 0140).

`benchmark run`, `benchmark compare` and `workflow optimize` given
`--remote` make their call of the service API on that remote, where it
runs as a job, and print what they print here: the remote checks the
benchmark and the workflows before any case runs, and refuses with the
same words. The call runs on a thread of its own while the command waits,
so Ctrl-C or SIGTERM cancels the job at the remote before the command
stops.
"""

import sys
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.remote_runs import on_remote
from azathoth.cli.rendering.benchmark_executions import (
    render_workflow_benchmark_comparison_execution,
)
from azathoth.cli.rendering.benchmarks import render_benchmark_run
from azathoth.cli.rendering.optimization import render_optimization_summary
from azathoth.cli.service import service_instance

T = TypeVar("T")


def _reported(
    call: Callable[[api.Instance, api.CancellationToken], T],
    render: Callable[[T], str],
) -> int:
    """Make a call of the remote `--remote` chose and print what it returns, or why it failed."""

    try:
        instance = service_instance(CliRuntimeConfiguration.from_environment())
        returned = on_remote(lambda token: call(instance, token))
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(render(returned))

    return 0


def run_benchmark_on_remote(
    *,
    benchmark_id: UUID,
    workflow_id: UUID,
) -> int:
    """Run a workflow against a benchmark on a remote, as `benchmark run` reports one here."""

    return _reported(
        lambda instance, token: instance.benchmarks.run(benchmark_id, workflow_id, cancel=token),
        render_benchmark_run,
    )


def compare_benchmarks_on_remote(
    *,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
    target_latency_seconds: float,
    target_cost_usd: float,
) -> int:
    """Compare workflows against a benchmark on a remote, as `benchmark compare` reports here."""

    return _reported(
        lambda instance, token: instance.benchmarks.compare(
            benchmark_id,
            workflow_ids,
            target_latency_seconds=target_latency_seconds,
            target_cost_usd=target_cost_usd,
            cancel=token,
        ),
        render_workflow_benchmark_comparison_execution,
    )


def optimize_on_remote(
    *,
    workflow_id: UUID,
    benchmark_id: UUID,
    target_latency_seconds: float,
    target_cost_usd: float,
    generations: int,
) -> int:
    """Optimize a workflow against a benchmark on a remote, as `workflow optimize` reports here."""

    return _reported(
        lambda instance, token: instance.optimization.optimize(
            workflow_id,
            benchmark_id,
            target_latency_seconds=target_latency_seconds,
            target_cost_usd=target_cost_usd,
            generations=generations,
            cancel=token,
        ),
        render_optimization_summary,
    )


__all__ = [
    "compare_benchmarks_on_remote",
    "optimize_on_remote",
    "run_benchmark_on_remote",
]
