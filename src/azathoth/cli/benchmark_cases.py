"""Benchmark case authoring commands for the Azathoth CLI."""

import sys
from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.evaluation import (
    BenchmarkCaseConflictError,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.workflows import (
    BenchmarkCaseSourceError,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    benchmark_case_from_run,
    latest_corrected_output,
    workflow_run_input,
)


@dataclass(frozen=True)
class SuppliedExpectedValue:
    """The expected value an operator supplied for a new benchmark case.

    Wrapping the value keeps a supplied JSON null distinct from no value at
    all: a supplied null is expected, and feedback is not consulted.
    """

    value: JsonValue


def add_benchmark_case(
    benchmark_id: UUID,
    *,
    run_id: UUID,
    comparison: OutcomeComparison,
    expected: SuppliedExpectedValue | None = None,
    description: str | None = None,
) -> int:
    """Append a case replaying one recorded run's input as a new benchmark revision.

    The case expects the supplied value. Without one, it expects the corrected
    output of the run's latest bad feedback that carries a correction; good
    feedback never supplies a value. The benchmark need not belong to the
    run's workflow, because any workflow can run against any benchmark.

    Nothing is written when any check fails. Only durable state is read, so
    the runtime is never loaded and no provider credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    benchmarks = SQLiteBenchmarkRepository(
        configuration.database,
    )

    dataset = benchmarks.get(benchmark_id)

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    run = SQLiteWorkflowRunRepository(
        configuration.database,
    ).get(run_id)

    if run is None:
        print(
            f"Run {run_id} was not found.",
            file=sys.stderr,
        )

        return 1

    try:
        workflow_run_input(run)
    except BenchmarkCaseSourceError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    feedback = None

    if expected is not None:
        expected_value = expected.value
    else:
        feedback = latest_corrected_output(
            SQLiteWorkflowRunFeedbackRepository(
                configuration.database,
            ).feedback_for_run(run_id)
        )

        if feedback is None:
            print(
                f"Run {run_id} has no corrected output; pass --expected.",
                file=sys.stderr,
            )

            return 1

        expected_value = feedback.corrected_output

    try:
        case = benchmark_case_from_run(
            run,
            comparison=comparison,
            expected=expected_value,
            description=description,
            feedback=feedback,
        )

        extended = dataset.with_case(case)
    except (
        BenchmarkCaseSourceError,
        BenchmarkCaseConflictError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    revision = benchmarks.save(extended)

    print(
        f"Added benchmark case {case.id} to benchmark dataset {benchmark_id} "
        f"revision {revision.number}."
    )

    return 0


__all__ = [
    "SuppliedExpectedValue",
    "add_benchmark_case",
]
