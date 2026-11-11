"""Benchmark case authoring commands for the Azathoth CLI."""

import sys
from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.inputs import WorkflowInputFile, resolve_input_file
from azathoth.cli.persistence import repositories
from azathoth.cli.service import current_author
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCaseConflictError,
    CitationExpectation,
    OutcomeComparison,
)
from azathoth.inputs import (
    ContentStore,
    InputResolutionError,
    InputSourceError,
    is_binary_media_type,
)
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import (
    BenchmarkCaseSourceError,
    benchmark_case_from_input,
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
    run_id: UUID | None = None,
    input_file: WorkflowInputFile | None = None,
    sensitivity: Sensitivity | None = None,
    comparison: OutcomeComparison,
    expected: SuppliedExpectedValue | None = None,
    description: str | None = None,
    citations: CitationExpectation | None = None,
) -> int:
    """Append a case replaying one recorded run's input, or one file, as a new revision.

    A case from a run expects the supplied value. Without one, it expects the
    corrected output of the run's latest bad feedback that carries a
    correction; good feedback never supplies a value. A run given a PDF or an
    image becomes a case holding its handle and provenance, as long as the
    content store still holds the content (ADR 0117).

    A case from a file holds the file's content, kept in the content store as
    `workflow run --input-file` keeps it, and needs a supplied value. The
    benchmark need not belong to any one workflow, because any workflow can
    run against any benchmark. Either case may name what its run must cite.

    `sensitivity` labels the case (ADR 0123). A case from a run takes the
    run's label without one, and is refused one lower than the run's; a case
    from a file is internal without one.

    Nothing is written to the benchmark when any check fails. Only durable
    state is read, so the runtime is never loaded and no provider credentials
    are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    benchmarks = repositories(configuration).benchmarks

    dataset = benchmarks.get(benchmark_id)

    if dataset is None:
        print(
            f"Benchmark dataset {benchmark_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    if input_file is not None:
        case = _case_from_file(
            input_file,
            sensitivity=sensitivity,
            configuration=configuration,
            comparison=comparison,
            expected=expected,
            description=description,
            citations=citations,
        )
    else:
        assert run_id is not None

        case = _case_from_run(
            run_id,
            sensitivity=sensitivity,
            configuration=configuration,
            comparison=comparison,
            expected=expected,
            description=description,
            citations=citations,
        )

    if case is None:
        return 1

    try:
        extended = dataset.with_case(case)
    except BenchmarkCaseConflictError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    author = current_author()

    if author is None:
        return 1

    revision = benchmarks.save(extended, author=author)

    print(
        f"Added benchmark case {case.id} to benchmark dataset {benchmark_id} "
        f"revision {revision.number}."
    )

    return 0


def _case_from_run(
    run_id: UUID,
    *,
    sensitivity: Sensitivity | None,
    configuration: CliRuntimeConfiguration,
    comparison: OutcomeComparison,
    expected: SuppliedExpectedValue | None,
    description: str | None,
    citations: CitationExpectation | None,
) -> BenchmarkCase | None:
    """Return the case replaying one recorded run's input, or report why there is none."""

    run = repositories(configuration).runs.get(run_id)

    if run is None:
        print(
            f"Run {run_id} was not found.",
            file=sys.stderr,
        )

        return None

    try:
        workflow_run_input(run)
    except BenchmarkCaseSourceError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return None

    feedback = None

    if expected is not None:
        expected_value = expected.value
    else:
        feedback = latest_corrected_output(
            repositories(configuration).feedback.feedback_for_run(run_id)
        )

        if feedback is None:
            print(
                f"Run {run_id} has no corrected output; pass --expected.",
                file=sys.stderr,
            )

            return None

        expected_value = feedback.corrected_output

    try:
        case = benchmark_case_from_run(
            run,
            comparison=comparison,
            expected=expected_value,
            description=description,
            feedback=feedback,
            citations=citations,
            sensitivity=sensitivity,
        )
    except BenchmarkCaseSourceError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return None

    if not _content_kept(case, repositories(configuration).content):
        assert case.input_provenance is not None

        print(
            f"Run {run_id} received content {case.input_provenance.digest}, which the "
            "content store no longer holds.",
            file=sys.stderr,
        )

        return None

    return case


def _case_from_file(
    input_file: WorkflowInputFile,
    *,
    sensitivity: Sensitivity | None,
    configuration: CliRuntimeConfiguration,
    comparison: OutcomeComparison,
    expected: SuppliedExpectedValue | None,
    description: str | None,
    citations: CitationExpectation | None,
) -> BenchmarkCase | None:
    """Return the case of one input file, keeping its content, or report why there is none."""

    if expected is None:
        print(
            "A case read from --input-file needs --expected.",
            file=sys.stderr,
        )

        return None

    try:
        resolved = resolve_input_file(
            input_file,
            store=repositories(configuration).content,
        )

        return benchmark_case_from_input(
            resolved.model_copy(update={"sensitivity": sensitivity}),
            comparison=comparison,
            expected=expected.value,
            description=description,
            citations=citations,
        )
    except (
        InputSourceError,
        InputResolutionError,
        BenchmarkCaseSourceError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return None


def _content_kept(
    case: BenchmarkCase,
    store: ContentStore,
) -> bool:
    """Return whether the content store holds the content a case is given, if any."""

    provenance = case.input_provenance

    return (
        provenance is None
        or not is_binary_media_type(provenance.media_type)
        or store.contains(provenance.digest)
    )


__all__ = [
    "SuppliedExpectedValue",
    "add_benchmark_case",
]
