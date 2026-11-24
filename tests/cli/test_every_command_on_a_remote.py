"""Tests that every command that runs on a remote says the same here and there (ADR 0140).

Each command that runs on a remote has a parity test: here, for the
commands no other module covers, and in the module `ELSEWHERE` names for
the rest. A script of commands runs twice from one start, here over one
database and on a remote serving a copy of it, and each step must print
the same there as here, once the times it recorded, and the IDs only one
side made, are set aside.
"""

import json
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.cli import main
from azathoth.cli.configuration import OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE
from azathoth.cli.parsing import build_parser
from azathoth.cli.parsing.targets import NEVER_ON_A_REMOTE, command_parsers
from azathoth.revisions import AUTHOR_VARIABLE
from tests.api.test_benchmark_run import stocked_benchmark
from tests.api.test_invoke import promote
from tests.api.test_models import StaticDirectory
from tests.api.test_runs import COUNT_WORKFLOW_ID, FAIL_TOOL_ID, MISSING_ID
from tests.cli.test_catalog_on_a_remote import ALPHA, BETA
from tests.cli.test_remote_option import Reaching
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

TIME_PATTERN = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(\+00:00|Z)")

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

ELSEWHERE: dict[str, str] = {
    **dict.fromkeys(
        ("workflow list", "workflow show", "workflow runs", "run show"),
        "test_reading_runs_on_a_remote",
    ),
    **dict.fromkeys(
        ("workflow run", "workflow invoke", "job run", "run resume", "invocation resume"),
        "test_running_on_a_remote",
    ),
    **dict.fromkeys(
        (
            "workflow production",
            "workflow revisions",
            "workflow invocations",
            "invocation show",
            "workflow promote",
            "workflow rollback",
        ),
        "test_production_on_a_remote",
    ),
    **dict.fromkeys(
        (
            "benchmark show",
            "benchmark add-case",
            "benchmark run",
            "benchmark compare",
            "workflow optimize",
        ),
        "test_benchmarks_on_a_remote",
    ),
    **dict.fromkeys(
        (
            "model list",
            "model show",
            "model portfolio",
            "model authorize",
            "model policy",
            "model deauthorize",
            "tool show",
            "tool implementations",
            "tool implementation-show",
            "tool test-cases",
            "tool test-case-show",
            "tool install-standard",
        ),
        "test_catalog_on_a_remote",
    ),
    **dict.fromkeys(("goal list", "goal show", "goal import"), "test_remote_option"),
}
"""The commands whose parity another module tests, and which module."""


@dataclass(frozen=True)
class Held:
    """What the database both sides start from holds, by what each is for."""

    benchmark_id: UUID
    case_ids: tuple[UUID, ...]
    run_id: UUID
    invocation_id: UUID
    execution_id: UUID
    experiment_id: UUID


