"""Tests for `workflow diff`, `tool diff` and `benchmark diff` (ADR 0133)."""

from pathlib import Path

import pytest

from azathoth import api
from azathoth.cli import main
from azathoth.cli.rendering import render_revision_change, render_revision_comparison
from azathoth.cli.rendering.sensitivity import restricted_output_warning
from tests.api.test_browse import (
    BENCHMARK_ID,
    TOOL_ID,
    TOOL_VERSION,
    WORKFLOW_ID,
    example_benchmark,
    example_tool,
    example_workflow,
    stock,
)
from tests.api.test_revision_comparison import (
    restricted,
    save_benchmarks,
    second_case,
    with_cases,
)
from tests.cli.test_experiment_commands import configure_database


@pytest.fixture
def location(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> str:
    """Return the CLI's database, empty."""

    return str(configure_database(monkeypatch, tmp_path))


@pytest.fixture
def stocked(
    location: str,
) -> str:
    """Return the CLI's database, holding three revisions of each example."""

    stock(location)

    return location


#
# Text
#


def test_workflow_diff_prints_a_line_per_change(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["workflow", "diff", str(WORKFLOW_ID), "1", "2"]) == 0

    captured = capsys.readouterr()
    description = example_workflow().metadata.description
    assert captured.out == f'~ /metadata/description: "{description}" -> "Changed."\n'
    assert captured.err == ""


def test_identical_revisions_are_said_to_be(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["workflow", "diff", str(WORKFLOW_ID), "1", "3"]) == 0

    assert capsys.readouterr().out == "Revisions 1 and 3 are identical.\n"


def test_tool_diff_names_the_version(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["tool", "diff", str(TOOL_ID), "2", "3", "--version", TOOL_VERSION]) == 0

    description = example_tool().definition.description
    assert capsys.readouterr().out == f'~ /definition/description: "Changed." -> "{description}"\n'


def test_benchmark_diff_abbreviates_a_case_added_or_removed(
    location: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = example_benchmark().cases[0]
    save_benchmarks(location, with_cases(first), with_cases(first, second_case()))

    assert main(["benchmark", "diff", str(BENCHMARK_ID), "1", "2"]) == 0
    assert capsys.readouterr().out == "+ /cases/1: {...}\n"
    assert main(["benchmark", "diff", str(BENCHMARK_ID), "2", "1"]) == 0
    assert capsys.readouterr().out == "- /cases/1: {...}\n"


def test_benchmark_diff_prints_restricted_values_and_warns(
    location: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = restricted(second_case("patient 412 reports"))
    save_benchmarks(
        location,
        with_cases(case),
        with_cases(case.model_copy(update={"input": "patient 413 reports"})),
    )

    assert main(["benchmark", "diff", str(BENCHMARK_ID), "1", "2"]) == 0

    captured = capsys.readouterr()
    assert captured.out == '~ /cases/0/input: "patient 412 reports" -> "patient 413 reports"\n'
    assert captured.err == restricted_output_warning(f"Benchmark {BENCHMARK_ID}") + "\n"


def test_benchmark_diff_of_internal_cases_does_not_warn(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["benchmark", "diff", str(BENCHMARK_ID), "1", "2"]) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("~ /description: ")
    assert captured.err == ""


#
# JSON
#


def test_each_diff_prints_the_apis_comparison_as_json(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with api.open(stocked) as opened:
        expected = (
            opened.workflows.compare_revisions(WORKFLOW_ID, 1, 2),
            opened.tools.compare_revisions(TOOL_ID, TOOL_VERSION, 1, 2),
            opened.benchmarks.compare_revisions(BENCHMARK_ID, 1, 3),
        )

    commands = (
        ["workflow", "diff", str(WORKFLOW_ID), "1", "2"],
        ["tool", "diff", str(TOOL_ID), "1", "2", "--version", TOOL_VERSION],
        ["benchmark", "diff", str(BENCHMARK_ID), "1", "3"],
    )

    for command, comparison in zip(commands, expected, strict=True):
        assert main([*command, "--output", "json"]) == 0
        printed = api.RevisionComparison.model_validate_json(capsys.readouterr().out)
        assert printed == comparison


#
# What is missing
#


def test_each_diff_says_what_is_missing(
    stocked: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["workflow", "diff", str(WORKFLOW_ID), "1", "9"]) == 1
    assert capsys.readouterr().err == f"Workflow {WORKFLOW_ID} has no revision 9.\n"
    assert main(["tool", "diff", str(TOOL_ID), "1", "2", "--version", "9.9.9"]) == 1
    assert capsys.readouterr().err == f"Tool {TOOL_ID}@9.9.9 is not configured.\n"
    assert main(["benchmark", "diff", str(BENCHMARK_ID), "9", "1"]) == 1
    assert capsys.readouterr().err == f"Benchmark dataset {BENCHMARK_ID} has no revision 9.\n"


@pytest.mark.parametrize(
    "arguments",
    [
        ["workflow", "diff", str(WORKFLOW_ID), "0", "1"],
        ["workflow", "diff", str(WORKFLOW_ID), "1"],
        ["tool", "diff", str(TOOL_ID), "1", "2"],
        ["benchmark", "diff", str(BENCHMARK_ID), "1", "2", "--output", "yaml"],
    ],
)
def test_a_diff_that_is_not_one_is_refused(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2


#
# Rendering
#


def test_a_change_renders_each_kind_of_value() -> None:
    assert render_revision_change(api.RevisionChange(kind="added", pointer="/a", after=[])) == (
        "+ /a: []"
    )
    assert render_revision_change(
        api.RevisionChange(kind="removed", pointer="/a", before=[1, 2])
    ) == ("- /a: [...]")
    assert render_revision_change(
        api.RevisionChange(kind="changed", pointer="/a", before=None, after="é")
    ) == ('~ /a: null -> "é"')


def test_a_withheld_value_says_so() -> None:
    assert render_revision_change(
        api.RevisionChange(kind="changed", pointer="/cases/0/input", withheld=True)
    ) == ("~ /cases/0/input: (withheld) -> (withheld)")


def test_identical_revisions_render_as_one_line(
    stocked: str,
) -> None:
    with api.open(stocked) as opened:
        comparison = opened.workflows.compare_revisions(WORKFLOW_ID, 3, 1)

    assert render_revision_comparison(comparison) == "Revisions 3 and 1 are identical."
