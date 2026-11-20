"""Contract tests for comparing two revisions value by value (ADR 0133)."""

from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.api.comparison import compare_documents, json_pointer
from azathoth.evaluation import BenchmarkCase, BenchmarkDataset
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from tests.api.test_browse import (
    BENCHMARK_ID,
    MISSING_ID,
    TOOL_ID,
    TOOL_VERSION,
    WORKFLOW_ID,
    example_benchmark,
    example_tool,
    example_workflow,
    stock,
)

SECOND_CASE_ID = UUID("b1000000-0000-4000-8000-000000000012")


@pytest.fixture
def stocked(
    location: str,
) -> str:
    """Return the database, holding three revisions of each example, the third the first's."""

    stock(location)

    return location


def second_case(
    text: str = "the color out of space",
) -> BenchmarkCase:
    """Return a second case for the example benchmark."""

    first = example_benchmark().cases[0]

    return first.model_copy(update={"id": SECOND_CASE_ID, "input": text})


def restricted(
    case: BenchmarkCase,
) -> BenchmarkCase:
    """Return a case labelled restricted."""

    return case.model_copy(update={"sensitivity": Sensitivity.RESTRICTED})


def with_cases(
    *cases: BenchmarkCase,
) -> BenchmarkDataset:
    """Return the example benchmark holding these cases."""

    return example_benchmark().model_copy(update={"cases": cases})


def save_benchmarks(
    location: str,
    *datasets: BenchmarkDataset,
) -> None:
    """Save each dataset as the benchmark's next revision."""

    repositories = open_repositories(location)

    for dataset in datasets:
        repositories.benchmarks.save(dataset)


#
# Workflows
#


