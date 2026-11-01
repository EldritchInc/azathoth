"""Durable benchmark inspection commands for the Azathoth CLI."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.benchmark_checks import (
    comparisons_supported,
    configured_benchmark,
    results_declared,
)
from azathoth.cli.benchmark_execution import (
    compare_configured_benchmarks,
    execute_configured_benchmark,
)
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering import (
    render_workflow_benchmark_comparison_execution,
    render_workflow_benchmark_execution,
    render_workflow_benchmark_execution_summaries,
    render_workflow_benchmark_result,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDatasetRevision,
    BenchmarkDocumentError,
    BenchmarkRepository,
    SemanticJudgingError,
    UnsupportedComparisonError,
    decode_benchmark_document,
    earliest_identical_benchmark_revision,
    encode_benchmark_document,
)
from azathoth.runtime import (
    JudgeUnavailableError,
    WorkflowNotConfiguredError,
)
from azathoth.workflows import (
    WorkflowBenchmarkEvidenceRecorder,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowScoringPolicy,
)


def list_benchmarks() -> int:
    """List durable benchmark datasets."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = repositories(configuration).benchmarks

    for dataset in repository.datasets():
        print(f"{dataset.id}  {dataset.version}  {dataset.name}")

    return 0


def show_benchmark(
    benchmark_id: UUID,
    *,
    revision: int | None = None,
) -> int:
    """Show one imported revision of a benchmark dataset, the latest by default."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = repositories(configuration).benchmarks

    selected = _selected_revision(
        repository,
        benchmark_id,
        revision,
    )

    if selected is None:
        return 1

    latest = repository.latest_revision(benchmark_id)

    _print_benchmark_dataset(
        selected,
        latest_number=latest.number if latest is not None else selected.number,
    )

    return 0


def export_benchmark(
    benchmark_id: UUID,
    *,
    revision: int | None = None,
) -> int:
    """Print one imported benchmark revision as an importable JSON document.

    Importing the output again appends a revision with identical content.
    Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    selected = _selected_revision(
        repositories(configuration).benchmarks,
        benchmark_id,
        revision,
    )

    if selected is None:
        return 1

    print(encode_benchmark_document(selected.dataset))

    return 0


def list_benchmark_history(
    benchmark_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List the imported revisions of one benchmark, newest first.

    Each line contains the revision number, import time, the first twelve
    characters of the content digest, the declared version, the case count,
    and the name. A revision with the same content as an earlier one names
    the earliest such revision. Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    history = repositories(configuration).benchmarks.revisions(benchmark_id)

    if not history:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    newest_first = tuple(reversed(history))

    if limit is not None:
        newest_first = newest_first[:limit]

    for selected in newest_first:
        identical = earliest_identical_benchmark_revision(
            history,
            selected,
        )

        note = f"  identical to revision {identical.number}" if identical is not None else ""

        dataset = selected.dataset

        print(
            f"{selected.number}  {_render_imported_at(selected)}  "
            f"{selected.content_digest[:12]}  {dataset.version}  "
            f"{len(dataset.cases)} cases  {dataset.name}{note}"
        )

    return 0


def _selected_revision(
    repository: BenchmarkRepository,
    benchmark_id: UUID,
    revision: int | None,
) -> BenchmarkDatasetRevision | None:
    """Return the requested revision, printing the failure when there is none."""

    latest = repository.latest_revision(benchmark_id)

    if latest is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return None

    if revision is None:
        return latest

    selected = repository.revision(
        benchmark_id,
        revision,
    )

    if selected is None:
        print(
            f"Benchmark dataset {benchmark_id} has no revision {revision}.",
            file=sys.stderr,
        )

    return selected


def _render_imported_at(
    revision: BenchmarkDatasetRevision,
) -> str:
    """Render when one revision was imported, or that it is unknown."""

    if revision.imported_at is None:
        return "unknown"

    return revision.imported_at.isoformat()


def list_benchmark_cases(
    benchmark_id: UUID,
) -> int:
    """List cases belonging to one durable benchmark dataset."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = repositories(configuration).benchmarks

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

    repository = repositories(configuration).benchmarks

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
    revision: BenchmarkDatasetRevision,
    *,
    latest_number: int,
) -> None:
    """Render one imported revision of a reusable benchmark workload."""

    dataset = revision.dataset

    print(f"ID: {dataset.id}")
    print(f"Revision: {revision.number} of {latest_number}")
    print(f"Imported: {_render_imported_at(revision)}")
    print(f"Content Digest: {revision.content_digest}")
    print(f"Name: {dataset.name}")
    print(f"Version: {dataset.version}")
    print(f"Description: {dataset.description}")
    print(f"Cases: {len(dataset.cases)}")

    counts = dataset.comparison_counts()

    print(
        "Comparisons: "
        + (
            ", ".join(f"{comparison.value} {count}" for comparison, count in counts.items())
            or "none"
        )
    )


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
    """Import one durable benchmark dataset from a JSON document.

    Importing never replaces anything: each import appends the next revision
    under the document's benchmark ID. Re-importing earlier content is
    reported as identical to the earliest revision with the same content.
    """

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

    repository = repositories(configuration).benchmarks

    saved = repository.save(
        dataset,
    )

    identical = earliest_identical_benchmark_revision(
        repository.revisions(dataset.id),
        saved,
    )

    note = f" (identical to revision {identical.number})" if identical is not None else ""

    print(f"Imported benchmark dataset {dataset.id} revision {saved.number}{note}.")

    return 0


def run_benchmark(
    *,
    benchmark_id: UUID,
    workflow_id: UUID,
) -> int:
    """Execute one configured workflow against a durable benchmark.

    Each case judges the workflow's declared result. Unsupported comparisons
    and workflows without a declared result are rejected before runtime
    bootstrap, without executing any case. Every case run, every evaluation,
    and one execution record are saved, and the execution identifier leads
    the output.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    dataset = configured_benchmark(
        configuration,
        benchmark_id,
    )

    if dataset is None:
        return 1

    if not comparisons_supported(
        configuration,
        dataset,
    ):
        return 1

    if not results_declared(
        configuration,
        (workflow_id,),
    ):
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
                recorder=_benchmark_recorder(configuration),
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        JudgeUnavailableError,
        UnsupportedComparisonError,
        SemanticJudgingError,
        WorkflowResultError,
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
            execution_id=result.id,
        )
    )

    return 0