def script(
    held: Held,
    files: Path,
) -> list[tuple[str, ...]]:
    """Return the script both sides run, each step one command."""

    count, missing = str(COUNT_WORKFLOW_ID), str(MISSING_ID)
    tool, benchmark = str(FAIL_TOOL_ID), str(held.benchmark_id)
    first_case, second_case = (str(case_id) for case_id in held.case_ids)
    run, invocation = str(held.run_id), str(held.invocation_id)
    experiment = str(held.experiment_id)

    return [
        # Workflows
        ("workflow", "history", count),
        ("workflow", "history", missing),
        ("workflow", "export", count),
        ("workflow", "export", count, "--revision", "9"),
        ("workflow", "import", str(files / "workflow.json")),
        ("workflow", "import", str(files / "workflow-changed.json")),
        ("workflow", "import", str(files / "missing.json")),
        ("workflow", "history", count),
        ("workflow", "diff", count, "1", "2"),
        ("workflow", "diff", count, "1", "2", "--output", "json"),
        ("workflow", "diff", count, "1", "9"),
        ("workflow", "experiments", count),
        ("workflow", "experiments", missing),
        # Runs, invocations and experiments
        ("run", "annotations", run),
        ("run", "annotations", missing),
        ("run", "children", run),
        ("run", "children", missing),
        ("run", "interrupted", count),
        ("run", "feedback", run, "--bad", "--reason", "Off by one.", "--corrected-output", "2"),
        ("run", "feedback", run, "--good"),
        ("run", "feedback", missing, "--good"),
        ("invocation", "annotations", invocation),
        ("invocation", "annotations", missing),
        ("experiment", "show", experiment),
        ("experiment", "show", missing),
        ("experiment", "compare", experiment),
        ("experiment", "compare", missing),
        # Models and judges
        ("model", "usage", ALPHA.identifier),
        ("model", "usage", "openrouter/example/unused"),
        ("judge", "list"),
        ("judge", "add", ALPHA.identifier),
        ("judge", "add", ALPHA.identifier),
        ("judge", "add", BETA.identifier),
        ("judge", "list"),
        ("judge", "remove", ALPHA.identifier),
        ("judge", "remove", ALPHA.identifier),
        ("judge", "list"),
        # Tools
        ("tool", "list"),
        ("tool", "versions", tool),
        ("tool", "versions", missing),
        ("tool", "history", tool),
        ("tool", "export", tool, "--version", "1.0.0"),
        ("tool", "export", tool, "--version", "9.9.9"),
        ("tool", "import", str(files / "tool.json")),
        ("tool", "import", str(files / "tool-changed.json")),
        ("tool", "history", tool, "--version", "1.0.0"),
        ("tool", "diff", tool, "1", "2", "--version", "1.0.0"),
        ("tool", "diff", tool, "1", "9", "--version", "1.0.0"),
        ("tool", "usage", tool),
        ("tool", "usage", missing),
        ("tool", "from-mcp", "--tool", "count"),
        ("tool", "from-mcp", "--tool", "count", "--url", "https://mcp.example.com/mcp", "--", "x"),
        # Benchmarks
        ("benchmark", "list"),
        ("benchmark", "history", benchmark),
        ("benchmark", "history", missing),
        ("benchmark", "export", benchmark),
        ("benchmark", "export", benchmark, "--revision", "9"),
        ("benchmark", "import", str(files / "benchmark.json")),
        ("benchmark", "import", str(files / "benchmark-changed.json")),
        ("benchmark", "diff", benchmark, "1", "4"),
        ("benchmark", "cases", benchmark),
        ("benchmark", "cases", missing),
        ("benchmark", "case-show", benchmark, first_case),
        ("benchmark", "executions", benchmark),
        ("benchmark", "executions", missing),
        ("benchmark", "execution-show", str(held.execution_id)),
        ("benchmark", "execution-show", missing),
        ("benchmark", "create", "--name", "made", "--description", "Made on both sides."),
        ("benchmark", "create", "--name", " ", "--description", "Refused."),
        ("benchmark", "edit-case", benchmark, first_case, "--description", "Three words."),
        ("benchmark", "edit-case", benchmark, first_case, "--description", "Three words."),
        ("benchmark", "edit-case", benchmark, missing, "--description", "Unknown."),
        ("benchmark", "remove-case", benchmark, second_case),
        ("benchmark", "remove-case", benchmark, second_case),
        ("benchmark", "cases", benchmark),
        ("benchmark", "list"),
        # Spend
        ("spend",),
        ("spend", "--group", "model"),
        ("spend", "--output", "json"),
        ("spend", "--output", "csv", "--by", "week"),
        ("spend", "--workflow", count),
    ]


def remote_commands() -> set[str]:
    """Return every command that runs on a remote."""

    return {
        command
        for command, _ in command_parsers(build_parser())
        if command not in NEVER_ON_A_REMOTE
    }


def command_of(
    step: tuple[str, ...],
    commands: set[str],
) -> str:
    """Return the command a step runs: the longest run of its first words that is one."""

    return next(
        " ".join(step[:length])
        for length in range(len(step), 0, -1)
        if " ".join(step[:length]) in commands
    )


def test_every_command_that_runs_on_a_remote_has_a_parity_test(
    tmp_path: Path,
) -> None:
    commands = remote_commands()
    held = Held(
        MISSING_ID, (MISSING_ID, MISSING_ID), MISSING_ID, MISSING_ID, MISSING_ID, MISSING_ID
    )
    here = {command_of(step, commands) for step in script(held, tmp_path)}

    assert set(ELSEWHERE) <= commands
    assert not here & set(ELSEWHERE)
    assert here | set(ELSEWHERE) == commands

    for command, module in ELSEWHERE.items():
        text = (Path(__file__).parent / f"{module}.py").read_text(encoding="utf-8")

        assert command.split()[-1] in text, (command, module)


