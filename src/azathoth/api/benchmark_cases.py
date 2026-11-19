"""A benchmark's cases as the service API shows them (ADR 0130).

Every case is read from one revision of its benchmark, so a case is always
named with the revision it was read from. Where a case came from is read
from what made it: a recorded run names itself in the case's metadata, and
a file in its input's provenance (ADRs 0086 and 0117).
"""

from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.models import (
    BenchmarkCaseDetail,
    BenchmarkCaseSummary,
    CaseCitations,
    CaseSource,
    CitedSegmentSummary,
)
from azathoth.evaluation import BenchmarkCase, BenchmarkDatasetRevision
from azathoth.sensitivity import effective_sensitivity
from azathoth.workflows import SOURCE_FEEDBACK_METADATA_KEY, SOURCE_RUN_METADATA_KEY


def case_not_found_message(
    benchmark_id: UUID,
    case_id: UUID,
) -> str:
    """Return what a case a benchmark revision does not hold is refused with."""

    return f"Benchmark case {case_id} is not configured in dataset {benchmark_id}."


def _named_id(
    metadata: Mapping[str, JsonValue],
    key: str,
) -> UUID | None:
    """Return the ID a case's metadata names under `key`, or None when it names none."""

    value = metadata.get(key)

    if not isinstance(value, str):
        return None

    try:
        return UUID(value)
    except ValueError:
        return None


def _source(
    case: BenchmarkCase,
) -> CaseSource:
    """Return where a case came from: a run, a file, or JSON given as it is."""

    if _named_id(case.metadata, SOURCE_RUN_METADATA_KEY) is not None:
        return "run"

    if case.input_provenance is not None:
        return "file"

    return "json"


def case_summary(
    selected: BenchmarkDatasetRevision,
    case: BenchmarkCase,
) -> BenchmarkCaseSummary:
    """Return the API's view of one case of one benchmark revision."""

    return BenchmarkCaseSummary(
        benchmark_id=selected.dataset_id,
        revision=selected.number,
        case_id=case.id,
        description=case.expected.description,
        comparison=case.expected.comparison.value,
        sensitivity=effective_sensitivity(case.sensitivity),
        source=_source(case),
        source_run_id=_named_id(case.metadata, SOURCE_RUN_METADATA_KEY),
        cited=case.expected.citations is not None,
        command=f"azathoth benchmark case-show {selected.dataset_id} {case.id}",
    )


def case_detail(
    selected: BenchmarkDatasetRevision,
    case: BenchmarkCase,
) -> BenchmarkCaseDetail:
    """Return one case of one benchmark revision with its input and expected outcome."""

    citations = case.expected.citations

    return BenchmarkCaseDetail(
        **case_summary(selected, case).model_dump(),
        input=case.input,
        input_provenance=(
            None if case.input_provenance is None else case.input_provenance.model_dump(mode="json")
        ),
        expected=case.expected.value,
        citations=(
            None
            if citations is None
            else CaseCitations(
                require=tuple(
                    CitedSegmentSummary(source=cited.source, segment=cited.segment)
                    for cited in citations.require
                ),
                on_unverified=citations.on_unverified,
            )
        ),
        source_feedback_id=_named_id(case.metadata, SOURCE_FEEDBACK_METADATA_KEY),
        metadata=case.metadata,
    )


__all__ = [
    "case_detail",
    "case_not_found_message",
    "case_summary",
]
