"""A benchmark's cases as the service API shows and changes them (ADR 0130).

Every case is read from one revision of its benchmark, so a case is always
named with the revision it was read from. Where a case came from is read
from what made it: a recorded run names itself in the case's metadata, and
a file in its input's provenance (ADRs 0086 and 0117).

An edit changes what a case expects and how it is judged, never its ID,
its input or where it came from, and its label only ever rises (ADR 0123).
"""

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Final
from uuid import UUID

from pydantic import JsonValue, ValidationError

from azathoth.api.errors import (
    ConflictError,
    ContentUnavailableError,
    InvalidArgumentError,
    NotFoundError,
)
from azathoth.api.models import (
    BenchmarkCaseDetail,
    BenchmarkCaseSummary,
    CaseCitations,
    CaseComparison,
    CaseSource,
    CitedSegmentSummary,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDatasetRevision,
    CitationExpectation,
    CitedSegment,
    ExpectedOutcome,
    OutcomeComparison,
    json_schema_validator,
    json_values_equal,
)
from azathoth.inputs import ResolvedInput, is_binary_media_type
from azathoth.persistence.repositories import Repositories
from azathoth.sensitivity import Sensitivity, effective_sensitivity, stored_sensitivity
from azathoth.workflows import (
    SOURCE_FEEDBACK_METADATA_KEY,
    SOURCE_RUN_METADATA_KEY,
    BenchmarkCaseSourceError,
    benchmark_case_from_input,
    benchmark_case_from_run,
    latest_corrected_output,
    workflow_run_input,
)


class Keep(Enum):
    """What an edit is given for a field it leaves as it is."""

    KEEP = "keep"


KEEP: Final = Keep.KEEP
"""Leave a field of a case as it is: a value may be JSON null, so None cannot say so."""

COMPARISONS: Final = tuple(comparison.value for comparison in OutcomeComparison)
"""Every comparison a case may judge by."""


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


def required_text(
    value: str,
    what: str,
) -> str:
    """Return a value without its surrounding spaces, refusing a blank one.

    Raises:
        InvalidArgumentError: The value is blank.
    """

    stripped = value.strip()

    if not stripped:
        raise InvalidArgumentError(f"{what} must not be blank.")

    return stripped


def comparison_of(
    value: CaseComparison,
) -> OutcomeComparison:
    """Return the comparison a case judges by, refusing one Azathoth has none of.

    Raises:
        InvalidArgumentError: No comparison has this name.
    """

    try:
        return OutcomeComparison(value)
    except ValueError as exc:
        raise InvalidArgumentError(
            f"comparison must be one of {', '.join(COMPARISONS)}, not {value!r}."
        ) from exc


def citation_expectation(
    citations: CaseCitations | None,
) -> CitationExpectation | None:
    """Return what a case's run must cite, from the API's view of it.

    Raises:
        InvalidArgumentError: A segment is named twice, or a name is empty.
    """

    if citations is None:
        return None

    try:
        return CitationExpectation(
            require=tuple(
                CitedSegment(source=cited.source, segment=cited.segment)
                for cited in citations.require
            ),
            on_unverified=citations.on_unverified,
        )
    except ValidationError as exc:
        raise InvalidArgumentError(_first_message(exc)) from exc


def checked_expected_value(
    comparison: OutcomeComparison,
    expected: JsonValue,
) -> None:
    """Refuse an expected value its comparison cannot use: a schema must be a JSON Schema.

    Raises:
        InvalidArgumentError: The comparison is `schema`, and the value is
            not a valid JSON Schema.
    """

    if comparison is not OutcomeComparison.SCHEMA:
        return

    try:
        json_schema_validator(expected)
    except ValueError as exc:
        raise InvalidArgumentError(
            f"Expected value cannot be used with comparison 'schema': {exc}"
        ) from exc


def edited_case(
    case: BenchmarkCase,
    *,
    comparison: CaseComparison | None,
    expected: JsonValue | Keep,
    description: str | None,
    citations: CaseCitations | None | Keep,
    sensitivity: Sensitivity | None,
) -> BenchmarkCase:
    """Return a case with what an edit gives it, and everything else as it was.

    A new expected value is no longer the corrected output of the judgment
    the case was made from, so the case stops naming that judgment.

    Raises:
        InvalidArgumentError: The edit changes nothing, a description is
            blank, a comparison is unknown or cannot use the expected value,
            a citation is malformed, or the label is lower than the case's.
    """

    if (
        comparison is None
        and isinstance(expected, Keep)
        and description is None
        and isinstance(citations, Keep)
        and sensitivity is None
    ):
        raise InvalidArgumentError(
            f"An edit of benchmark case {case.id} changes nothing: give it a comparison, an "
            "expected value, a description, citations or a label."
        )

    outcome = case.expected
    judged_by = outcome.comparison if comparison is None else comparison_of(comparison)
    value = outcome.value if isinstance(expected, Keep) else expected

    checked_expected_value(judged_by, value)

    current = effective_sensitivity(case.sensitivity)
    label = current if sensitivity is None else sensitivity

    if label.rank < current.rank:
        raise InvalidArgumentError(
            f"Benchmark case {case.id} is {current.value}; an edit cannot label it {label.value}."
        )

    metadata = (
        case.metadata
        if isinstance(expected, Keep)
        else {
            key: kept for key, kept in case.metadata.items() if key != SOURCE_FEEDBACK_METADATA_KEY
        }
    )

    try:
        return BenchmarkCase(
            id=case.id,
            input=case.input,
            input_provenance=case.input_provenance,
            sensitivity=stored_sensitivity(label),
            expected=ExpectedOutcome(
                description=(
                    outcome.description
                    if description is None
                    else required_text(description, "A case's description")
                ),
                value=value,
                comparison=judged_by,
                citations=(
                    outcome.citations
                    if isinstance(citations, Keep)
                    else citation_expectation(citations)
                ),
            ),
            metadata=metadata,
        )
    except ValidationError as exc:
        raise InvalidArgumentError(_first_message(exc)) from exc


