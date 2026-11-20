"""`workflow diff`, `tool diff` and `benchmark diff` (ADR 0133).

Each reads through the service API's `compare_revisions`, so the command
line and every other caller say the same of what changed between two
revisions. Only durable state is read.
"""

import sys
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.output_format import DiffOutputFormat
from azathoth.cli.rendering import render_revision_comparison
from azathoth.cli.rendering.sensitivity import warn_if_restricted
from azathoth.cli.service import service_instance
from azathoth.sensitivity import Sensitivity


def _printed(
    comparison: api.RevisionComparison,
    output: DiffOutputFormat,
) -> int:
    """Print one comparison in the output format asked for."""

    if output is DiffOutputFormat.JSON:
        print(comparison.model_dump_json(indent=2))
    else:
        print(render_revision_comparison(comparison))

    return 0


def diff_workflow(
    workflow_id: UUID,
    before: int,
    after: int,
    *,
    output: DiffOutputFormat = DiffOutputFormat.TEXT,
) -> int:
    """Print what differs between two imported revisions of one workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        comparison = service_instance(configuration).workflows.compare_revisions(
            workflow_id, before, after
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return _printed(comparison, output)


def diff_tool(
    tool_id: UUID,
    before: int,
    after: int,
    *,
    version: str,
    output: DiffOutputFormat = DiffOutputFormat.TEXT,
) -> int:
    """Print what differs between two imported revisions of one exact tool version."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        comparison = service_instance(configuration).tools.compare_revisions(
            tool_id, version, before, after
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return _printed(comparison, output)


def diff_benchmark(
    benchmark_id: UUID,
    before: int,
    after: int,
    *,
    output: DiffOutputFormat = DiffOutputFormat.TEXT,
) -> int:
    """Print what differs between two imported revisions of one benchmark.

    The owner may read restricted data, so a restricted case's values are
    printed, and a warning on standard error says the output holds them,
    as `benchmark export` warns.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        benchmarks = service_instance(configuration).benchmarks
        comparison = benchmarks.compare_revisions(benchmark_id, before, after)
        withheld = benchmarks.compare_revisions(
            benchmark_id, before, after, include_restricted=False
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    status = _printed(comparison, output)

    if any(change.withheld for change in withheld.changes):
        warn_if_restricted(Sensitivity.RESTRICTED, f"Benchmark {benchmark_id}")

    return status


__all__ = [
    "diff_benchmark",
    "diff_tool",
    "diff_workflow",
]
