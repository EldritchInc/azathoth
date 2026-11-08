"""Contract tests for browsing workflows, tools and benchmarks (ADR 0120)."""

import json
import shlex
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from azathoth.evaluation import (
    BenchmarkDataset,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import (
    ToolDocument,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

EXAMPLES = Path(__file__).parents[2] / "examples"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

TOOL_VERSION = "1.0.0"

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def example_workflow() -> WorkflowSpecification:
    """Return the simple prompt example workflow."""

    return decode_workflow_document(
        (EXAMPLES / "workflows" / "simple-prompt.json").read_text(encoding="utf-8")
    )


def example_tool() -> ToolDocument:
    """Return the word count example tool document."""

    return decode_tool_document(
        (EXAMPLES / "tools" / "word-count.json").read_text(encoding="utf-8")
    )


def example_benchmark() -> BenchmarkDataset:
    """Return the word count example benchmark."""

    return decode_benchmark_document(
        (EXAMPLES / "benchmarks" / "word-count.json").read_text(encoding="utf-8")
    )


def described_workflow(
    description: str,
) -> WorkflowSpecification:
    """Return the example workflow with another description."""

    specification = example_workflow()

    return specification.model_copy(
        update={
            "metadata": specification.metadata.model_copy(update={"description": description}),
        }
    )


def described_tool(
    description: str,
) -> ToolDocument:
    """Return the example tool document with another description."""

    document = example_tool()

    return document.model_copy(
        update={
            "definition": document.definition.model_copy(update={"description": description}),
        }
    )


def versioned_tool(
    version: str,
) -> ToolDocument:
    """Return the example tool document as another exact version, with artifacts of its own."""

    document = example_tool()

    return ToolDocument(
        definition=document.definition.model_copy(update={"version": version}),
        implementations=tuple(
            implementation.model_copy(update={"id": uuid4(), "tool_version": version})
            for implementation in document.implementations
        ),
        test_cases=tuple(
            test_case.model_copy(update={"id": uuid4()}) for test_case in document.test_cases
        ),
    )


def described_benchmark(
    description: str,
) -> BenchmarkDataset:
    """Return the example benchmark with another description."""

    return example_benchmark().model_copy(update={"description": description})


def stock(
    location: str,
) -> None:
    """Import three revisions of each example; the third reverts to the first."""

    repositories = open_repositories(location)

    for workflow in (example_workflow(), described_workflow("Changed."), example_workflow()):
        repositories.workflows.save(workflow)

    for tool in (example_tool(), described_tool("Changed."), example_tool()):
        repositories.tools.save_document(tool)

    for benchmark in (example_benchmark(), described_benchmark("Changed."), example_benchmark()):
        repositories.benchmarks.save(benchmark)


def parses(
    command: str,
) -> bool:
    """Return whether the CLI accepts one command an API value carries."""

    words = shlex.split(command)

    assert words[0] == "azathoth"

    build_parser().parse_args(words[1:])

    return True


#
# Workflows
#


def test_an_empty_instance_lists_nothing(
    instance: api.Azathoth,
) -> None:
    assert instance.workflows.list() == ()
    assert instance.tools.list() == ()
    assert instance.benchmarks.list() == ()


def test_workflows_are_listed_at_their_latest_revision(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    (summary,) = instance.workflows.list()

    assert summary.id == WORKFLOW_ID
    assert summary.name == "simple prompt"
    assert summary.version == "1.0.0"
    assert summary.description == "Return a concise answer to one request."
    assert summary.revision.number == 3
    assert summary.revision.identical_to == 1
    assert summary.revision.imported_at is not None
    assert summary.command == f"azathoth workflow show {WORKFLOW_ID}"
    assert parses(summary.command)


def test_a_workflow_is_its_latest_revision_by_default(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    workflow = instance.workflows.get(WORKFLOW_ID)

    assert workflow.revision.number == 3
    assert workflow.latest_number == 3
    assert workflow.document == json.loads(encode_workflow_document(example_workflow()))
    assert workflow.command == f"azathoth workflow show {WORKFLOW_ID} --revision 3"
    assert parses(workflow.command)


def test_an_earlier_workflow_revision_is_returned_as_it_was(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    workflow = instance.workflows.get(WORKFLOW_ID, revision=2)

    assert workflow.description == "Changed."
    assert workflow.revision.number == 2
    assert workflow.revision.identical_to is None
    assert workflow.latest_number == 3
    assert workflow.document == json.loads(encode_workflow_document(described_workflow("Changed.")))
    assert workflow.command == f"azathoth workflow show {WORKFLOW_ID} --revision 2"


def test_a_workflows_digest_is_its_revisions(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    revisions = open_repositories(location).workflows.revisions(WORKFLOW_ID)

    history = instance.workflows.history(WORKFLOW_ID)
    digests = tuple(entry.revision.content_digest for entry in history)

    assert digests == tuple(revision.content_digest for revision in reversed(revisions))


def test_a_workflows_history_is_newest_first_and_names_reverts(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    history = instance.workflows.history(WORKFLOW_ID)

    assert tuple(entry.revision.number for entry in history) == (3, 2, 1)
    assert tuple(entry.revision.identical_to for entry in history) == (1, None, None)
    assert tuple(entry.description for entry in history) == (
        "Return a concise answer to one request.",
        "Changed.",
        "Return a concise answer to one request.",
    )
    assert history[1].command == f"azathoth workflow show {WORKFLOW_ID} --revision 2"
    assert all(parses(entry.command) for entry in history)


def test_a_workflows_history_can_be_limited_to_its_newest_revisions(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    history = instance.workflows.history(WORKFLOW_ID, limit=2)

    assert tuple(entry.revision.number for entry in history) == (3, 2)


def test_an_unknown_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    for call in (
        lambda: instance.workflows.get(MISSING_ID),
        lambda: instance.workflows.history(MISSING_ID),
    ):
        with pytest.raises(api.NotFoundError) as raised:
            call()

        assert str(raised.value) == f"Workflow {MISSING_ID} is not configured."
        assert raised.value.code == "not_found"


def test_a_missing_workflow_revision_is_not_found(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    with pytest.raises(api.RevisionNotFoundError) as raised:
        instance.workflows.get(WORKFLOW_ID, revision=4)

    assert str(raised.value) == f"Workflow {WORKFLOW_ID} has no revision 4."
    assert raised.value.code == "revision_not_found"
    assert isinstance(raised.value, api.NotFoundError)


#
# Tools
#


def test_tools_are_listed_by_version_at_their_latest_revision(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    (summary,) = instance.tools.list()

    assert summary.id == TOOL_ID
    assert summary.version == TOOL_VERSION
    assert summary.name == example_tool().definition.name
    assert summary.description == example_tool().definition.description
    assert summary.revision.number == 3
    assert summary.revision.identical_to == 1
    assert summary.implementation_count == 1
    assert summary.test_case_count == 2
    assert summary.command == f"azathoth tool show {TOOL_ID} --version {TOOL_VERSION}"
    assert parses(summary.command)


def test_a_tool_is_its_versions_latest_revision_by_default(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    tool = instance.tools.get(TOOL_ID, TOOL_VERSION)

    assert tool.revision.number == 3
    assert tool.latest_number == 3
    assert tool.document == json.loads(encode_tool_document(example_tool()))
    assert tool.command == (f"azathoth tool export {TOOL_ID} --version {TOOL_VERSION} --revision 3")
    assert parses(tool.command)


def test_an_earlier_tool_revision_is_returned_as_it_was(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    tool = instance.tools.get(TOOL_ID, TOOL_VERSION, revision=2)

    assert tool.description == "Changed."
    assert tool.revision.number == 2
    assert tool.document == json.loads(encode_tool_document(described_tool("Changed.")))


def test_a_tools_history_is_newest_first_and_can_be_limited(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    history = instance.tools.history(TOOL_ID)

    assert tuple(entry.revision.number for entry in history) == (3, 2, 1)
    assert tuple(entry.revision.identical_to for entry in history) == (1, None, None)
    assert all(parses(entry.command) for entry in history)
    assert tuple(entry.revision.number for entry in instance.tools.history(TOOL_ID, limit=1)) == (
        3,
    )


def test_a_tools_history_can_be_limited_to_one_version(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    assert len(instance.tools.history(TOOL_ID, version=TOOL_VERSION)) == 3

    with pytest.raises(api.NotFoundError) as raised:
        instance.tools.history(TOOL_ID, version="9.9.9")

    assert str(raised.value) == f"Tool {TOOL_ID}@9.9.9 is not configured."


def test_each_tool_version_has_revisions_of_its_own(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)
    open_repositories(location).tools.save_document(versioned_tool("2.0.0"))

    listed = instance.tools.list()

    assert tuple((summary.version, summary.revision.number) for summary in listed) == (
        (TOOL_VERSION, 3),
        ("2.0.0", 1),
    )

    first = instance.tools.get(TOOL_ID, TOOL_VERSION)
    second = instance.tools.get(TOOL_ID, "2.0.0")

    assert (first.revision.number, first.latest_number) == (3, 3)
    assert (second.revision.number, second.latest_number) == (1, 1)
    assert second.command == f"azathoth tool export {TOOL_ID} --version 2.0.0 --revision 1"

    history = instance.tools.history(TOOL_ID)

    assert tuple((entry.version, entry.revision.number) for entry in history) == (
        ("2.0.0", 1),
        (TOOL_VERSION, 3),
        (TOOL_VERSION, 2),
        (TOOL_VERSION, 1),
    )
    assert tuple(entry.revision.identical_to for entry in history) == (None, 1, None, None)


def test_a_tool_version_is_quoted_in_its_commands(
    instance: api.Azathoth,
    location: str,
) -> None:
    open_repositories(location).tools.save_document(versioned_tool("2.0 beta"))

    (summary,) = instance.tools.list()
    tool = instance.tools.get(TOOL_ID, "2.0 beta")

    assert summary.command == f"azathoth tool show {TOOL_ID} --version '2.0 beta'"
    assert tool.command == f"azathoth tool export {TOOL_ID} --version '2.0 beta' --revision 1"
    assert parses(summary.command)
    assert parses(tool.command)


def test_an_unknown_tool_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.tools.get(MISSING_ID, TOOL_VERSION)

    assert str(raised.value) == f"Tool {MISSING_ID}@{TOOL_VERSION} is not configured."
    assert raised.value.code == "not_found"

    with pytest.raises(api.NotFoundError) as raised:
        instance.tools.history(MISSING_ID)

    assert str(raised.value) == f"Tool {MISSING_ID} is not configured."


def test_a_missing_tool_revision_is_not_found(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    with pytest.raises(api.RevisionNotFoundError) as raised:
        instance.tools.get(TOOL_ID, TOOL_VERSION, revision=7)

    assert str(raised.value) == f"Tool {TOOL_ID}@{TOOL_VERSION} has no revision 7."


#
# Benchmarks
#


def test_benchmarks_are_listed_at_their_latest_revision(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    (summary,) = instance.benchmarks.list()

    assert summary.id == BENCHMARK_ID
    assert summary.name == "word count"
    assert summary.case_count == 1
    assert summary.revision.number == 3
    assert summary.revision.identical_to == 1
    assert summary.command == f"azathoth benchmark show {BENCHMARK_ID}"
    assert parses(summary.command)


def test_a_benchmark_revision_is_returned_as_it_was(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    latest = instance.benchmarks.get(BENCHMARK_ID)
    earlier = instance.benchmarks.get(BENCHMARK_ID, revision=2)

    assert latest.revision.number == 3
    assert latest.latest_number == 3
    assert latest.document == json.loads(encode_benchmark_document(example_benchmark()))
    assert latest.command == f"azathoth benchmark show {BENCHMARK_ID} --revision 3"
    assert parses(latest.command)
    assert earlier.description == "Changed."
    assert earlier.document == json.loads(
        encode_benchmark_document(described_benchmark("Changed."))
    )


def test_a_benchmarks_history_is_newest_first_and_can_be_limited(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    history = instance.benchmarks.history(BENCHMARK_ID)

    assert tuple(entry.revision.number for entry in history) == (3, 2, 1)
    assert tuple(entry.revision.identical_to for entry in history) == (1, None, None)
    assert all(parses(entry.command) for entry in history)
    assert len(instance.benchmarks.history(BENCHMARK_ID, limit=2)) == 2


def test_an_unknown_benchmark_or_revision_is_not_found(
    instance: api.Azathoth,
    location: str,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.benchmarks.get(MISSING_ID)

    assert str(raised.value) == f"Benchmark dataset {MISSING_ID} is not configured."

    stock(location)

    with pytest.raises(api.RevisionNotFoundError) as raised:
        instance.benchmarks.get(BENCHMARK_ID, revision=4)

    assert str(raised.value) == f"Benchmark dataset {BENCHMARK_ID} has no revision 4."


#
# Every namespace
#


def test_a_closed_instance_refuses_to_browse(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    for call in (
        opened.workflows.list,
        opened.tools.list,
        opened.benchmarks.list,
    ):
        with pytest.raises(api.InstanceClosedError):
            call()


def test_browsed_values_are_their_own_json(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(location)

    values: tuple[api.ApiModel, ...] = (
        *instance.workflows.list(),
        instance.workflows.get(WORKFLOW_ID),
        *instance.tools.list(),
        instance.tools.get(TOOL_ID, TOOL_VERSION),
        *instance.benchmarks.list(),
        instance.benchmarks.get(BENCHMARK_ID),
    )

    for value in values:
        assert type(value).model_validate_json(value.model_dump_json()) == value


def test_a_revision_limit_must_be_positive(
    instance: api.Azathoth,
) -> None:
    for call in (
        lambda: instance.workflows.history(WORKFLOW_ID, limit=0),
        lambda: instance.tools.history(TOOL_ID, limit=0),
        lambda: instance.benchmarks.history(BENCHMARK_ID, limit=0),
    ):
        with pytest.raises(
            api.InvalidArgumentError,
            match=r"^A history limit must be at least 1\.$",
        ):
            call()
