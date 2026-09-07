"""Durable benchmark inspection commands for the Azathoth CLI."""

import json
import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    SQLiteBenchmarkRepository,
)


def list_benchmarks() -> int:
    """List durable benchmark datasets."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteBenchmarkRepository(
        configuration.database,
    )

    for dataset in repository.datasets():
        print(f"{dataset.id}  {dataset.version}  {dataset.name}")

    return 0


def show_benchmark(
    benchmark_id: UUID,
) -> int:
    """Show one durable benchmark dataset."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteBenchmarkRepository(
        configuration.database,
    )

    dataset = repository.get(
        benchmark_id,
    )

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    _print_benchmark_dataset(
        dataset,
    )

    return 0


def list_benchmark_cases(
    benchmark_id: UUID,
) -> int:
    """List cases belonging to one durable benchmark dataset."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteBenchmarkRepository(
        configuration.database,
    )

    dataset = repository.get(
        benchmark_id,
    )

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    for case in dataset.cases:
        print(f"{case.id}  {case.expected.description}")

    return 0


def show_benchmark_case(
    benchmark_id: UUID,
    case_id: UUID,
) -> int:
    """Show one case from one durable benchmark dataset."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteBenchmarkRepository(
        configuration.database,
    )

    dataset = repository.get(
        benchmark_id,
    )

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    case = next(
        (candidate for candidate in dataset.cases if candidate.id == case_id),
        None,
    )

    if case is None:
        print(
            f"Benchmark case {case_id} is not configured in dataset {benchmark_id}.",
            file=sys.stderr,
        )

        return 1

    _print_benchmark_case(
        case,
    )

    return 0


def _print_benchmark_dataset(
    dataset: BenchmarkDataset,
) -> None:
    """Render one durable reusable benchmark workload."""

    print(f"ID: {dataset.id}")
    print(f"Name: {dataset.name}")
    print(f"Version: {dataset.version}")
    print(f"Description: {dataset.description}")
    print(f"Cases: {len(dataset.cases)}")


def _print_benchmark_case(
    case: BenchmarkCase,
) -> None:
    """Render one durable benchmark case."""

    print(f"ID: {case.id}")

    print("Input:")
    print(
        json.dumps(
            case.input,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("Expected:")
    print(f"  Description: {case.expected.description}")
    print(f"  Comparison: {case.expected.comparison.value}")
    print("  Value:")
    print(
        _indent(
            json.dumps(
                case.expected.value,
                ensure_ascii=False,
                indent=2,
            ),
            prefix="    ",
        )
    )

    print("Metadata:")
    print(
        json.dumps(
            case.metadata,
            ensure_ascii=False,
            indent=2,
        )
    )


def _indent(
    value: str,
    *,
    prefix: str,
) -> str:
    """Indent every line of one rendered value."""

    return "\n".join(f"{prefix}{line}" for line in value.splitlines())


__all__ = [
    "list_benchmark_cases",
    "list_benchmarks",
    "show_benchmark",
    "show_benchmark_case",
]
