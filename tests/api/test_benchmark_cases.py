"""Contract tests for reading a benchmark's cases through the service API (ADR 0130)."""

import shlex
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    CitationExpectation,
    CitedSegment,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import InputProvenance, content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import (
    SOURCE_FEEDBACK_METADATA_KEY,
    SOURCE_RUN_METADATA_KEY,
    SOURCE_URI_METADATA_KEY,
)

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")

JSON_CASE_ID = UUID("b1000000-0000-4000-8000-000000000011")

RUN_CASE_ID = UUID("b1000000-0000-4000-8000-000000000012")

FILE_CASE_ID = UUID("b1000000-0000-4000-8000-000000000013")

SOURCE_RUN_ID = UUID("c1000000-0000-4000-8000-000000000001")

SOURCE_FEEDBACK_ID = UUID("c2000000-0000-4000-8000-000000000001")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")

TICKET = b"My printer is on fire."

TICKET_URI = "file:///tickets/7.txt"

JSON_CASE = BenchmarkCase(
    id=JSON_CASE_ID,
    input="that is not dead which can eternal lie",
    expected=ExpectedOutcome(
        description="Eight whitespace-delimited words.",
        value=8,
        comparison=OutcomeComparison.EXACT,
    ),
)

RUN_CASE = BenchmarkCase(
    id=RUN_CASE_ID,
    input={"text": "A ticket."},
    sensitivity=Sensitivity.RESTRICTED,
    expected=ExpectedOutcome(
        description="Added from run c1000000-0000-4000-8000-000000000001.",
        value={"summary": "A ticket, summarized."},
        comparison=OutcomeComparison.SEMANTIC,
        citations=CitationExpectation(
            require=(CitedSegment(source="ticket", segment="body"),),
            on_unverified="ignore",
        ),
    ),
    metadata={
        SOURCE_RUN_METADATA_KEY: str(SOURCE_RUN_ID),
        SOURCE_FEEDBACK_METADATA_KEY: str(SOURCE_FEEDBACK_ID),
    },
)

TICKET_PROVENANCE = InputProvenance(
    uri=TICKET_URI,
    media_type="text/plain",
    size_bytes=len(TICKET),
    digest=content_bytes_digest(TICKET),
)

FILE_CASE = BenchmarkCase(
    id=FILE_CASE_ID,
    input=TICKET.decode(),
    input_provenance=TICKET_PROVENANCE,
    sensitivity=Sensitivity.PUBLIC,
    expected=ExpectedOutcome(
        description=f"Added from {TICKET_URI}.",
        value=5,
        comparison=OutcomeComparison.NORMALIZED,
    ),
    metadata={SOURCE_URI_METADATA_KEY: TICKET_URI},
)


def dataset(
    *cases: BenchmarkCase,
) -> BenchmarkDataset:
    """Return the word count benchmark holding `cases`."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="word count",
        description="Count the words in text.",
        cases=cases,
    )


@pytest.fixture
def stocked(
    location: str,
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return the instance holding two revisions: one case, then three."""

    repositories = open_repositories(location)

    repositories.benchmarks.save(dataset(JSON_CASE))
    repositories.benchmarks.save(dataset(JSON_CASE, RUN_CASE, FILE_CASE))

    return instance


def parses(
    command: str,
) -> bool:
    """Return whether the CLI accepts one command an API value carries."""

    words = shlex.split(command)

    assert words[0] == "azathoth"

    build_parser().parse_args(words[1:])

    return True


def test_cases_are_listed_in_order_from_the_latest_revision(
    stocked: api.Azathoth,
) -> None:
    listed = stocked.benchmarks.cases(BENCHMARK_ID)

    assert [case.case_id for case in listed] == [JSON_CASE_ID, RUN_CASE_ID, FILE_CASE_ID]
    assert all(case.benchmark_id == BENCHMARK_ID for case in listed)
    assert all(case.revision == 2 for case in listed)
    assert all(parses(case.command) for case in listed)


def test_a_case_summary_says_where_it_came_from_and_how_it_is_judged(
    stocked: api.Azathoth,
) -> None:
    from_json, from_run, from_file = stocked.benchmarks.cases(BENCHMARK_ID)

    assert from_json.source == "json"
    assert from_json.source_run_id is None
    assert from_json.comparison == "exact"
    assert from_json.description == "Eight whitespace-delimited words."
    assert from_json.sensitivity == "internal"
    assert from_json.cited is False

    assert from_run.source == "run"
    assert from_run.source_run_id == SOURCE_RUN_ID
    assert from_run.comparison == "semantic"
    assert from_run.sensitivity == "restricted"
    assert from_run.cited is True

    assert from_file.source == "file"
    assert from_file.source_run_id is None
    assert from_file.sensitivity == "public"
    assert from_file.command == (f"azathoth benchmark case-show {BENCHMARK_ID} {FILE_CASE_ID}")


def test_an_earlier_revision_lists_its_own_cases(
    stocked: api.Azathoth,
) -> None:
    (only,) = stocked.benchmarks.cases(BENCHMARK_ID, revision=1)

    assert only.case_id == JSON_CASE_ID
    assert only.revision == 1


def test_a_case_is_read_with_its_input_and_expected_outcome(
    stocked: api.Azathoth,
) -> None:
    case = stocked.benchmarks.case(BENCHMARK_ID, RUN_CASE_ID)

    assert case.input == {"text": "A ticket."}
    assert case.expected == {"summary": "A ticket, summarized."}
    assert case.citations == api.CaseCitations(
        require=(api.CitedSegmentSummary(source="ticket", segment="body"),),
        on_unverified="ignore",
    )
    assert case.input_provenance is None
    assert case.source_feedback_id == SOURCE_FEEDBACK_ID
    assert case.metadata == RUN_CASE.metadata
    assert parses(case.command)


def test_a_file_case_names_the_content_it_was_given(
    stocked: api.Azathoth,
) -> None:
    case = stocked.benchmarks.case(BENCHMARK_ID, FILE_CASE_ID)

    assert case.input == TICKET.decode()
    assert case.input_provenance == TICKET_PROVENANCE.model_dump(mode="json")
    assert case.citations is None
    assert case.source_feedback_id is None


def test_a_null_expected_value_is_told_apart_from_no_value(
    location: str,
    instance: api.Azathoth,
) -> None:
    expects_null = JSON_CASE.model_copy(
        update={"expected": JSON_CASE.expected.model_copy(update={"value": None})}
    )
    open_repositories(location).benchmarks.save(dataset(expects_null))

    case = instance.benchmarks.case(BENCHMARK_ID, JSON_CASE_ID)

    assert case.expected is None
    assert "expected" in case.model_dump()


def test_an_unknown_benchmark_revision_or_case_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(
        api.NotFoundError, match=f"Benchmark dataset {MISSING_ID} is not configured."
    ):
        stocked.benchmarks.cases(MISSING_ID)

    with pytest.raises(api.RevisionNotFoundError):
        stocked.benchmarks.cases(BENCHMARK_ID, revision=3)

    with pytest.raises(
        api.NotFoundError,
        match=f"Benchmark case {RUN_CASE_ID} is not configured in dataset {BENCHMARK_ID}.",
    ):
        stocked.benchmarks.case(BENCHMARK_ID, RUN_CASE_ID, revision=1)

    with pytest.raises(api.NotFoundError):
        stocked.benchmarks.case(MISSING_ID, JSON_CASE_ID)
