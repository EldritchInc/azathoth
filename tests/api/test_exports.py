"""Contract tests for exporting a revision as the document that imports it again (ADR 0133)."""

from pathlib import Path

import pytest

from azathoth import api
from azathoth.cli import export_benchmark, export_tool, export_workflow
from azathoth.evaluation import encode_benchmark_document
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.tools import encode_tool_document
from azathoth.workflows import encode_workflow_document
from tests.api.test_browse import (
    BENCHMARK_ID,
    MISSING_ID,
    TOOL_ID,
    TOOL_VERSION,
    WORKFLOW_ID,
    described_benchmark,
    described_tool,
    described_workflow,
    example_benchmark,
    example_tool,
    example_workflow,
    stock,
)
from tests.cli.test_experiment_commands import configure_database


@pytest.fixture
def stocked(
    location: str,
) -> str:
    """Return the database, holding three revisions of each example, the third the first's."""

    stock(location)

    return location


#
# Workflows
#


def test_a_workflow_is_exported_as_the_document_that_imports_it(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    exported = instance.workflows.export(WORKFLOW_ID)

    assert isinstance(exported, api.DocumentExport)
    assert exported.text == encode_workflow_document(example_workflow()) + "\n"
    assert exported.file_name == "simple-prompt.r3.workflow.json"
    assert exported.sensitivity is None


def test_an_earlier_workflow_revision_is_exported_as_it_was(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    exported = instance.workflows.export(WORKFLOW_ID, revision=2)

    assert exported.text == encode_workflow_document(described_workflow("Changed.")) + "\n"
    assert exported.file_name == "simple-prompt.r2.workflow.json"


def test_importing_the_latest_export_again_appends_nothing(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    imported = instance.workflows.import_document(instance.workflows.export(WORKFLOW_ID).text)

    assert not imported.created
    assert imported.workflow.revision.number == 3


def test_an_unknown_workflow_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Workflow {MISSING_ID} is not configured."):
        instance.workflows.export(MISSING_ID)

    with pytest.raises(api.RevisionNotFoundError, match="has no revision 9"):
        instance.workflows.export(WORKFLOW_ID, revision=9)


#
# Tools
#


def test_a_tool_version_is_exported_named_by_its_version(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    exported = instance.tools.export(TOOL_ID, TOOL_VERSION)

    assert exported.text == encode_tool_document(example_tool()) + "\n"
    assert exported.file_name == "word-count-1.0.0.r3.tool.json"
    assert instance.tools.export(TOOL_ID, TOOL_VERSION, revision=2).text == (
        encode_tool_document(described_tool("Changed.")) + "\n"
    )


def test_an_unknown_tool_version_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Tool {TOOL_ID}@9.9.9 is not configured."):
        instance.tools.export(TOOL_ID, "9.9.9")

    with pytest.raises(api.RevisionNotFoundError, match="has no revision 9"):
        instance.tools.export(TOOL_ID, TOOL_VERSION, revision=9)


#
# Benchmarks
#


def test_a_benchmark_is_exported_with_its_label(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    exported = instance.benchmarks.export(BENCHMARK_ID)

    assert exported.text == encode_benchmark_document(example_benchmark()) + "\n"
    assert exported.file_name == "word-count.r3.benchmark.json"
    assert instance.benchmarks.export(BENCHMARK_ID, revision=2).text == (
        encode_benchmark_document(described_benchmark("Changed.")) + "\n"
    )


def test_a_restricted_benchmark_says_so_in_its_export(
    location: str,
    instance: api.Azathoth,
) -> None:
    benchmark = example_benchmark()
    first, *rest = benchmark.cases
    open_repositories(location).benchmarks.save(
        benchmark.model_copy(
            update={
                "cases": (first.model_copy(update={"sensitivity": Sensitivity.RESTRICTED}), *rest)
            }
        )
    )

    assert instance.benchmarks.export(BENCHMARK_ID).sensitivity is Sensitivity.RESTRICTED


def test_an_unknown_benchmark_or_revision_is_not_found(
    stocked: str,
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Benchmark dataset {MISSING_ID}"):
        instance.benchmarks.export(MISSING_ID)

    with pytest.raises(api.RevisionNotFoundError, match="has no revision 9"):
        instance.benchmarks.export(BENCHMARK_ID, revision=9)


#
# The commands
#


def test_each_export_command_prints_the_apis_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    location = str(configure_database(monkeypatch, tmp_path))
    stock(location)

    with api.open(location) as opened:
        expected = (
            opened.workflows.export(WORKFLOW_ID, revision=2).text,
            opened.tools.export(TOOL_ID, TOOL_VERSION).text,
            opened.benchmarks.export(BENCHMARK_ID).text,
        )

    assert export_workflow(WORKFLOW_ID, revision=2) == 0
    assert capsys.readouterr().out == expected[0]
    assert export_tool(TOOL_ID, version=TOOL_VERSION) == 0
    assert capsys.readouterr().out == expected[1]
    assert export_benchmark(BENCHMARK_ID) == 0
    assert capsys.readouterr().out == expected[2]


def test_each_export_command_says_what_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stock(str(configure_database(monkeypatch, tmp_path)))

    assert export_workflow(MISSING_ID) == 1
    assert capsys.readouterr().err == f"Workflow {MISSING_ID} is not configured.\n"
    assert export_workflow(WORKFLOW_ID, revision=9) == 1
    assert capsys.readouterr().err == f"Workflow {WORKFLOW_ID} has no revision 9.\n"
    assert export_tool(TOOL_ID, version="9.9.9") == 1
    assert capsys.readouterr().err == f"Tool {TOOL_ID}@9.9.9 is not configured.\n"
    assert export_benchmark(MISSING_ID) == 1
    assert capsys.readouterr().err == f"Benchmark dataset {MISSING_ID} is not configured.\n"
