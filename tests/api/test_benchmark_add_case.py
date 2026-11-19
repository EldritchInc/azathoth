"""Contract tests for adding a case to a benchmark, and turning a run into one (ADR 0130)."""

from uuid import UUID

import pytest

from azathoth import api
from azathoth.context import create_input_sensitivity_event
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import SOURCE_URI_METADATA_KEY
from tests.workflows.test_benchmark_case_source import (
    FIRST_FEEDBACK_ID,
    INPUT,
    RUN_ID,
    SECOND_FEEDBACK_ID,
    bad_feedback,
    create_run,
    good_feedback,
    handle_of,
    input_event,
    resolved_events,
)

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")

EXISTING_ID = UUID("b1000000-0000-4000-8000-000000000011")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")

PDF = b"%PDF-1.7\n% a claim\n%%EOF\n"

TICKET_URI = "file:///tickets/7.txt"

EXISTING = BenchmarkCase(
    id=EXISTING_ID,
    input={"text": "that is not dead"},
    expected=ExpectedOutcome(
        description="Four words.",
        value=4,
        comparison=OutcomeComparison.EXACT,
    ),
)


@pytest.fixture
def stocked(
    location: str,
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return the instance holding a benchmark of one case, and the run of the input."""

    repositories = open_repositories(location)

    repositories.benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID, name="word count", description="Count words.", cases=(EXISTING,)
        )
    )
    repositories.runs.save(create_run(input_event()))

    return instance


def revisions(
    instance: api.Azathoth,
) -> int:
    """Return how many revisions the benchmark has."""

    return len(instance.benchmarks.history(BENCHMARK_ID))


#
# Run to case
#


def test_a_run_becomes_a_case_expecting_the_value_given(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.add_case(
        BENCHMARK_ID, run_id=RUN_ID, comparison="exact", expected=4
    )

    assert change.benchmark.revision.number == 2
    assert change.benchmark.case_count == 2
    assert change.case.revision == 2
    assert change.case.source == "run"
    assert change.case.source_run_id == RUN_ID
    assert change.case.input == INPUT
    assert change.case.expected == 4
    assert change.case.description == f"Added from run {RUN_ID}."
    assert change.case.source_feedback_id is None
    assert [case.case_id for case in stocked.benchmarks.cases(BENCHMARK_ID)] == [
        EXISTING_ID,
        change.case.case_id,
    ]


def test_a_run_becomes_a_case_expecting_its_latest_correction(
    location: str,
    stocked: api.Azathoth,
) -> None:
    feedback = open_repositories(location).feedback

    feedback.save(bad_feedback(FIRST_FEEDBACK_ID, corrected=5, minutes=1))
    feedback.save(bad_feedback(SECOND_FEEDBACK_ID, corrected=6, minutes=2))

    change = stocked.benchmarks.add_case(
        BENCHMARK_ID, run_id=RUN_ID, comparison="exact", description="Six, once corrected."
    )

    assert change.case.expected == 6
    assert change.case.source_feedback_id == SECOND_FEEDBACK_ID
    assert change.case.description == "Six, once corrected."


def test_a_run_with_no_correction_needs_an_expected_value(
    location: str,
    stocked: api.Azathoth,
) -> None:
    open_repositories(location).feedback.save(good_feedback(FIRST_FEEDBACK_ID, minutes=1))

    with pytest.raises(
        api.InvalidArgumentError, match=f"Run {RUN_ID} has no corrected output; pass --expected."
    ):
        stocked.benchmarks.add_case(BENCHMARK_ID, run_id=RUN_ID, comparison="exact")

    assert revisions(stocked) == 1


def test_a_run_given_a_null_expected_value_expects_null(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.add_case(
        BENCHMARK_ID, run_id=RUN_ID, comparison="exact", expected=None
    )

    assert change.case.expected is None


def test_a_case_from_a_restricted_run_is_restricted_and_never_lower(
    location: str,
    instance: api.Azathoth,
) -> None:
    repositories = open_repositories(location)
    repositories.benchmarks.save(
        BenchmarkDataset(id=BENCHMARK_ID, name="word count", description="Count words.")
    )
    repositories.runs.save(
        create_run(
            input_event(),
            create_input_sensitivity_event(Sensitivity.RESTRICTED, producer="azathoth.test"),
        )
    )

    with pytest.raises(
        api.InvalidArgumentError,
        match=f"Run {RUN_ID} is restricted; a case made from it cannot be internal.",
    ):
        instance.benchmarks.add_case(
            BENCHMARK_ID,
            run_id=RUN_ID,
            comparison="exact",
            expected=4,
            sensitivity=Sensitivity.INTERNAL,
        )

    change = instance.benchmarks.add_case(
        BENCHMARK_ID, run_id=RUN_ID, comparison="exact", expected=4
    )

    assert change.case.sensitivity == "restricted"
    assert change.benchmark.sensitivity == "restricted"


def test_a_run_whose_content_is_gone_cannot_become_a_case(
    location: str,
    stocked: api.Azathoth,
) -> None:
    run = create_run(*resolved_events("application/pdf", handle_of("application/pdf")))
    open_repositories(location).runs.save(run.model_copy(update={"id": MISSING_ID}))

    with pytest.raises(api.ContentUnavailableError, match="which the content store no longer"):
        stocked.benchmarks.add_case(BENCHMARK_ID, run_id=MISSING_ID, comparison="exact", expected=1)

    assert revisions(stocked) == 1


def test_an_unknown_run_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Run {MISSING_ID} was not found."):
        stocked.benchmarks.add_case(BENCHMARK_ID, run_id=MISSING_ID, comparison="exact", expected=1)


#
# Cases from JSON and from files
#


def test_json_becomes_a_case_with_its_label(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.add_case(
        BENCHMARK_ID,
        input=api.RunInput(payload={"text": "which can eternal lie"}),
        comparison="normalized",
        expected=4,
        sensitivity=Sensitivity.PUBLIC,
        citations=api.CaseCitations(
            require=(api.CitedSegmentSummary(source="poem", segment="l1"),),
            on_unverified="fail",
        ),
    )

    assert change.case.source == "json"
    assert change.case.input == {"text": "which can eternal lie"}
    assert change.case.description == "Added from an inline input."
    assert change.case.sensitivity == "public"
    assert change.case.cited is True


def test_a_text_file_becomes_a_case_naming_where_it_was_read_from(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.add_case(
        BENCHMARK_ID,
        file=api.RunFile(content=b"My printer is on fire.", media_type="text/plain"),
        file_uri=TICKET_URI,
        comparison="exact",
        expected=5,
    )

    assert change.case.source == "file"
    assert change.case.input == "My printer is on fire."
    assert change.case.description == f"Added from {TICKET_URI}."
    assert change.case.metadata == {SOURCE_URI_METADATA_KEY: TICKET_URI}
    assert change.case.input_provenance is not None
    assert change.case.input_provenance["uri"] == TICKET_URI
    assert change.case.input_provenance["digest"] == content_bytes_digest(b"My printer is on fire.")


def test_a_pdf_becomes_a_case_holding_its_kept_contents_handle(
    location: str,
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.add_case(
        BENCHMARK_ID,
        file=api.RunFile(content=PDF, media_type="application/pdf"),
        comparison="exact",
        expected="A claim.",
    )

    assert change.case.source == "file"
    assert change.case.input == handle_of("application/pdf", PDF)
    assert open_repositories(location).content.get(content_bytes_digest(PDF)) == PDF


def test_a_file_that_is_not_its_media_type_is_refused(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError):
        stocked.benchmarks.add_case(
            BENCHMARK_ID,
            file=api.RunFile(content=b"not a pdf", media_type="application/pdf"),
            comparison="exact",
            expected=1,
        )

    assert revisions(stocked) == 1


@pytest.mark.parametrize(
    "source",
    [
        {"input": api.RunInput(payload="words")},
        {"file": api.RunFile(content=b"words", media_type="text/plain")},
    ],
)
def test_a_case_from_json_or_a_file_needs_an_expected_value(
    stocked: api.Azathoth,
    source: dict[str, object],
) -> None:
    with pytest.raises(api.InvalidArgumentError, match="needs an expected value"):
        add = stocked.benchmarks.add_case
        add(BENCHMARK_ID, comparison="exact", **source)  # type: ignore[arg-type]


#
# What every case is refused for
#


@pytest.mark.parametrize(
    "sources",
    [
        {},
        {"run_id": RUN_ID, "input": api.RunInput(payload="words")},
        {"file_uri": TICKET_URI, "input": api.RunInput(payload="words")},
    ],
)
def test_a_case_comes_from_exactly_one_source(
    stocked: api.Azathoth,
    sources: dict[str, object],
) -> None:
    with pytest.raises(api.InvalidArgumentError):
        add = stocked.benchmarks.add_case
        add(BENCHMARK_ID, comparison="exact", expected=1, **sources)  # type: ignore[arg-type]


def test_a_duplicate_case_is_a_conflict(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.ConflictError, match=f"already contains case {EXISTING_ID}"):
        stocked.benchmarks.add_case(
            BENCHMARK_ID,
            input=api.RunInput(payload={"text": "that is not dead"}),
            comparison="exact",
            expected=4,
        )

    assert revisions(stocked) == 1


def test_a_case_needs_a_known_benchmark_and_comparison(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(
        api.NotFoundError, match=f"Benchmark dataset {MISSING_ID} is not configured."
    ):
        stocked.benchmarks.add_case(MISSING_ID, run_id=RUN_ID, comparison="exact", expected=4)

    with pytest.raises(api.InvalidArgumentError, match="comparison must be one of"):
        fuzzy: api.CaseComparison = "fuzzy"  # type: ignore[assignment]
        stocked.benchmarks.add_case(BENCHMARK_ID, run_id=RUN_ID, comparison=fuzzy, expected=4)