def check_not_duplicated(
    benchmark_id: UUID,
    cases: Iterable[BenchmarkCase],
    case: BenchmarkCase,
) -> None:
    """Refuse a case another case of the benchmark already is, as `benchmark add-case` does.

    Raises:
        ConflictError: Another case has a JSON-equal input, the same
            comparison and a JSON-equal expected value.
    """

    for existing in cases:
        if (
            existing.id != case.id
            and existing.expected.comparison is case.expected.comparison
            and json_values_equal(existing.input, case.input)
            and json_values_equal(existing.expected.value, case.expected.value)
        ):
            raise ConflictError(
                f"Benchmark dataset {benchmark_id} already contains case {existing.id} "
                "with this input and expected outcome."
            )


def case_from_run(
    repositories: Repositories,
    run_id: UUID,
    *,
    comparison: OutcomeComparison,
    expected: JsonValue | Keep,
    description: str | None,
    citations: CitationExpectation | None,
    sensitivity: Sensitivity | None,
) -> BenchmarkCase:
    """Return the case replaying one recorded run's input, as `benchmark add-case` makes it.

    Without an expected value, it expects the corrected output of the run's
    latest bad judgment that carries one (ADR 0086); good feedback never
    supplies one. A run given a PDF or an image is refused once the content
    store no longer holds its content (ADR 0117).

    Raises:
        NotFoundError: No run was kept with this ID.
        InvalidArgumentError: The run received no input, or input more than
            once; it has no correction and no expected value is given; or
            the label is lower than the run's.
        ContentUnavailableError: The content store no longer holds the
            content the run received.
    """

    run = repositories.runs.get(run_id)

    if run is None:
        raise NotFoundError(f"Run {run_id} was not found.")

    feedback = None

    try:
        workflow_run_input(run)

        if isinstance(expected, Keep):
            feedback = latest_corrected_output(repositories.feedback.feedback_for_run(run_id))

            if feedback is None:
                raise InvalidArgumentError(
                    f"Run {run_id} has no corrected output; pass --expected."
                )

            expected = feedback.corrected_output

        case = benchmark_case_from_run(
            run,
            comparison=comparison,
            expected=expected,
            description=description,
            feedback=feedback,
            citations=citations,
            sensitivity=sensitivity,
        )
    except BenchmarkCaseSourceError as exc:
        raise InvalidArgumentError(str(exc)) from exc

    provenance = case.input_provenance

    if (
        provenance is not None
        and is_binary_media_type(provenance.media_type)
        and not repositories.content.contains(provenance.digest)
    ):
        raise ContentUnavailableError(
            f"Run {run_id} received content {provenance.digest}, which the content store "
            "no longer holds."
        )

    return case


def case_from_input(
    resolved: ResolvedInput,
    *,
    comparison: OutcomeComparison,
    expected: JsonValue | Keep,
    description: str | None,
    citations: CitationExpectation | None,
    sensitivity: Sensitivity | None,
) -> BenchmarkCase:
    """Return the case of one resolved input: JSON given as it is, or a file's.

    It is internal without a label (ADR 0123), and needs an expected value.

    Raises:
        InvalidArgumentError: No expected value is given, or it cannot be
            used with its comparison.
    """

    if isinstance(expected, Keep):
        raise InvalidArgumentError(
            "A case made from JSON or a file needs an expected value: only a run's judgment "
            "can supply one."
        )

    try:
        return benchmark_case_from_input(
            resolved.model_copy(update={"sensitivity": sensitivity}),
            comparison=comparison,
            expected=expected,
            description=description,
            citations=citations,
        )
    except BenchmarkCaseSourceError as exc:
        raise InvalidArgumentError(str(exc)) from exc


def _first_message(
    error: ValidationError,
) -> str:
    """Return the first reason a model refused its values, as a sentence."""

    return str(error.errors()[0]["msg"]).removeprefix("Value error, ")


__all__ = [
    "COMPARISONS",
    "KEEP",
    "Keep",
    "case_detail",
    "case_from_input",
    "case_from_run",
    "case_not_found_message",
    "case_summary",
    "check_not_duplicated",
    "checked_expected_value",
    "citation_expectation",
    "comparison_of",
    "edited_case",
    "required_text",
]
