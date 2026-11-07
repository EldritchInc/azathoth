"""Export the citations a run checked as W3C Web Annotations (ADR 0117)."""

import json
import sys
from uuid import UUID

from azathoth import __version__
from azathoth.citations import CitationRecord, citation_annotations
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import CitationCheckError, stored_citation_checks
from azathoth.workflows import journaled_citations

GENERATOR: str = f"Azathoth {__version__}"
"""The software an exported annotation names as its generator."""


class AnnotationExportError(ValueError):
    """Raised when a run's citations cannot be exported."""


def export_run_annotations(
    run_id: UUID,
) -> int:
    """Print every verified check one run's cited steps kept, as Web Annotations.

    The checks are read from the records the run's journal names, so a run
    still under way exports what its committed steps checked. Only durable
    state is read.
    """

    stored = repositories(CliRuntimeConfiguration.from_environment())

    if stored.runs.get(run_id) is None and not stored.run_journal.entries(run_id):
        print(f"Run {run_id} was not found.", file=sys.stderr)

        return 1

    return _print_annotations(stored, run_id)


def export_invocation_annotations(
    invocation_id: UUID,
) -> int:
    """Print every verified check one invocation's run kept, as Web Annotations."""

    stored = repositories(CliRuntimeConfiguration.from_environment())

    if stored.invocations.get(invocation_id) is None:
        print(f"Invocation {invocation_id} was not found.", file=sys.stderr)

        return 1

    association = stored.invocation_runs.get(invocation_id)
    run_id = (
        association.run_id
        if association is not None
        else stored.run_journal.invocation_run_id(invocation_id)
    )

    if run_id is None:
        print(f"Invocation {invocation_id} has no run.", file=sys.stderr)

        return 1

    return _print_annotations(stored, run_id)


def run_citation_records(
    stored: Repositories,
    run_id: UUID,
) -> list[CitationRecord]:
    """Return every citations record one run's committed steps kept, with its checks.

    Raises:
        AnnotationExportError: The content store no longer holds a record,
            or what it holds under a record's digest is not one.
    """

    records: list[CitationRecord] = []

    for step_id, digest in journaled_citations(stored.run_journal, run_id):
        try:
            checks = stored_citation_checks(stored.content, digest)
        except CitationCheckError as exc:
            raise AnnotationExportError(str(exc)) from exc

        if checks is None:
            raise AnnotationExportError(
                f"Citation record {digest} of step {step_id} is not in the content store."
            )

        records.append(CitationRecord(step_id=step_id, record=digest, checks=checks))

    return records


def _print_annotations(
    stored: Repositories,
    run_id: UUID,
) -> int:
    """Print one run's annotation collection, or report why it cannot be made."""

    try:
        records = run_citation_records(stored, run_id)
    except AnnotationExportError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        json.dumps(
            citation_annotations(run_id, records, generator=GENERATOR),
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


__all__ = [
    "GENERATOR",
    "AnnotationExportError",
    "export_invocation_annotations",
    "export_run_annotations",
    "run_citation_records",
]
