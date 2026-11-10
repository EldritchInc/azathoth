"""Contract tests for who imports are recorded as and what they build on (ADR 0122)."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.revisions import AUTHOR_VARIABLE, Author
from azathoth.standard import STANDARD_TOOL_AUTHOR, standard_tool_documents

EXAMPLES = Path(__file__).parents[2] / "examples"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")


def document(
    *parts: str,
    description: str | None = None,
) -> dict[str, JsonValue]:
    """Return one example document as JSON values, with another description when given."""

    values: dict[str, JsonValue] = json.loads(EXAMPLES.joinpath(*parts).read_text(encoding="utf-8"))

    if description is None:
        return values

    if parts[0] == "workflows":
        metadata = values["metadata"]
        assert isinstance(metadata, dict)
        metadata["description"] = description
    elif parts[0] == "tools":
        definition = values["definition"]
        assert isinstance(definition, dict)
        definition["description"] = description
    else:
        values["description"] = description

    return values


def workflow(
    description: str | None = None,
) -> dict[str, JsonValue]:
    return document("workflows", "simple-prompt.json", description=description)


def tool(
    description: str | None = None,
) -> dict[str, JsonValue]:
    return document("tools", "word-count.json", description=description)


def benchmark(
    description: str | None = None,
) -> dict[str, JsonValue]:
    return document("benchmarks", "word-count.json", description=description)


def revision_digests(
    location: str,
) -> tuple[str, ...]:
    """Return the revision digest of each of the example workflow's revisions, oldest first."""

    return tuple(
        record.revision_digest
        for record in open_repositories(location).workflows.lineage(WORKFLOW_ID)
    )


# What an import did


def test_an_import_of_new_content_is_created(
    instance: api.Azathoth,
) -> None:
    imported = instance.workflows.import_document(workflow())
    changed = instance.workflows.import_document(workflow("Changed."))

    assert (imported.created, changed.created) == (True, True)
    assert changed.workflow.revision.number == 2


def test_an_unchanged_tool_import_appends_nothing(
    instance: api.Azathoth,
) -> None:
    first = instance.tools.import_document(tool())
    again = instance.tools.import_document(tool())

    assert first.created
    assert not again.created
    assert again.tool == first.tool


def test_an_unchanged_benchmark_import_appends_nothing(
    instance: api.Azathoth,
) -> None:
    first = instance.benchmarks.import_document(benchmark())
    again = instance.benchmarks.import_document(benchmark())

    assert first.created
    assert not again.created
    assert again.benchmark == first.benchmark


# Building on an earlier revision


def test_a_workflow_import_based_on_an_earlier_revision_forks(
    instance: api.Azathoth,
    location: str,
) -> None:
    instance.workflows.import_document(workflow())
    instance.workflows.import_document(workflow("Changed."))

    first, _ = revision_digests(location)

    fork = instance.workflows.import_document(workflow("Forked."), based_on=first)

    assert fork.created
    assert fork.workflow.revision.number == 3
    assert open_repositories(location).workflows.lineage(WORKFLOW_ID)[2].parent_digest == first


def test_an_import_identical_to_the_revision_it_builds_on_returns_that_revision(
    instance: api.Azathoth,
    location: str,
) -> None:
    original = instance.workflows.import_document(workflow())
    instance.workflows.import_document(workflow("Changed."))

    first, _ = revision_digests(location)

    again = instance.workflows.import_document(workflow(), based_on=first)

    assert not again.created
    assert again.workflow.revision == original.workflow.revision
    assert again.workflow.latest_number == 2


def test_an_import_based_on_an_unknown_revision_is_refused(
    instance: api.Azathoth,
    location: str,
) -> None:
    instance.workflows.import_document(workflow())

    with pytest.raises(api.RevisionNotFoundError) as raised:
        instance.workflows.import_document(workflow("Changed."), based_on="f" * 64)

    assert str(raised.value) == (
        f"Revision {'f' * 64} is not a revision of workflow {WORKFLOW_ID}."
    )
    assert raised.value.code == "revision_not_found"
    assert len(revision_digests(location)) == 1


def test_a_tool_import_based_on_an_unknown_revision_is_refused(
    instance: api.Azathoth,
) -> None:
    instance.tools.import_document(tool())

    with pytest.raises(api.RevisionNotFoundError, match="is not a revision of tool"):
        instance.tools.import_document(tool("Changed."), based_on="f" * 64)


def test_a_benchmark_import_based_on_an_unknown_revision_is_refused(
    instance: api.Azathoth,
) -> None:
    instance.benchmarks.import_document(benchmark())

    with pytest.raises(api.RevisionNotFoundError, match="is not a revision of benchmark"):
        instance.benchmarks.import_document(benchmark("Changed."), based_on="f" * 64)


