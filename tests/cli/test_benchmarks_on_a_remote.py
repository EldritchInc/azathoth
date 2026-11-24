"""Tests that the benchmark and optimization commands say the same here and on a remote (ADR 0140).

`benchmark show`, `benchmark add-case`, `benchmark run`, `benchmark
compare` and `workflow optimize` given `--remote` make their call of that
remote's service API and print what they print here. Each is run over one
database twice, once here and once on a remote serving it, and what
differs between two runs, the IDs they make, is set aside before the two
are compared.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.api.benchmark_executions import execution_detail
from azathoth.cli import main
from azathoth.cli.parsing.targets import NOT_YET_ON_A_REMOTE
from azathoth.cli.rendering.benchmarks import render_benchmark_run
from azathoth.persistence.repositories import open_repositories
from azathoth.remote.calling import CallerInstances
from azathoth.remote.runners import JobRunners
from azathoth.workflows import decode_workflow_document
from tests.api.test_benchmark_run import (
    NO_RESULT_STEP_ID,
    NO_RESULT_WORKFLOW_ID,
    SECOND_STEP_ID,
    SECOND_WORKFLOW_ID,
    stocked_benchmark,
)
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    MISSING_ID,
    tool_step,
    workflow,
)
from tests.cli.test_remote_option import Reaching
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class Stocked:
    """The benchmarks a database holds, by what each is for."""

    def __init__(
        self,
        path: Path,
        instance: api.Azathoth,
    ) -> None:
        self.path = path
        self.counted = stocked_benchmark(
            instance,
            ("one two three", 3, "exact"),
            ("four five", 5, "exact"),
        )
        self.empty = instance.benchmarks.create("empty", "Nothing to count.").benchmark.id
        self.labelled = instance.benchmarks.create(
            "labelled", "Count restricted words."
        ).benchmark.id
        instance.benchmarks.add_case(
            self.labelled,
            input=api.RunInput(payload="secret words"),
            comparison="exact",
            expected=2,
            sensitivity=api.Sensitivity.RESTRICTED,
        )
        instance.benchmarks.add_case(
            self.labelled,
            input=api.RunInput(payload="cited words"),
            comparison="normalized",
            expected=2,
            citations=api.CaseCitations(
                require=(api.CitedSegmentSummary(source="doc-1", segment="s1"),),
                on_unverified="fail",
            ),
        )
        self.here = instance.benchmarks.create("here", "Cases added here.").benchmark.id
        self.there = instance.benchmarks.create("there", "Cases added there.").benchmark.id

    def kept(
        self,
    ) -> set[str]:
        """Return the IDs two runs share, kept when what they printed is compared."""

        return {
            str(identifier)
            for identifier in (
                COUNT_WORKFLOW_ID,
                COUNT_STEP_ID,
                SECOND_WORKFLOW_ID,
                SECOND_STEP_ID,
                NO_RESULT_WORKFLOW_ID,
                MISSING_ID,
                self.counted,
                self.empty,
                self.labelled,
            )
        }


@pytest.fixture
def stocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Stocked]:
    """Point the command line at a database a remote with runners serves, naming it `origin`."""

    configured = configure_database(monkeypatch, tmp_path)
    configured.touch()
    monkeypatch.setenv("AZATHOTH_AUTHOR", ERIS.name)

    with api.open(configured) as instance:
        held = Stocked(configured, instance)
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    document = workflow(NO_RESULT_WORKFLOW_ID, tool_step(NO_RESULT_STEP_ID, "word_count"))
    del document["result"]
    open_repositories(configured).workflows.save(decode_workflow_document(json.dumps(document)))

    served = Served(configured, principal=ERIS)
    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")
    monkeypatch.setattr(httpx, "Client", Reaching(served))
    runners = JobRunners(
        served.jobs,
        CallerInstances(open_repositories(configured)),
        count=2,
        poll_seconds=0.02,
        beat_seconds=0.05,
    )

    with runners:
        yield held


def said(
    capsys: pytest.CaptureFixture[str],
    kept: set[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Return what a command exits with and prints, with the IDs it made set aside."""

    status = main(arguments)
    printed = capsys.readouterr()

    def comparable(text: str) -> str:
        return UUID_PATTERN.sub(
            lambda found: found.group(0) if found.group(0) in kept else "<ID>",
            text,
        )

    return status, comparable(printed.out), comparable(printed.err)


