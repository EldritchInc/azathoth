"""Contract tests for importing workflows, tools and benchmarks (ADR 0120)."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.persistence.repositories import open_repositories

EXAMPLES = Path(__file__).parents[2] / "examples"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")


def example(
    *parts: str,
) -> str:
    """Return one example document's text."""

    return EXAMPLES.joinpath(*parts).read_text(encoding="utf-8")


def example_json(
    *parts: str,
) -> dict[str, JsonValue]:
    """Return one example document as JSON values."""

    document: dict[str, JsonValue] = json.loads(example(*parts))

    return document


#
# Workflows
#


def test_a_workflow_document_is_imported_as_its_first_revision(
    instance: api.Azathoth,
    location: str,
) -> None:
    result = instance.workflows.import_document(example("workflows", "simple-prompt.json"))
    imported = result.workflow

    assert result.created
    assert imported.id == WORKFLOW_ID
    assert imported.revision.number == 1
    assert imported.revision.identical_to is None
    assert imported.latest_number == 1
    assert imported.document == example_json("workflows", "simple-prompt.json")
    assert imported.command == f"azathoth workflow show {WORKFLOW_ID} --revision 1"
    assert len(open_repositories(location).workflows.revisions(WORKFLOW_ID)) == 1


def test_a_workflow_can_be_imported_from_json_values(
    instance: api.Azathoth,
) -> None:
    imported = instance.workflows.import_document(example_json("workflows", "simple-prompt.json"))

    assert imported.workflow == instance.workflows.get(WORKFLOW_ID)


def test_importing_unchanged_content_again_appends_nothing(
    instance: api.Azathoth,
) -> None:
    first = instance.workflows.import_document(example("workflows", "simple-prompt.json"))

    again = instance.workflows.import_document(example("workflows", "simple-prompt.json"))

    assert first.created
    assert not again.created
    assert again.workflow == first.workflow


def test_a_workflow_document_that_is_not_one_is_refused(
    instance: api.Azathoth,
    location: str,
) -> None:
    for document in ("not json", {"metadata": "nothing"}):
        with pytest.raises(api.InvalidDocumentError) as raised:
            instance.workflows.import_document(document)

        assert str(raised.value) == "Workflow document is not a valid WorkflowSpecification."
        assert raised.value.code == "invalid_document"
        assert isinstance(raised.value, api.InvalidArgumentError)

    assert open_repositories(location).workflows.specifications() == ()


def test_a_workflow_without_a_result_is_refused(
    instance: api.Azathoth,
    location: str,
) -> None:
    document = example_json("workflows", "simple-prompt.json")
    del document["result"]

    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.workflows.import_document(document)

    assert str(raised.value) == "Workflow document must declare a result."
    assert open_repositories(location).workflows.specifications() == ()


#
# Tools
#


def test_a_tool_document_is_imported_as_its_versions_first_revision(
    instance: api.Azathoth,
) -> None:
    result = instance.tools.import_document(example("tools", "word-count.json"))
    imported = result.tool

    assert result.created
    assert (imported.id, imported.version) == (TOOL_ID, "1.0.0")
    assert imported.revision.number == 1
    assert imported.implementation_count == 1
    assert imported.document == example_json("tools", "word-count.json")
    assert imported == instance.tools.get(TOOL_ID, "1.0.0")


def test_a_tool_document_that_is_not_one_is_refused(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.tools.import_document("{}")

    assert str(raised.value) == "Tool document is not valid."


def test_a_tool_azathoth_cannot_run_is_refused_before_anything_is_saved(
    instance: api.Azathoth,
    location: str,
) -> None:
    document = example_json("tools", "word-count.json")
    implementations = document["implementations"]

    assert isinstance(implementations, list)
    assert isinstance(implementations[0], dict)

    implementations[0]["runtime"] = "ruby"

    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.tools.import_document(document)

    assert str(raised.value) == (
        "Tool implementation 22222222-2222-2222-2222-222222222222 uses unsupported runtime "
        "'ruby'; supported runtimes: mcp, process, python."
    )
    assert open_repositories(location).tools.definitions() == ()


def test_a_tool_whose_implementation_belongs_to_another_version_is_refused(
    instance: api.Azathoth,
    location: str,
) -> None:
    instance.tools.import_document(example("tools", "word-count.json"))

    document = example_json("tools", "word-count.json")
    definition = document["definition"]
    implementations = document["implementations"]

    assert isinstance(definition, dict)
    assert isinstance(implementations, list)
    assert isinstance(implementations[0], dict)

    definition["version"] = "2.0.0"
    implementations[0]["tool_version"] = "2.0.0"

    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.tools.import_document(document)

    assert str(raised.value) == (
        f"Tool implementation 22222222-2222-2222-2222-222222222222 belongs to tool {TOOL_ID}@1.0.0."
    )
    assert len(open_repositories(location).tools.definitions()) == 1


#
# Benchmarks
#


def test_a_benchmark_document_is_imported_as_its_first_revision(
    instance: api.Azathoth,
) -> None:
    result = instance.benchmarks.import_document(example("benchmarks", "word-count.json"))
    imported = result.benchmark

    assert result.created
    assert imported.id == BENCHMARK_ID
    assert imported.revision.number == 1
    assert imported.case_count == 1
    assert imported == instance.benchmarks.get(BENCHMARK_ID)


def test_a_benchmark_document_that_is_not_one_is_refused(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.benchmarks.import_document("[]")

    assert str(raised.value) == "Benchmark document is not a valid BenchmarkDataset."


def test_a_closed_instance_imports_nothing(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.workflows.import_document(example("workflows", "simple-prompt.json"))