def test_a_tool_and_a_benchmark_import_can_fork(
    instance: api.Azathoth,
    location: str,
) -> None:
    instance.tools.import_document(tool())
    instance.tools.import_document(tool("Changed."))
    instance.benchmarks.import_document(benchmark())
    instance.benchmarks.import_document(benchmark("Changed."))

    repositories = open_repositories(location)
    first_tool = repositories.tools.document_lineage(TOOL_ID, "1.0.0")[0].revision_digest
    first_benchmark = repositories.benchmarks.lineage(BENCHMARK_ID)[0].revision_digest

    tool_fork = instance.tools.import_document(tool("Forked."), based_on=first_tool)
    benchmark_fork = instance.benchmarks.import_document(
        benchmark("Forked."),
        based_on=first_benchmark,
    )

    assert tool_fork.tool.revision.number == 3
    assert benchmark_fork.benchmark.revision.number == 3
    assert repositories.tools.document_lineage(TOOL_ID, "1.0.0")[2].parent_digest == first_tool
    assert repositories.benchmarks.lineage(BENCHMARK_ID)[2].parent_digest == first_benchmark


# Who imports


def test_imports_are_recorded_as_the_author_the_instance_is_opened_with(
    location: str,
) -> None:
    with api.open(location, author="Eris Discordia <eris@example.com>") as instance:
        instance.workflows.import_document(workflow())
        instance.tools.import_document(tool())
        instance.benchmarks.import_document(benchmark())

    eris = Author(name="Eris Discordia", email="eris@example.com")
    repositories = open_repositories(location)

    assert repositories.workflows.lineage(WORKFLOW_ID)[0].author == eris
    assert repositories.tools.document_lineage(TOOL_ID, "1.0.0")[0].author == eris
    assert repositories.benchmarks.lineage(BENCHMARK_ID)[0].author == eris


def test_without_one_imports_are_recorded_as_the_author_variable_names(
    location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with api.open(location) as instance:
        monkeypatch.setenv(AUTHOR_VARIABLE, "Discordia")
        instance.workflows.import_document(workflow())

        monkeypatch.setenv(AUTHOR_VARIABLE, "Eris <eris@example.com>")
        instance.workflows.import_document(workflow("Changed."))

    first, second = open_repositories(location).workflows.lineage(WORKFLOW_ID)

    assert first.author == Author(name="Discordia")
    assert second.author == Author(name="Eris", email="eris@example.com")


def test_a_given_author_is_used_over_the_author_variable(
    location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "Discordia")

    with api.open(location, author="Eris") as instance:
        instance.workflows.import_document(workflow())

    (record,) = open_repositories(location).workflows.lineage(WORKFLOW_ID)

    assert record.author == Author(name="Eris")


def test_a_malformed_given_author_is_refused_before_anything_is_opened(
    tmp_path: Path,
) -> None:
    with pytest.raises(api.InvalidAuthorError) as raised:
        api.open(tmp_path / "missing.db", author="Eris <eris>")

    assert str(raised.value) == 'Author \'Eris <eris>\' is not "Name <email>" or "Name".'
    assert raised.value.code == "invalid_author"
    assert isinstance(raised.value, api.InvalidArgumentError)


def test_a_malformed_author_variable_refuses_the_import_and_saves_nothing(
    instance: api.Azathoth,
    location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "Eris <eris>")

    for importing in (
        lambda: instance.workflows.import_document(workflow()),
        lambda: instance.tools.import_document(tool()),
        lambda: instance.benchmarks.import_document(benchmark()),
    ):
        with pytest.raises(api.InvalidAuthorError) as raised:
            importing()

        assert str(raised.value) == (
            'AZATHOTH_AUTHOR is \'Eris <eris>\'; set it to "Name <email>" or "Name".'
        )

    repositories = open_repositories(location)

    assert repositories.workflows.specifications() == ()
    assert all(definition.id != TOOL_ID for definition in repositories.tools.definitions())
    assert repositories.benchmarks.datasets() == ()


def test_the_standard_tools_are_recorded_as_azathoths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "Eris <eris>")

    path = tmp_path / "azathoth.db"

    api.initialize(path)

    repositories = open_repositories(str(path))

    for standard in standard_tool_documents():
        definition = standard.definition

        (record,) = repositories.tools.document_lineage(definition.id, definition.version)

        assert record.author == STANDARD_TOOL_AUTHOR


def test_the_standard_tool_author_is_azathoth() -> None:
    assert Author(name="Azathoth") == STANDARD_TOOL_AUTHOR