def here_and_there(
    capsys: pytest.CaptureFixture[str],
    stocked: Stocked,
    *arguments: str,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    kept = stocked.kept()

    return (
        said(capsys, kept, *arguments),
        said(capsys, kept, *arguments, "--remote", "origin"),
    )


def test_a_benchmark_is_shown_the_same_here_and_on_a_remote(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for benchmark in (stocked.counted, stocked.empty, stocked.labelled, MISSING_ID):
        for revision in ((), ("--revision", "1"), ("--revision", "9")):
            here, there = here_and_there(
                capsys, stocked, "benchmark", "show", str(benchmark), *revision
            )

            assert there == here, (benchmark, revision)

    status, shown, _ = said(
        capsys, stocked.kept(), "benchmark", "show", str(stocked.labelled), "--remote", "origin"
    )

    assert status == 0
    assert "Revision: 3 of 3\n" in shown
    assert "\nSensitivity: restricted\nCited Cases: 1\nComparisons: exact 1, normalized 1\n" in (
        shown
    )


@pytest.mark.parametrize(
    "workflow_id",
    [COUNT_WORKFLOW_ID, SECOND_WORKFLOW_ID, NO_RESULT_WORKFLOW_ID, MISSING_ID],
    ids=str,
)
def test_a_benchmark_run_says_the_same_here_and_on_a_remote(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
    workflow_id: UUID,
) -> None:
    for benchmark in (stocked.counted, stocked.empty, MISSING_ID):
        here, there = here_and_there(
            capsys,
            stocked,
            "benchmark",
            "run",
            str(benchmark),
            "--workflow",
            str(workflow_id),
        )

        assert there == here, benchmark


def test_a_successful_run_on_a_remote_is_saved_there_and_reported_as_here(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, printed, _ = said(
        capsys,
        stocked.kept(),
        "benchmark",
        "run",
        str(stocked.counted),
        "--workflow",
        str(COUNT_WORKFLOW_ID),
        "--remote",
        "origin",
    )

    with api.open(stocked.path) as instance:
        (saved,) = instance.benchmarks.executions(stocked.counted)

    assert status == 0
    assert printed.splitlines() == [
        "Execution ID: <ID>",
        f"Benchmark ID: {stocked.counted}",
        f"Workflow ID: {COUNT_WORKFLOW_ID}",
        "Cases Run: 2",
        "Cases Passed: 1",
        "Accuracy: 0.500000",
        "Passed (exact): 1/2",
        "Run failures: 0",
        "Total Tokens: 0",
        "Total Latency: 0 ms",
        "Total Cost: $0.000000",
    ]
    assert saved.kind == "run"


COMPARISONS = [
    (COUNT_WORKFLOW_ID, SECOND_WORKFLOW_ID),
    (COUNT_WORKFLOW_ID, COUNT_WORKFLOW_ID),
    (COUNT_WORKFLOW_ID,),
    (COUNT_WORKFLOW_ID, NO_RESULT_WORKFLOW_ID),
    (COUNT_WORKFLOW_ID, MISSING_ID),
]


@pytest.mark.parametrize("workflow_ids", COMPARISONS, ids=lambda ids: " ".join(map(str, ids)))
def test_a_benchmark_comparison_says_the_same_here_and_on_a_remote(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
    workflow_ids: tuple[UUID, ...],
) -> None:
    named = [word for workflow_id in workflow_ids for word in ("--workflow", str(workflow_id))]

    for benchmark in (stocked.counted, stocked.empty, MISSING_ID):
        for targets in (("5", "0.01"), ("0", "0.01")):
            here, there = here_and_there(
                capsys,
                stocked,
                "benchmark",
                "compare",
                str(benchmark),
                *named,
                "--target-latency",
                targets[0],
                "--target-cost",
                targets[1],
            )

            assert there == here, (benchmark, targets)


@pytest.mark.parametrize(
    ("workflow_id", "generations"),
    [
        (COUNT_WORKFLOW_ID, "1"),
        (COUNT_WORKFLOW_ID, "2"),
        (COUNT_WORKFLOW_ID, "0"),
        (NO_RESULT_WORKFLOW_ID, "1"),
        (MISSING_ID, "1"),
    ],
)
def test_an_optimization_says_the_same_here_and_on_a_remote(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
    workflow_id: UUID,
    generations: str,
) -> None:
    for benchmark in (stocked.counted, stocked.empty, MISSING_ID):
        here, there = here_and_there(
            capsys,
            stocked,
            "workflow",
            "optimize",
            str(workflow_id),
            "--benchmark",
            str(benchmark),
            "--target-latency",
            "5",
            "--target-cost",
            "0.01",
            "--generations",
            generations,
        )

        assert there == here, benchmark


def test_a_successful_optimization_on_a_remote_records_its_experiments_there(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, printed, _ = said(
        capsys,
        stocked.kept(),
        "workflow",
        "optimize",
        str(COUNT_WORKFLOW_ID),
        "--benchmark",
        str(stocked.counted),
        "--target-latency",
        "5",
        "--target-cost",
        "0.01",
        "--remote",
        "origin",
    )

    with api.open(stocked.path) as instance:
        (recorded,) = instance.experiments.list(COUNT_WORKFLOW_ID)

    assert status == 0
    assert printed.startswith(
        f"Workflow: workflow {COUNT_WORKFLOW_ID}\nWorkflow ID: {COUNT_WORKFLOW_ID}\n"
    )
    assert "\nGeneration 1\nExperiment ID: <ID>\nEvaluated Candidates: 1\n" in printed
    assert f"\n  Step ID: {COUNT_STEP_ID}\n" in printed
    assert printed.endswith("\n\nWinning Experiment ID: <ID>\n")
    assert recorded.benchmark_id == stocked.counted


def test_a_case_is_added_the_same_here_and_on_a_remote(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    words = tmp_path / "words.txt"
    words.write_text("one two three four", encoding="utf-8")
    kept = stocked.kept()
    commands = [
        ("--input-file", str(words), "--expected", "4"),
        ("--input-file", str(words)),
        ("--input-file", str(tmp_path / "missing.txt"), "--expected", "4"),
        ("--input-file", str(words), "--expected", "4"),
        ("--input-file", str(words), "--expected", "5", "--sensitivity", "public"),
    ]

    for command in commands:
        here = said(
            capsys,
            kept,
            "benchmark",
            "add-case",
            str(stocked.here),
            "--comparison",
            "exact",
            *command,
        )
        there = said(
            capsys,
            kept,
            "benchmark",
            "add-case",
            str(stocked.there),
            "--comparison",
            "exact",
            *command,
            "--remote",
            "origin",
        )

        assert there == here, command

    with api.open(stocked.path) as instance:
        added_here = instance.benchmarks.cases(stocked.here)
        added_there = instance.benchmarks.cases(stocked.there)

    assert len(added_here) == len(added_there) == 2

    shown_here = said(
        capsys, kept, "benchmark", "case-show", str(stocked.here), str(added_here[0].case_id)
    )
    shown_there = said(
        capsys,
        kept,
        "benchmark",
        "case-show",
        str(stocked.there),
        str(added_there[0].case_id),
        "--remote",
        "origin",
    )

    assert shown_there == shown_here
    assert '"uri": "file://' in shown_there[1]


def test_a_case_added_to_an_unknown_benchmark_on_a_remote_is_refused_as_here(
    stocked: Stocked,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    words = tmp_path / "words.txt"
    words.write_text("one two", encoding="utf-8")
    here, there = here_and_there(
        capsys,
        stocked,
        "benchmark",
        "add-case",
        str(MISSING_ID),
        "--comparison",
        "exact",
        "--input-file",
        str(words),
        "--expected",
        "2",
    )

    assert there == here
    assert here[0] == 1


def test_a_run_whose_case_runs_are_gone_shows_its_totals_as_unknown(
    stocked: Stocked,
) -> None:
    with api.open(stocked.path) as instance:
        ran = instance.benchmarks.run(stocked.counted, COUNT_WORKFLOW_ID)

    saved = open_repositories(stocked.path).benchmark_executions.get(ran.execution_id)

    assert saved is not None
    assert ran.candidates[0].total_tokens == 0

    lines = render_benchmark_run(execution_detail(saved)).splitlines()

    assert lines[-3:] == [
        "Total Tokens: unknown",
        "Total Latency: unknown",
        "Total Cost: unknown",
    ]


def test_the_benchmark_commands_now_run_on_a_remote() -> None:
    assert (
        not {
            "benchmark add-case",
            "benchmark compare",
            "benchmark run",
            "benchmark show",
            "workflow optimize",
        }
        & NOT_YET_ON_A_REMOTE
    )
