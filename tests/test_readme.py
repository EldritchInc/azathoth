"""Tests that the README's quickstart runs as it shows, and its storefront holds.

PyPI renders this README as the project's page, frozen with each release, so
everything it shows is checked here: the quickstart runs command by command,
the badges name real files and classifiers, and the sections the release
plan settled are present.
"""

import re
import shlex
from pathlib import Path

import pytest

from azathoth.cli import main
from azathoth.standard import standard_tool_documents
from tests.examples.test_word_count_benchmark_examples import configure_walkthrough

PROJECT_ROOT = Path(__file__).parents[1]

README = PROJECT_ROOT / "README.md"

WORK_WITH_US = "https://eldritchinc.com/workwithus/"

BADGES = (
    (
        "https://github.com/EldritchInc/azathoth/actions/workflows/ci.yml/badge.svg?branch=main",
        "https://github.com/EldritchInc/azathoth/actions/workflows/ci.yml",
    ),
    ("https://img.shields.io/pypi/v/azathoth-ai", "https://pypi.org/project/azathoth-ai/"),
    ("https://img.shields.io/pypi/pyversions/azathoth-ai", "https://pypi.org/project/azathoth-ai/"),
    ("https://img.shields.io/pypi/dm/azathoth-ai", "https://pypistats.org/packages/azathoth-ai"),
    (
        "https://img.shields.io/github/license/EldritchInc/azathoth",
        "https://github.com/EldritchInc/azathoth/blob/main/LICENSE",
    ),
)

RUN_LINE = re.compile(r"^(?P<id>[0-9a-f-]{36})  \S+  succeeded  \S+s  (?P<kind>\w+)  -$")


def text() -> str:
    """Return the README."""

    return README.read_text(encoding="utf-8")


def section(
    heading: str,
) -> str:
    """Return one `## ` section of the README, without its heading."""

    start = text().index(f"\n## {heading}\n") + len(f"\n## {heading}\n")
    end = text().find("\n## ", start)

    return text()[start : end if end != -1 else len(text())]


def prose(
    body: str,
) -> str:
    """Return some text with its lines joined, as it reads."""

    return " ".join(body.split())


def bash_blocks(
    body: str,
) -> list[str]:
    """Return every bash block in some text."""

    return re.findall(r"```bash\n(.*?)```", body, re.DOTALL)


def quickstart_commands() -> list[tuple[str, ...]]:
    """Return every `azathoth` command the quickstart shows, in order.

    `--version` is left out: argparse prints it and exits, and the package
    tests check the version itself.
    """

    commands = []

    for block in bash_blocks(section("Quickstart")):
        for line in block.splitlines():
            if line.startswith("azathoth ") and line != "azathoth --version":
                commands.append(tuple(shlex.split(line)[1:]))

    return commands


@pytest.fixture
def ran(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> list[tuple[tuple[str, ...], int, str]]:
    """Run the quickstart from the repository's root; return each command, status and output."""

    configure_walkthrough(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(PROJECT_ROOT)

    results = []

    for command in quickstart_commands():
        status = main(command)
        results.append((command, status, capsys.readouterr().out))

    return results


# The quickstart


def test_the_quickstart_installs_initializes_and_clones_before_it_runs() -> None:
    (install, lifecycle) = bash_blocks(section("Quickstart"))

    assert "python -m pip install azathoth-ai\n" in install
    assert install.rstrip().endswith("azathoth init")
    assert lifecycle.startswith(
        "git clone https://github.com/EldritchInc/azathoth.git\ncd azathoth\n"
    )


def test_every_quickstart_command_succeeds(
    ran: list[tuple[tuple[str, ...], int, str]],
) -> None:
    assert [command[0:2] for command, _, _ in ran] == [
        ("init",),
        ("tool", "import"),
        ("tool", "import"),
        ("workflow", "import"),
        ("workflow", "run"),
        ("benchmark", "import"),
        ("benchmark", "run"),
        ("workflow", "promote"),
        ("workflow", "invoke"),
        ("workflow", "runs"),
    ]
    assert all(status == 0 for _, status, _ in ran)


def test_the_quickstart_shows_what_each_step_really_prints(
    ran: list[tuple[tuple[str, ...], int, str]],
) -> None:
    outputs = {command[0:2]: output for command, _, output in ran}
    benchmark = outputs[("benchmark", "run")].splitlines()
    shown = section("Quickstart")

    assert outputs[("workflow", "run")] == "8\n"
    assert "It prints `8`" in prose(shown)
    assert outputs[("workflow", "invoke")] == '{"result": 8}\n'
    assert 'prints `{"result": 8}`' in prose(shown)

    (report,) = re.findall(r"```text\n(Cases Run.*?)```", shown, re.DOTALL)

    for line in report.splitlines():
        assert line in benchmark, line


def test_the_quickstart_ends_with_one_run_of_each_kind(
    ran: list[tuple[tuple[str, ...], int, str]],
) -> None:
    (*_, (_, _, listed)) = ran
    kinds = []

    for line in listed.splitlines():
        matched = RUN_LINE.match(line)

        assert matched is not None, line
        kinds.append(matched["kind"])

    assert kinds == ["production", "benchmark", "configured"]
    assert "`production`, `benchmark` and `configured`" in prose(section("Quickstart"))


# The storefront


def test_the_badges_are_the_planned_five_and_name_real_things() -> None:
    for image, target in BADGES:
        assert f"]({image})]({target})" in text(), image

    assert (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").exists()

    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for version in ("3.11", "3.12", "3.13"):
        assert f'"Programming Language :: Python :: {version}"' in pyproject


def test_commercial_support_links_the_work_with_us_page() -> None:
    assert f"]({WORK_WITH_US})" in section("Commercial Support and Pilots")


def test_the_readme_asks_for_no_funding_itself() -> None:
    assert "patreon" not in text().lower()
    assert "Support the Project" not in text()


def test_the_project_status_is_this_release_and_its_promise() -> None:
    status = section("Project Status")

    assert "Azathoth 1.1 " in status
    assert "1.0" not in status.replace("1.0.0", "")

    for promised in ("workflow, tool and job documents", "database schema", "Python API"):
        assert promised in status, promised


def test_the_readme_lists_every_standard_tool() -> None:
    for document in standard_tool_documents():
        assert f"`{document.definition.name}`" in text(), document.definition.name
