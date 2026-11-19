"""Contract tests for creating a benchmark and editing its cases (ADR 0130)."""

from uuid import UUID

import pytest

from azathoth import api
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import SOURCE_FEEDBACK_METADATA_KEY, SOURCE_RUN_METADATA_KEY

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")

FIRST_ID = UUID("b1000000-0000-4000-8000-000000000011")

SECOND_ID = UUID("b1000000-0000-4000-8000-000000000012")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")

SOURCE_RUN_ID = "c1000000-0000-4000-8000-000000000001"

SOURCE_FEEDBACK_ID = "c2000000-0000-4000-8000-000000000001"

FIRST = BenchmarkCase(
    id=FIRST_ID,
    input="that is not dead",
    expected=ExpectedOutcome(
        description="Four words.",
        value=4,
        comparison=OutcomeComparison.EXACT,
    ),
)

SECOND = BenchmarkCase(
    id=SECOND_ID,
    input="which can eternal lie",
    sensitivity=Sensitivity.RESTRICTED,
    expected=ExpectedOutcome(
        description="Added from a run.",
        value=4,
        comparison=OutcomeComparison.EXACT,
    ),
    metadata={
        SOURCE_RUN_METADATA_KEY: SOURCE_RUN_ID,
        SOURCE_FEEDBACK_METADATA_KEY: SOURCE_FEEDBACK_ID,
    },
)

CITED = api.CaseCitations(
    require=(api.CitedSegmentSummary(source="ticket", segment="p1.s2"),),
    on_unverified="ignore",
)


