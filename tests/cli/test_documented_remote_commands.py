"""Tests that ADR 0140, the READMEs, the guide and the changelog say what `--remote` does.

The command line's README lists every command and option the parser has,
and every command that never runs on a remote with the sentence it says.
Each document quotes what a command says exactly, and names the fields the
service API's views gained.
"""

import re
from pathlib import Path

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from azathoth.cli.parsing.targets import NEVER_ON_A_REMOTE, command_parsers
from azathoth.cli.remote_choice import LOCAL_DATABASE_MESSAGE
from azathoth.cli.remote_runs import CANCEL_WAIT_SECONDS, CHILD_RUN_MESSAGE

ROOT = Path(__file__).parents[2]

ADRS = ROOT / "docs" / "adrs"

ADR = ADRS / "0140-the-command-line-on-a-remote.md"

CLI = ROOT / "src" / "azathoth" / "cli" / "README.md"

API = ROOT / "src" / "azathoth" / "api" / "README.md"

GUIDE = ROOT / "docs" / "remote.md"

CHANGELOG = ROOT / "CHANGELOG.md"

BRANCH = re.compile(r"^((?:│   |    )*)(?:├── |└── )(.*)$")
"""One line of the command tree: how deep it is, and what it names."""

VIEW_FIELDS: dict[str, tuple[str, ...]] = {
    "RunSummary": ("source",),
    "RunDetail": ("lineage", "evaluations"),
    "RunStepDetail": ("resources",),
    "InvocationSummary": ("error_code",),
    "ProductionState": ("emissions",),
    "InvocationDetail": ("request_digest", "lineage", "input_provenance", "citations"),
    "BenchmarkDetail": ("cited_cases", "comparisons"),
    "ExecutionCandidate": ("total_tokens", "total_latency_ms", "total_cost_usd"),
    "OptimizationSummary": ("workflow_name", "initial_candidates", "final_experiment"),
}
"""The fields each view gained so the command line prints from it."""


def text(
    document: Path,
) -> str:
    return document.read_text(encoding="utf-8")


def flat(
    document: Path,
) -> str:
    """Return a document with its lines joined, as prose reads across them."""

    return " ".join(text(document).split())


def documented(
    document: Path,
    message: str,
) -> None:
    """Require a document to quote one message, as a line of its own."""

    assert f"\n{message}\n" in text(document), (document.name, message)


def command_tree() -> tuple[set[str], dict[str, set[str]]]:
    """Return the commands the README's tree names, and the options it names under each."""

    tree = text(CLI).split("# V1 Command Surface", 1)[1].split("```text\n", 1)[1]
    tree = tree.split("```", 1)[0]
    commands: set[str] = set()
    options: dict[str, set[str]] = {}
    path: list[str] = []

    for line in tree.splitlines():
        branch = BRANCH.match(line)

        if branch is None:
            continue

        depth = len(branch.group(1)) // 4
        named = branch.group(2)

        if named.startswith("-"):
            options.setdefault(" ".join(path[:depth]), set()).update(
                re.findall(r"--[a-z][a-z-]*", named)
            )
        else:
            path = [*path[:depth], named.split()[0]]
            commands.add(" ".join(path))

    return commands, options


def test_the_command_tree_names_every_command_and_option() -> None:
    commands, options = command_tree()

    for command, parser in command_parsers(build_parser()):
        assert command in commands, command

        taken = {
            option
            for action in parser._actions
            for option in action.option_strings
            if option.startswith("--") and option not in ("--help", "--remote")
        }

        assert taken <= options.get(command, set()), (command, taken - options.get(command, set()))


def test_the_command_line_names_every_command_that_never_runs_on_a_remote() -> None:
    rows = re.findall(r"^\| `([a-z -]+)` \| (.+) \|$", text(CLI), re.MULTILINE)
    never = {command: said for command, said in rows if command in NEVER_ON_A_REMOTE}

    assert never == dict(NEVER_ON_A_REMOTE)
    assert "Every command but fourteen takes `--remote <NAME>`" in flat(CLI)
    assert len(NEVER_ON_A_REMOTE) == 14


def test_the_command_line_quotes_what_a_command_on_a_remote_says(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    path.touch()

    with api.open(path) as instance, pytest.raises(api.NotFoundError) as raised:
        instance.remote("nowhere").connect()

    documented(CLI, str(raised.value))
    documented(CLI, CHILD_RUN_MESSAGE)
    documented(CLI, "The remote at <URL> could not be reached: <REASON>")
    assert f"up to {CANCEL_WAIT_SECONDS:g} seconds" in flat(CLI)


def test_the_decision_quotes_what_the_command_line_says() -> None:
    documented(ADR, LOCAL_DATABASE_MESSAGE)
    documented(ADR, CHILD_RUN_MESSAGE)
    documented(ADR, NEVER_ON_A_REMOTE["tool verify"])

    decision = flat(ADR)

    for command in NEVER_ON_A_REMOTE:
        assert f"`{command}`" in decision, command

    assert f"up to {CANCEL_WAIT_SECONDS:g} seconds" in decision


def test_the_decision_amends_the_one_it_says_and_is_listed() -> None:
    status = next(
        line
        for line in text(ADRS / "0127-the-remote-serves-the-service-api.md").splitlines()
        if line.startswith("- Status:")
    )

    assert status.endswith(", ADR 0140")
    assert "\n- Status: Accepted\n" in text(ADR)
    assert "(0140-the-command-line-on-a-remote.md)" in text(ADRS / "README.md")


def test_the_service_api_names_every_field_the_command_line_prints_from() -> None:
    section = text(API).split("\n## What the Command Line Prints\n", 1)[1].split("\n## ", 1)[0]

    for view, fields in VIEW_FIELDS.items():
        (row,) = [line for line in section.splitlines() if line.startswith(f"| `{view}` |")]
        model = getattr(api, view)

        for field in fields:
            assert field in model.model_fields, (view, field)
            assert f"`{field}`" in row, (view, field)

    for call in ("definition", "implementations", "implementation", "test_cases", "test_case"):
        assert f"`tools.{call}`" in section, call


def test_the_guide_and_the_changelog_say_what_runs_on_a_remote() -> None:
    documented(GUIDE, NEVER_ON_A_REMOTE["init"])

    changelog = text(CHANGELOG).split("\n## ", 2)[1]

    for name in ("0139-a-run-job-names-its-run", "0140-the-command-line-on-a-remote"):
        assert (
            f"(https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/{name}.md)" in changelog
        ), name