def write_documents(
    instance: api.Azathoth,
    files: Path,
    benchmark_id: UUID,
) -> None:
    """Write the documents the script imports: each as exported, and each with a change."""

    exports = {
        "workflow": instance.workflows.export(COUNT_WORKFLOW_ID).text,
        "tool": instance.tools.export(FAIL_TOOL_ID, "1.0.0").text,
        "benchmark": instance.benchmarks.export(benchmark_id).text,
    }

    for kind, text in exports.items():
        (files / f"{kind}.json").write_text(text, encoding="utf-8")
        changed = json.loads(text)
        described = changed["definition"] if kind == "tool" else changed

        if kind == "workflow":
            described = changed["metadata"]

        described["description"] = f"The {kind} as changed."
        (files / f"{kind}-changed.json").write_text(json.dumps(changed), encoding="utf-8")


@pytest.fixture
def started(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Held, Path]]:
    """Hold runs, an invocation, a benchmark's execution and an experiment here, and copy them.

    The command line runs on the database here, and a remote named `origin`
    serves the copy. The providers here and at the remote serve Alpha and Beta.
    """

    def directory(*_: object, **__: object) -> StaticDirectory:
        return StaticDirectory("openrouter", (ALPHA, BETA))

    monkeypatch.setattr("azathoth.cli.bootstrap.OpenRouterModelDirectory", directory)
    monkeypatch.setattr("azathoth.api.instance.model_directories", lambda _settings: (directory(),))
    monkeypatch.setenv(OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE, "test-openrouter-key")
    monkeypatch.setenv(AUTHOR_VARIABLE, ERIS.name)

    here = configure_database(monkeypatch, tmp_path)
    here.touch()
    files = tmp_path / "files"
    files.mkdir()

    with api.open(here) as instance:
        benchmark_id = stocked_benchmark(
            instance,
            ("one two three", 3, "exact"),
            ("four five", 5, "exact"),
        )
        case_ids = tuple(case.case_id for case in instance.benchmarks.cases(benchmark_id))
        run = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="one two"))
        execution = instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID)
        optimized = instance.optimization.optimize(
            COUNT_WORKFLOW_ID, benchmark_id, target_latency_seconds=5.0, target_cost_usd=0.01
        )
        instance.portfolio.add(ALPHA.identifier)
        instance.portfolio.add(BETA.identifier)
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)
        write_documents(instance, files, benchmark_id)

    promote(str(here), COUNT_WORKFLOW_ID)

    with api.open(here) as instance:
        invoked = instance.runs.invoke(COUNT_WORKFLOW_ID, input="three more words")

    assert run.run_id is not None and invoked.invocation_id is not None

    there = tmp_path / "remote.db"
    shutil.copyfile(here, there)
    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")
    monkeypatch.setattr(httpx, "Client", Reaching(Served(there, principal=ERIS)))

    yield (
        Held(
            benchmark_id=benchmark_id,
            case_ids=case_ids,
            run_id=run.run_id,
            invocation_id=invoked.invocation_id,
            execution_id=execution.execution_id,
            experiment_id=optimized.winning_experiment_id,
        ),
        files,
    )


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    status = main(arguments)
    printed = capsys.readouterr()

    return status, TIME_PATTERN.sub("<TIME>", printed.out), TIME_PATTERN.sub("<TIME>", printed.err)


def comparable(
    here: tuple[int, str, str],
    there: tuple[int, str, str],
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """Return what two sides printed, with each ID only one of them printed numbered in order."""

    found = [set(UUID_PATTERN.findall(side[1] + side[2])) for side in (here, there)]
    shared = found[0] & found[1]

    def numbered(side: tuple[int, str, str]) -> tuple[int, str, str]:
        order: dict[str, str] = {}

        def name(match: re.Match[str]) -> str:
            value = match.group(0)

            if value in shared:
                return value

            return order.setdefault(value, f"<ID {len(order) + 1}>")

        return side[0], UUID_PATTERN.sub(name, side[1]), UUID_PATTERN.sub(name, side[2])

    return numbered(here), numbered(there)


def test_every_other_command_says_the_same_here_and_on_a_remote(
    started: tuple[Held, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    held, files = started
    steps = script(held, files)
    here = [said(capsys, *step) for step in steps]
    there = [said(capsys, *step, "--remote", "origin") for step in steps]

    for step, step_here, step_there in zip(steps, here, there, strict=True):
        compared_here, compared_there = comparable(step_here, step_there)

        assert compared_there == compared_here, step

    succeeded = [step for step, (status, _, _) in zip(steps, here, strict=True) if status == 0]

    assert len(succeeded) > len(steps) // 2