@pytest.fixture
def stocked(
    location: str,
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return the instance holding one benchmark with two cases, at revision 1."""

    open_repositories(location).benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="word count",
            description="Count words.",
            cases=(FIRST, SECOND),
        )
    )

    return instance


def revisions(
    instance: api.Azathoth,
) -> int:
    """Return how many revisions the benchmark has."""

    return len(instance.benchmarks.history(BENCHMARK_ID))


#
# Creating a benchmark
#


def test_a_new_benchmark_has_one_revision_and_no_cases(
    instance: api.Azathoth,
) -> None:
    created = instance.benchmarks.create("tickets", "Summarize support tickets.")

    assert created.created is True
    assert created.benchmark.name == "tickets"
    assert created.benchmark.description == "Summarize support tickets."
    assert created.benchmark.version == "1.0.0"
    assert created.benchmark.case_count == 0
    assert created.benchmark.revision.number == 1
    assert instance.benchmarks.cases(created.benchmark.id) == ()
    assert [summary.id for summary in instance.benchmarks.list()] == [created.benchmark.id]


def test_every_new_benchmark_is_its_own(
    instance: api.Azathoth,
) -> None:
    first = instance.benchmarks.create("tickets", "Tickets.", version="2.0.0")
    second = instance.benchmarks.create("tickets", "Tickets.")

    assert first.benchmark.id != second.benchmark.id
    assert first.benchmark.version == "2.0.0"


@pytest.mark.parametrize(
    ("name", "description", "version"),
    [(" ", "Tickets.", "1.0.0"), ("tickets", "", "1.0.0"), ("tickets", "Tickets.", " ")],
)
def test_a_benchmark_needs_a_name_a_description_and_a_version(
    instance: api.Azathoth,
    name: str,
    description: str,
    version: str,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match="must not be blank"):
        instance.benchmarks.create(name, description, version=version)

    assert instance.benchmarks.list() == ()


#
# Editing a case
#


def test_an_edit_saves_the_next_revision_changing_only_what_it_is_given(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.update_case(
        BENCHMARK_ID,
        FIRST_ID,
        comparison="normalized",
        description="  Four words, however spaced.  ",
    )

    assert change.benchmark.revision.number == 2
    assert change.case.revision == 2
    assert change.case.case_id == FIRST_ID
    assert change.case.input == "that is not dead"
    assert change.case.comparison == "normalized"
    assert change.case.description == "Four words, however spaced."
    assert change.case.expected == 4
    assert change.case.sensitivity == "internal"
    assert stocked.benchmarks.case(BENCHMARK_ID, FIRST_ID, revision=1).comparison == "exact"
    assert [case.case_id for case in stocked.benchmarks.cases(BENCHMARK_ID)] == [
        FIRST_ID,
        SECOND_ID,
    ]


def test_an_edit_may_expect_null(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID, expected=None)

    assert change.case.expected is None
    assert stocked.benchmarks.case(BENCHMARK_ID, FIRST_ID).expected is None


def test_a_new_expected_value_no_longer_comes_from_the_runs_judgment(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.update_case(BENCHMARK_ID, SECOND_ID, expected=5)

    assert change.case.expected == 5
    assert change.case.source == "run"
    assert change.case.source_run_id == UUID(SOURCE_RUN_ID)
    assert change.case.source_feedback_id is None
    assert change.case.metadata == {SOURCE_RUN_METADATA_KEY: SOURCE_RUN_ID}


def test_an_edit_names_or_clears_what_the_run_must_cite(
    stocked: api.Azathoth,
) -> None:
    cited = stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID, citations=CITED)

    assert cited.case.citations == CITED
    assert cited.case.cited is True

    cleared = stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID, citations=None)

    assert cleared.case.citations is None
    assert cleared.benchmark.revision.number == 3


def test_an_edit_may_raise_a_label_but_never_lower_it(
    stocked: api.Azathoth,
) -> None:
    raised = stocked.benchmarks.update_case(
        BENCHMARK_ID, FIRST_ID, sensitivity=Sensitivity.RESTRICTED
    )

    assert raised.case.sensitivity == "restricted"
    assert raised.benchmark.sensitivity == "restricted"

    with pytest.raises(
        api.InvalidArgumentError,
        match=f"Benchmark case {SECOND_ID} is restricted; an edit cannot label it public.",
    ):
        stocked.benchmarks.update_case(BENCHMARK_ID, SECOND_ID, sensitivity=Sensitivity.PUBLIC)

    assert revisions(stocked) == 2


def test_an_edit_that_changes_nothing_is_refused(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match="changes nothing"):
        stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID)

    assert revisions(stocked) == 1


def test_an_edit_to_what_a_case_already_holds_saves_nothing(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID, expected=4)

    assert change.benchmark.revision.number == 1
    assert revisions(stocked) == 1


def test_an_edit_that_duplicates_another_case_is_a_conflict(
    location: str,
    stocked: api.Azathoth,
) -> None:
    twin_id = UUID("b1000000-0000-4000-8000-000000000013")
    twin = FIRST.model_copy(
        update={
            "id": twin_id,
            "expected": FIRST.expected.model_copy(update={"value": 5}),
        }
    )
    open_repositories(location).benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="word count",
            description="Count words.",
            cases=(FIRST, SECOND, twin),
        )
    )

    with pytest.raises(
        api.ConflictError,
        match=f"already contains case {FIRST_ID} with this input and expected outcome",
    ):
        stocked.benchmarks.update_case(BENCHMARK_ID, twin_id, expected=4)

    assert revisions(stocked) == 2


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"description": "   "}, "must not be blank"),
        ({"comparison": "schema", "expected": "not a schema"}, "comparison 'schema'"),
        ({"comparison": "fuzzy"}, "comparison must be one of"),
    ],
)
def test_an_edit_is_refused_when_its_case_would_be(
    stocked: api.Azathoth,
    change: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match=message):
        stocked.benchmarks.update_case(BENCHMARK_ID, FIRST_ID, **change)  # type: ignore[arg-type]

    assert revisions(stocked) == 1


def test_editing_an_unknown_benchmark_or_case_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match="is not configured"):
        stocked.benchmarks.update_case(MISSING_ID, FIRST_ID, expected=1)

    with pytest.raises(
        api.NotFoundError,
        match=f"Benchmark case {MISSING_ID} is not configured in dataset {BENCHMARK_ID}.",
    ):
        stocked.benchmarks.update_case(BENCHMARK_ID, MISSING_ID, expected=1)


#
# Removing a case
#


def test_a_removed_case_leaves_the_next_revision_and_stays_in_earlier_ones(
    stocked: api.Azathoth,
) -> None:
    change = stocked.benchmarks.remove_case(BENCHMARK_ID, SECOND_ID)

    assert change.case.case_id == SECOND_ID
    assert change.case.revision == 1
    assert change.case.sensitivity == "restricted"
    assert change.benchmark.revision.number == 2
    assert change.benchmark.case_count == 1
    assert change.benchmark.sensitivity == "internal"
    assert [case.case_id for case in stocked.benchmarks.cases(BENCHMARK_ID)] == [FIRST_ID]
    assert stocked.benchmarks.case(BENCHMARK_ID, SECOND_ID, revision=1).case_id == SECOND_ID


def test_removing_an_unknown_case_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Benchmark case {MISSING_ID} is not configured"):
        stocked.benchmarks.remove_case(BENCHMARK_ID, MISSING_ID)

    assert revisions(stocked) == 1
