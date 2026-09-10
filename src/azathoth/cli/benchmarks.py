"""Durable benchmark inspection commands for the Azathoth CLI."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.benchmark_execution import (
    compare_configured_benchmarks,
    execute_configured_benchmark,
)
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_workflow_benchmark_ranking,
    render_workflow_benchmark_result,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkDocumentError,
    SQLiteBenchmarkRepository,
    decode_benchmark_document,
)
from azathoth.runtime import WorkflowNotConfiguredError
from azathoth.workflows import (
    WorkflowGenerationError,
    WorkflowScoringPolicy,
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


def import_benchmark(
    document_path: Path,
) -> int:
    """Import one durable benchmark dataset from a JSON document."""

    try:
        document = document_path.read_text(
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Unable to read benchmark document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    try:
        dataset = decode_benchmark_document(
            document,
        )
    except BenchmarkDocumentError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteBenchmarkRepository(
        configuration.database,
    )

    try:
        repository.save(
            dataset,
        )
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Imported benchmark dataset {dataset.id}.")

    return 0


def run_benchmark(
    *,
    benchmark_id: UUID,
    workflow_id: UUID,
    output_name: str,
) -> int:
    """Execute one configured workflow against a durable benchmark."""

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

    runtime = load_runtime(
        configuration,
    )

    try:
        result = asyncio.run(
            execute_configured_benchmark(
                runtime=runtime,
                workflow_id=workflow_id,
                dataset=dataset,
                output_name=output_name,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_benchmark_result(
            result,
            workflow_id=workflow_id,
        )
    )

    return 0


def compare_benchmarks(
    *,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
    output_name: str,
    target_latency_seconds: float,
    target_cost_usd: float,
) -> int:
    """Compare configured workflows against a durable benchmark."""

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

    runtime = load_runtime(
        configuration,
    )

    try:
        ranking = asyncio.run(
            compare_configured_benchmarks(
                runtime=runtime,
                workflow_ids=workflow_ids,
                dataset=dataset,
                output_name=output_name,
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=target_latency_seconds,
                    target_cost_usd=target_cost_usd,
                ),
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        ValueError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_benchmark_ranking(
            ranking,
            benchmark_id=benchmark_id,
        )
    )

    return 0


__all__ = [
    "compare_benchmarks",
    "import_benchmark",
    "list_benchmark_cases",
    "list_benchmarks",
    "render_workflow_benchmark_result",
    "show_benchmark",
    "show_benchmark_case",
]
