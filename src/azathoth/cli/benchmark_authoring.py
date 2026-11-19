"""Commands that create a benchmark and edit its cases (ADR 0130).

Each command calls the service API, so the command line and the API edit a
benchmark by the same rules, and each change saves the benchmark's next
revision. Only durable state is read and written, so no provider
credentials are needed.
"""

import sys
from uuid import UUID

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.service import service_instance
from azathoth.sensitivity import Sensitivity


def create_benchmark(
    *,
    name: str,
    description: str,
    version: str,
) -> int:
    """Create a benchmark with no cases, and print its ID."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        created = service_instance(configuration).benchmarks.create(
            name,
            description,
            version=version,
        )
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        f"Created benchmark dataset {created.benchmark.id} "
        f"revision {created.benchmark.revision.number}."
    )

    return 0


def edit_benchmark_case(
    benchmark_id: UUID,
    case_id: UUID,
    *,
    comparison: api.CaseComparison | None,
    expected: JsonValue | api.Keep,
    description: str | None,
    citations: api.CaseCitations | None | api.Keep,
    sensitivity: Sensitivity | None,
) -> int:
    """Change what one case expects, as the benchmark's next revision."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        change = service_instance(configuration).benchmarks.update_case(
            benchmark_id,
            case_id,
            comparison=comparison,
            expected=expected,
            description=description,
            citations=citations,
            sensitivity=sensitivity,
        )
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        f"Edited benchmark case {case_id} in benchmark dataset {benchmark_id} "
        f"revision {change.benchmark.revision.number}."
    )

    return 0


def remove_benchmark_case(
    benchmark_id: UUID,
    case_id: UUID,
) -> int:
    """Save the benchmark's next revision without one case."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        change = service_instance(configuration).benchmarks.remove_case(benchmark_id, case_id)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        f"Removed benchmark case {case_id} from benchmark dataset {benchmark_id} "
        f"revision {change.benchmark.revision.number}."
    )

    return 0


__all__ = [
    "create_benchmark",
    "edit_benchmark_case",
    "remove_benchmark_case",
]