def test_two_workflow_revisions_differ_where_their_documents_do(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    compared = instance.workflows.compare_revisions(WORKFLOW_ID, 1, 2)

    assert isinstance(compared, api.RevisionComparison)
    assert (compared.before.number, compared.after.number) == (1, 2)
    assert compared.before.content_digest != compared.after.content_digest
    assert not compared.identical
    assert compared.changes == (
        api.RevisionChange(
            kind="changed",
            pointer="/metadata/description",
            before=example_workflow().metadata.description,
            after="Changed.",
        ),
    )


def test_a_revision_that_reverted_is_identical_to_the_one_it_reverted_to(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    compared = instance.workflows.compare_revisions(WORKFLOW_ID, 1, 3)

    assert compared.identical
    assert compared.changes == ()
    assert compared.after.identical_to == 1


def test_a_revision_compared_with_itself_is_identical(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    compared = instance.workflows.compare_revisions(WORKFLOW_ID, 2, 2)

    assert compared.identical
    assert compared.changes == ()


def test_comparing_backwards_swaps_before_and_after(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    (change,) = instance.workflows.compare_revisions(WORKFLOW_ID, 2, 1).changes

    assert (change.before, change.after) == ("Changed.", example_workflow().metadata.description)


def test_an_unknown_workflow_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Workflow {MISSING_ID} is not configured."):
        instance.workflows.compare_revisions(MISSING_ID, 1, 2)

    with pytest.raises(api.RevisionNotFoundError) as raised:
        instance.workflows.compare_revisions(WORKFLOW_ID, 1, 9)

    assert str(raised.value) == f"Workflow {WORKFLOW_ID} has no revision 9."
    assert raised.value.code == "revision_not_found"


#
# Tools
#


def test_two_revisions_of_a_tool_version_differ_where_their_documents_do(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    compared = instance.tools.compare_revisions(TOOL_ID, TOOL_VERSION, 2, 3)

    assert compared.changes == (
        api.RevisionChange(
            kind="changed",
            pointer="/definition/description",
            before="Changed.",
            after=example_tool().definition.description,
        ),
    )
    assert instance.tools.compare_revisions(TOOL_ID, TOOL_VERSION, 1, 3).identical


def test_an_unknown_tool_version_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Tool {TOOL_ID}@9.9.9 is not configured."):
        instance.tools.compare_revisions(TOOL_ID, "9.9.9", 1, 2)

    with pytest.raises(api.RevisionNotFoundError, match=f"Tool {TOOL_ID}@1.0.0 has no revision 9."):
        instance.tools.compare_revisions(TOOL_ID, TOOL_VERSION, 9, 1)


#
# Benchmarks
#


def test_two_benchmark_revisions_differ_where_their_documents_do(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    compared = instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2)

    assert compared.changes == (
        api.RevisionChange(
            kind="changed",
            pointer="/description",
            before=example_benchmark().description,
            after="Changed.",
        ),
    )


def test_a_case_appended_is_added_and_a_case_dropped_is_removed(
    location: str,
    instance: api.Azathoth,
) -> None:
    first = example_benchmark().cases[0]
    save_benchmarks(location, with_cases(first), with_cases(first, second_case()))

    (added,) = instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2).changes
    (removed,) = instance.benchmarks.compare_revisions(BENCHMARK_ID, 2, 1).changes

    expected = second_case().model_dump(mode="json")
    assert added == api.RevisionChange(kind="added", pointer="/cases/1", after=expected)
    assert removed == api.RevisionChange(kind="removed", pointer="/cases/1", before=expected)


def test_a_case_inserted_first_reads_as_each_case_changing(
    location: str,
    instance: api.Azathoth,
) -> None:
    first = example_benchmark().cases[0]
    save_benchmarks(location, with_cases(first), with_cases(second_case(), first))

    changes = instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2).changes

    assert [(change.kind, change.pointer) for change in changes] == [
        ("changed", "/cases/0/id"),
        ("changed", "/cases/0/input"),
        ("added", "/cases/1"),
    ]


def test_a_restricted_cases_values_are_withheld_without_restricted_access(
    location: str,
    instance: api.Azathoth,
) -> None:
    case = restricted(second_case("patient 412 reports"))
    save_benchmarks(
        location,
        with_cases(case),
        with_cases(case.model_copy(update={"input": "patient 413 reports"})),
    )

    (withheld,) = instance.benchmarks.compare_revisions(
        BENCHMARK_ID, 1, 2, include_restricted=False
    ).changes
    (shown,) = instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2).changes

    assert withheld == api.RevisionChange(kind="changed", pointer="/cases/0/input", withheld=True)
    assert shown == api.RevisionChange(
        kind="changed",
        pointer="/cases/0/input",
        before="patient 412 reports",
        after="patient 413 reports",
    )


def test_a_restricted_case_added_keeps_only_what_its_summary_shows(
    location: str,
    instance: api.Azathoth,
) -> None:
    first = example_benchmark().cases[0]
    case = restricted(second_case("patient 412 reports"))
    save_benchmarks(location, with_cases(first), with_cases(first, case))

    (added,) = instance.benchmarks.compare_revisions(
        BENCHMARK_ID, 1, 2, include_restricted=False
    ).changes

    assert added.kind == "added"
    assert added.withheld
    assert isinstance(added.after, dict)
    assert added.after["input"] is None
    assert added.after["sensitivity"] == "restricted"
    assert added.after["expected"] == {
        "description": case.expected.description,
        "value": None,
        "comparison": "exact",
    }


def test_a_case_that_becomes_restricted_withholds_only_its_values_after(
    location: str,
    instance: api.Azathoth,
) -> None:
    case = second_case("open text")
    save_benchmarks(
        location,
        with_cases(case),
        with_cases(restricted(case.model_copy(update={"input": "patient 412 reports"}))),
    )

    changes = instance.benchmarks.compare_revisions(
        BENCHMARK_ID, 1, 2, include_restricted=False
    ).changes

    assert changes == (
        api.RevisionChange(
            kind="changed", pointer="/cases/0/input", before="open text", withheld=True
        ),
        api.RevisionChange(kind="added", pointer="/cases/0/sensitivity", after="restricted"),
    )


def test_internal_cases_are_shown_without_restricted_access(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    assert instance.benchmarks.compare_revisions(
        BENCHMARK_ID, 1, 2, include_restricted=False
    ) == instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2)


def test_an_unknown_benchmark_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Benchmark dataset {MISSING_ID}"):
        instance.benchmarks.compare_revisions(MISSING_ID, 1, 2)

    with pytest.raises(
        api.RevisionNotFoundError, match=f"Benchmark dataset {BENCHMARK_ID} has no revision 9."
    ):
        instance.benchmarks.compare_revisions(BENCHMARK_ID, 9, 1)


#
# Comparing documents
#


def compared(
    before: JsonValue,
    after: JsonValue,
) -> list[tuple[str, str, JsonValue, JsonValue]]:
    """Return each change between two documents as its kind, pointer and values."""

    revision = api.Revision(
        number=1,
        content_digest="sha256:same",
        imported_at=None,
        identical_to=None,
        revision_digest="sha256:revision",
        parent_digest=None,
        parent_number=None,
        author=None,
    )

    return [
        (change.kind, change.pointer, change.before, change.after)
        for change in compare_documents(revision, revision, (before, after)).changes
    ]


def test_a_pointer_escapes_tildes_and_slashes() -> None:
    assert json_pointer(()) == ""
    assert json_pointer(("a/b", "m~n", 0)) == "/a~1b/m~0n/0"
    assert compared({"a/b": 1}, {"a/b": 2}) == [("changed", "/a~1b", 1, 2)]


def test_numbers_and_booleans_of_another_type_differ() -> None:
    assert compared([1, 1, 0], [1.0, True, False]) == [
        ("changed", "/0", 1, 1.0),
        ("changed", "/1", 1, True),
        ("changed", "/2", 0, False),
    ]


def test_keys_are_compared_in_document_order() -> None:
    assert compared({"b": 1, "a": 1, "c": 1}, {"a": 2, "d": 1, "b": 1}) == [
        ("changed", "/a", 1, 2),
        ("removed", "/c", 1, None),
        ("added", "/d", None, 1),
    ]


def test_a_value_of_another_shape_changes_whole() -> None:
    assert compared({"steps": [1]}, {"steps": {"0": 1}}) == [
        ("changed", "/steps", [1], {"0": 1}),
    ]


def test_a_comparison_round_trips_as_json(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    comparison = instance.benchmarks.compare_revisions(BENCHMARK_ID, 1, 2)

    assert api.RevisionComparison.model_validate_json(comparison.model_dump_json()) == comparison