def compare_benchmarks(
    *,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
    target_latency_seconds: float,
    target_cost_usd: float,
) -> int:
    """Compare configured workflows against a durable benchmark.

    Each case judges every workflow's declared result. Unsupported
    comparisons and workflows without a declared result are rejected before
    runtime bootstrap, without executing any case. Every case run, every
    evaluation, and one execution record are saved, and the comparison is
    rendered from that saved record.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    dataset = configured_benchmark(
        configuration,
        benchmark_id,
    )

    if dataset is None:
        return 1

    if not comparisons_supported(
        configuration,
        dataset,
    ):
        return 1

    if not results_declared(
        configuration,
        workflow_ids,
    ):
        return 1

    runtime = load_runtime(
        configuration,
    )

    recorder = _benchmark_recorder(configuration)

    try:
        ranking = asyncio.run(
            compare_configured_benchmarks(
                runtime=runtime,
                workflow_ids=workflow_ids,
                dataset=dataset,
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=target_latency_seconds,
                    target_cost_usd=target_cost_usd,
                ),
                recorder=recorder,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        JudgeUnavailableError,
        ValueError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    execution = recorder.executions.get(ranking.id)

    if execution is None:
        print(
            f"Benchmark execution {ranking.id} was not recorded.",
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_benchmark_comparison_execution(
            execution,
        )
    )

    return 0


def list_benchmark_executions(
    benchmark_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List saved runs and comparisons of one benchmark, newest first.

    Executions are listed for benchmarks that are configured or that have
    saved executions, so executions of a benchmark since removed remain
    inspectable. An identifier with neither fails, so a mistyped identifier
    is not mistaken for a benchmark that never ran. Only durable state is
    read, so no provider credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    execution_repository = repositories(configuration).benchmark_executions

    executions = execution_repository.executions_for_benchmark(benchmark_id)

    if not executions and repositories(configuration).benchmarks.get(benchmark_id) is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    newest_first = sorted(
        reversed(executions),
        key=lambda execution: execution.recorded_at,
        reverse=True,
    )

    if limit is not None:
        newest_first = newest_first[:limit]

    if not newest_first:
        return 0

    print(render_workflow_benchmark_execution_summaries(newest_first))

    return 0


def show_benchmark_execution(
    execution_id: UUID,
) -> int:
    """Show one saved benchmark run or comparison with every candidate and case.

    Only durable state is read, so no provider credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    execution = repositories(configuration).benchmark_executions.get(execution_id)

    if execution is None:
        print(
            f"Benchmark execution {execution_id} was not found.",
            file=sys.stderr,
        )

        return 1

    print(render_workflow_benchmark_execution(execution))

    return 0


def _benchmark_recorder(
    configuration: CliRuntimeConfiguration,
) -> WorkflowBenchmarkEvidenceRecorder:
    """Return the recorder that saves benchmark evidence to the configured database."""

    return WorkflowBenchmarkEvidenceRecorder(
        runs=repositories(configuration).runs,
        evaluations=repositories(configuration).run_evaluations,
        executions=repositories(configuration).benchmark_executions,
    )


__all__ = [
    "compare_benchmarks",
    "export_benchmark",
    "import_benchmark",
    "list_benchmark_history",
    "list_benchmark_cases",
    "list_benchmark_executions",
    "list_benchmarks",
    "render_workflow_benchmark_result",
    "show_benchmark",
    "show_benchmark_case",
    "show_benchmark_execution",
]
