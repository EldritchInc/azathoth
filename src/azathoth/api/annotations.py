"""A run's verified citations, exported as W3C Web Annotations (ADRs 0117 and 0129).

The checks are read from the records the run's journal names, so a run
still under way exports what its committed steps checked, and a run
recorded without a journal exports none. Only durable state is read.
"""

from typing import Final
from uuid import UUID

from pydantic import JsonValue

from azathoth import __version__
from azathoth.api.errors import ContentUnavailableError, NotFoundError
from azathoth.api.models import Annotations
from azathoth.citations import CitationRecord, citation_annotations
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import CitationCheckError, stored_citation_checks
from azathoth.workflows import journaled_citations

GENERATOR: Final = f"Azathoth {__version__}"
"""The software an exported annotation names as its generator."""


def run_citation_records(
    stored: Repositories,
    run_id: UUID,
) -> list[CitationRecord]:
    """Return every citations record one run's committed steps kept, with its checks.

    Raises:
        ContentUnavailableError: The content store no longer holds a record,
            or what it holds under a record's digest is not one.
    """

    records: list[CitationRecord] = []

    for step_id, digest in journaled_citations(stored.run_journal, run_id):
        try:
            checks = stored_citation_checks(stored.content, digest)
        except CitationCheckError as exc:
            raise ContentUnavailableError(str(exc)) from exc

        if checks is None:
            raise ContentUnavailableError(
                f"Citation record {digest} of step {step_id} is not in the content store."
            )

        records.append(CitationRecord(step_id=step_id, record=digest, checks=checks))

    return records


def run_annotations(
    stored: Repositories,
    run_id: UUID,
) -> Annotations:
    """Return one run's annotation collection.

    Raises:
        NotFoundError: The run was neither kept nor journaled.
        ContentUnavailableError: A record of its citations cannot be read.
    """

    if stored.runs.get(run_id) is None and not stored.run_journal.entries(run_id):
        raise NotFoundError(f"Run {run_id} was not found.")

    return _annotations(
        stored,
        run_id,
        subject_id=run_id,
        command=f"azathoth run annotations {run_id}",
    )


def invocation_annotations(
    stored: Repositories,
    invocation_id: UUID,
) -> Annotations:
    """Return the annotation collection of one invocation's run.

    Raises:
        NotFoundError: The invocation is unknown, or has no run yet.
        ContentUnavailableError: A record of its run's citations cannot be read.
    """

    if stored.invocations.get(invocation_id) is None:
        raise NotFoundError(f"Invocation {invocation_id} was not found.")

    association = stored.invocation_runs.get(invocation_id)
    run_id = (
        association.run_id
        if association is not None
        else stored.run_journal.invocation_run_id(invocation_id)
    )

    if run_id is None:
        raise NotFoundError(f"Invocation {invocation_id} has no run.")

    return _annotations(
        stored,
        run_id,
        subject_id=invocation_id,
        command=f"azathoth invocation annotations {invocation_id}",
    )


def _annotations(
    stored: Repositories,
    run_id: UUID,
    *,
    subject_id: UUID,
    command: str,
) -> Annotations:
    """Return a run's annotation collection, and its annotations, for what was asked about."""

    collection = citation_annotations(
        run_id, run_citation_records(stored, run_id), generator=GENERATOR
    )

    return Annotations(
        subject_id=subject_id,
        run_id=run_id,
        collection=collection,
        items=_items(collection),
        command=command,
    )


def _items(
    collection: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], ...]:
    """Return the annotations of a collection's one page, or none when it has none."""

    page = collection.get("first")
    items = page.get("items") if isinstance(page, dict) else None

    if not isinstance(items, list):
        return ()

    return tuple(item for item in items if isinstance(item, dict))


__all__ = [
    "GENERATOR",
    "invocation_annotations",
    "run_annotations",
    "run_citation_records",
]
