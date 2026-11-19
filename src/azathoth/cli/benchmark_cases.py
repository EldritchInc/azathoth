"""Benchmark case authoring commands for the Azathoth CLI.

`benchmark add-case` calls the service API (ADR 0130), so a case is made by
the same rules wherever it is added. A file is read here, as every command
reads a local file, and given to the API with the URI it was read from.
"""

import sys
from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.inputs import WorkflowInputFile, resolve_input_file
from azathoth.cli.persistence import repositories
from azathoth.cli.service import service_instance
from azathoth.evaluation import CitationExpectation, OutcomeComparison
from azathoth.inputs import InputResolutionError, InputSourceError
from azathoth.sensitivity import Sensitivity


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
    benchmarks = service_instance(configuration).benchmarks
    supplied: JsonValue | api.Keep = api.KEEP if expected is None else expected.value
    case_citations = (
        None
        if citations is None
        else api.CaseCitations(
            require=tuple(
                api.CitedSegmentSummary(source=cited.source, segment=cited.segment)
                for cited in citations.require
            ),
            on_unverified=citations.on_unverified,
        )
    )

    try:
        benchmarks.history(benchmark_id, limit=1)

        if input_file is None:
            change = benchmarks.add_case(
                benchmark_id,
                run_id=run_id,
                comparison=comparison.value,
                expected=supplied,
                description=description,
                citations=case_citations,
                sensitivity=sensitivity,
            )
        else:
            if expected is None:
                print(
                    "A case read from --input-file needs --expected.",
                    file=sys.stderr,
                )

                return 1

            read = _read(input_file, configuration)

            if read is None:
                return 1

            change = benchmarks.add_case(
                benchmark_id,
                file=read[0],
                file_uri=read[1],
                comparison=comparison.value,
                expected=supplied,
                description=description,
                citations=case_citations,
                sensitivity=sensitivity,
            )
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        f"Added benchmark case {change.case.case_id} to benchmark dataset {benchmark_id} "
        f"revision {change.benchmark.revision.number}."
    )

    return 0


def _read(
    input_file: WorkflowInputFile,
    configuration: CliRuntimeConfiguration,
) -> tuple[api.RunFile, str] | None:
    """Return a file's content and the URI it was read from, or report why it cannot be read.

    It is resolved as `workflow run --input-file` resolves a file, so it is
    refused with the same messages, before the API is given its content.
    """

    try:
        resolved = resolve_input_file(
            input_file,
            store=repositories(configuration).content,
        )
    except (
        InputSourceError,
        InputResolutionError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return None

    assert resolved.provenance is not None
    assert resolved.provenance.uri is not None

    return (
        api.RunFile(content=input_file.path.read_bytes(), media_type=resolved.media_type),
        resolved.provenance.uri,
    )


__all__ = [
    "SuppliedExpectedValue",
    "add_benchmark_case",
]
