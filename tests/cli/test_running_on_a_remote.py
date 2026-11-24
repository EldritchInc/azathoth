"""Tests that the commands that run workflows say the same here and on a remote (ADR 0140).

`workflow run`, `workflow invoke`, `job run`, `run resume` and `invocation
resume` given `--remote` make their call on that remote, where it runs as
a job, and report it as they do here: the same step messages, step and
value records, terminal record or text, warning and exit status. Each is
run over one database twice, once here and once on a remote serving it,
and what differs between two runs, their IDs and how long they took, is
set aside before the two are compared.
"""

import _thread
import json
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.cli import main
from azathoth.cli.parsing.targets import remote_refusal
from azathoth.cli.remote_runs import CHILD_RUN_MESSAGE, on_remote
from azathoth.persistence.repositories import open_repositories
from azathoth.remote.calling import CallerInstances
from azathoth.remote.jobs import ServiceJobStatus
from azathoth.remote.runners import JobRunners
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.api.test_invoke import promote
from tests.api.test_run_started import ONCE_WORKFLOW_ID, appeared, stock_once
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    FAIL_STEP_ID,
    FAIL_WORKFLOW_ID,
    MISSING_ID,
    SLEEP_WORKFLOW_ID,
    stock,
    tool_step,
    workflow,
)
from tests.cli.test_remote_option import Reaching
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

EMIT_WORKFLOW_ID = UUID("c1400000-0000-4000-8000-000000000101")

EMIT_STEP_ID = UUID("c1400000-0000-4000-8000-000000000111")

KEPT = {
    str(identifier)
    for identifier in (
        COUNT_WORKFLOW_ID,
        COUNT_STEP_ID,
        FAIL_WORKFLOW_ID,
        FAIL_STEP_ID,
        EMIT_WORKFLOW_ID,
        EMIT_STEP_ID,
        MISSING_ID,
        ONCE_WORKFLOW_ID,
    )
}
"""The IDs two runs share, kept when what they printed is compared."""

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def comparable(
    printed: str,
) -> str:
    """Return what a command printed, with what differs between two of its runs set aside."""

    named = UUID_PATTERN.sub(
        lambda found: found.group(0) if found.group(0) in KEPT else "<ID>",
        printed,
    )
    timed = re.sub(r"Duration: \d+\.\d+s", "Duration: <S>", named)

    return re.sub(r"Latency: \d+ ms", "Latency: <MS>", timed)


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    """Point the command line at a database a remote with runners serves, naming it `origin`."""

    configured = configure_database(monkeypatch, tmp_path)
    configured.touch()

    with api.open(configured) as instance:
        stock(instance)
        stock_once(instance)
        emitting = workflow(
            EMIT_WORKFLOW_ID,
            {**tool_step(EMIT_STEP_ID, "word_count", message="Emitting"), "emit_values": True},
        )
        instance.workflows.import_document(emitting)
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    promote(str(configured), COUNT_WORKFLOW_ID, FAIL_WORKFLOW_ID, ONCE_WORKFLOW_ID)

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
        yield configured


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Return what a command exits with and prints, with what differs between runs set aside."""

    status = main(arguments)
    printed = capsys.readouterr()

    return status, comparable(printed.out), comparable(printed.err)


def here_and_there(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    return said(capsys, *arguments), said(capsys, *arguments, "--remote", "origin")


RUNS = [
    ("workflow", "run", str(COUNT_WORKFLOW_ID), "--input", '"one two three"'),
    ("workflow", "run", str(COUNT_WORKFLOW_ID)),
    ("workflow", "run", str(FAIL_WORKFLOW_ID), "--input", '"x"'),
    ("workflow", "run", str(EMIT_WORKFLOW_ID), "--input", '"a b"'),
    ("workflow", "run", str(MISSING_ID)),
    ("workflow", "run", str(COUNT_WORKFLOW_ID), "--sensitivity", "restricted"),
    (
        "workflow",
        "run",
        str(COUNT_WORKFLOW_ID),
        "--input",
        '"one"',
        "--sensitivity",
        "restricted",
    ),
]


@pytest.mark.parametrize("output", ["text", "jsonl", "result"])
@pytest.mark.parametrize("command", RUNS, ids=" ".join)
def test_a_run_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
    output: str,
) -> None:
    here, there = here_and_there(capsys, *command, "--output", output)

    assert there == here


def test_a_run_given_a_file_says_the_same_here_and_on_a_remote(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    words = tmp_path / "words.txt"
    words.write_text("one two three four", encoding="utf-8")
    unknown = tmp_path / "words.unknown"
    unknown.write_text("one", encoding="utf-8")

    for given in (words, unknown, tmp_path / "missing.txt"):
        here, there = here_and_there(
            capsys,
            "workflow",
            "run",
            str(COUNT_WORKFLOW_ID),
            "--input-file",
            str(given),
            "--output",
            "jsonl",
        )

        assert there == here, given


INVOCATIONS = [
    ("workflow", "invoke", str(COUNT_WORKFLOW_ID), "--input", '"one two"'),
    ("workflow", "invoke", str(FAIL_WORKFLOW_ID), "--input", '"x"'),
    ("workflow", "invoke", str(EMIT_WORKFLOW_ID), "--input", '"x"'),
    (
        "workflow",
        "invoke",
        str(COUNT_WORKFLOW_ID),
        "--input",
        '"a b c"',
        "--sensitivity",
        "restricted",
    ),
]


@pytest.mark.parametrize("output", ["text", "jsonl", "result"])
@pytest.mark.parametrize("command", INVOCATIONS, ids=" ".join)
def test_an_invocation_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
    output: str,
) -> None:
    here, there = here_and_there(capsys, *command, "--output", output)

    assert there == here


def test_a_keyed_invocation_replays_and_refuses_another_request_alike(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key in ("order-here", "order-there"):
        remote = () if key == "order-here" else ("--remote", "origin")
        invoked = [
            said(
                capsys,
                "workflow",
                "invoke",
                str(COUNT_WORKFLOW_ID),
                "--input",
                f'"{payload}"',
                "--idempotency-key",
                key,
                "--output",
                "jsonl",
                *remote,
            )
            for payload in ("one two", "one two", "something else")
        ]

        if key == "order-here":
            here = invoked
        else:
            there = invoked

    assert [status for status, _, _ in there] == [status for status, _, _ in here] == [0, 0, 1]
    assert [out for _, out, _ in there] == [
        out.replace("order-here", "order-there") for _, out, _ in here
    ]


def test_a_job_request_says_the_same_here_and_on_a_remote(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    words = tmp_path / "words.txt"
    words.write_text("one two three", encoding="utf-8")
    requests = {
        "inline": {"workflow_id": str(COUNT_WORKFLOW_ID), "input": {"value": "one two"}},
        "file": {
            "workflow_id": str(COUNT_WORKFLOW_ID),
            "input": {"uri": words.as_uri(), "media_type": "text/plain"},
        },
        "missing file": {
            "workflow_id": str(COUNT_WORKFLOW_ID),
            "input": {"uri": (tmp_path / "gone.txt").as_uri(), "media_type": "text/plain"},
        },
        "failing": {"workflow_id": str(FAIL_WORKFLOW_ID), "input": {"value": "x"}},
        "not deployed": {"workflow_id": str(EMIT_WORKFLOW_ID), "input": {"value": "x"}},
    }

    for name, fields in requests.items():
        envelopes = []

        for where, remote in (("here", ()), ("there", ("--remote", "origin"))):
            request = tmp_path / f"{name}-{where}.json"
            request.write_text(
                json.dumps(
                    {"kind": "invoke", "version": 1, "idempotency_key": f"{name}-{where}", **fields}
                ),
                encoding="utf-8",
            )
            status, out, err = said(capsys, "job", "run", str(request), *remote)
            envelopes.append((status, out.replace(f"{name}-{where}", "<KEY>"), err))

        assert envelopes[1] == envelopes[0], name

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")

    assert said(capsys, "job", "run", str(malformed), "--remote", "origin") == said(
        capsys, "job", "run", str(malformed)
    )


# Resuming


def interrupted_run(
    path: Path,
) -> UUID:
    """Start a run whose step sleeps, stop it there, and return it."""

    marker = path.parent / f"slept-{time.monotonic_ns()}"
    token = api.CancellationToken()
    started: list[UUID] = []

    def note(event: object) -> None:
        if isinstance(event, api.RunStarted) and event.run_id is not None:
            started.append(event.run_id)

    def stop_once_sleeping() -> None:
        appeared(marker)
        token.cancel()

    stopper = threading.Thread(target=stop_once_sleeping)
    stopper.start()

    with api.open(path) as instance, pytest.raises(api.RunCancelledError):
        instance.runs.run(
            ONCE_WORKFLOW_ID,
            input=api.RunInput(payload=str(marker)),
            on_event=note,
            cancel=token,
        )

    stopper.join()

    return started[0]


def interrupted_invocation(
    path: Path,
) -> UUID:
    """Start an invocation whose step sleeps, stop it there, and return it."""

    marker = path.parent / f"slept-{time.monotonic_ns()}"
    token = api.CancellationToken()

    def stop_once_sleeping() -> None:
        appeared(marker)
        token.cancel()

    stopper = threading.Thread(target=stop_once_sleeping)
    stopper.start()

    with api.open(path) as instance:
        with pytest.raises(api.RunCancelledError):
            instance.runs.invoke(ONCE_WORKFLOW_ID, input=str(marker), cancel=token)

        stopper.join()
        (invocation,) = [
            listed
            for listed in instance.invocations.list(ONCE_WORKFLOW_ID)
            if listed.status == "incomplete"
        ]

    return invocation.invocation_id


@pytest.mark.parametrize("output", ["text", "jsonl"])
def test_a_resumed_run_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
) -> None:
    here = said(capsys, "run", "resume", str(interrupted_run(database)), "--output", output)
    there = said(
        capsys,
        "run",
        "resume",
        str(interrupted_run(database)),
        "--output",
        output,
        "--remote",
        "origin",
    )

    assert there == here
    assert here[0] == 0


@pytest.mark.parametrize("output", ["text", "jsonl"])
def test_a_resumed_invocation_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
) -> None:
    here = said(
        capsys, "invocation", "resume", str(interrupted_invocation(database)), "--output", output
    )
    there = said(
        capsys,
        "invocation",
        "resume",
        str(interrupted_invocation(database)),
        "--output",
        output,
        "--remote",
        "origin",
    )

    assert there == here
    assert here[0] == 0


def test_what_cannot_be_resumed_is_refused_alike(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with api.open(database) as instance:
        finished = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="a")).run_id

    for command in (
        ("run", "resume", str(finished)),
        ("run", "resume", str(MISSING_ID)),
        ("invocation", "resume", str(MISSING_ID)),
    ):
        here, there = here_and_there(capsys, *command)

        assert there == here, command
        assert here[0] == 1


# Stopping, and what never runs on a remote


def test_a_call_stopped_by_ctrl_c_is_cancelled_at_the_remote_before_the_command_stops() -> None:
    seen: list[bool] = []

    def waits(
        token: api.CancellationToken,
    ) -> None:
        while not token.cancelled:
            time.sleep(0.01)

        seen.append(token.cancelled)
        raise api.RunCancelledError()

    threading.Timer(0.2, _thread.interrupt_main).start()

    with pytest.raises(KeyboardInterrupt):
        on_remote(waits)

    assert seen == [True]


def test_a_run_on_a_remote_stopped_by_ctrl_c_stops_its_job_and_exits_130(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    served_jobs = open_repositories(database)

    def interrupt_once_running() -> None:
        deadline = time.monotonic() + 30.0

        while time.monotonic() < deadline:
            if any(
                job.status is ServiceJobStatus.RUNNING
                for job in Served(database, principal=ERIS).jobs.jobs()
            ):
                time.sleep(0.2)
                _thread.interrupt_main()

                return

            time.sleep(0.02)

    threading.Thread(target=interrupt_once_running, daemon=True).start()
    status = main(
        ("workflow", "run", str(SLEEP_WORKFLOW_ID), "--input", '"x"', "--remote", "origin")
    )

    assert status == 130
    assert capsys.readouterr().err.endswith("Interrupted.\n")

    (job,) = Served(database, principal=ERIS).jobs.jobs()

    assert job.status is ServiceJobStatus.CANCELLED
    assert served_jobs.runs.runs_for_workflow(SLEEP_WORKFLOW_ID) == ()


@pytest.mark.parametrize(
    "command",
    [
        ("workflow", "run", str(COUNT_WORKFLOW_ID)),
        ("workflow", "invoke", str(COUNT_WORKFLOW_ID), "--input", '"a"'),
    ],
    ids=" ".join,
)
def test_a_run_another_runs_step_started_takes_no_remote(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
) -> None:
    monkeypatch.setenv(LINEAGE_ENVIRONMENT_VARIABLE, "anything")

    assert main((*command, "--remote", "origin")) == 2
    assert capsys.readouterr().err == f"{CHILD_RUN_MESSAGE}\n"


def test_the_commands_that_run_workflows_now_run_on_a_remote() -> None:
    for command in (
        "workflow run",
        "workflow invoke",
        "job run",
        "run resume",
        "invocation resume",
    ):
        assert remote_refusal(command) is None, command


def test_a_job_request_naming_s3_is_refused_alike_here_and_on_a_remote(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    envelopes = []

    for where, remote in (("here", ()), ("there", ("--remote", "origin"))):
        request = tmp_path / f"s3-{where}.json"
        request.write_text(
            json.dumps(
                {
                    "kind": "invoke",
                    "version": 1,
                    "idempotency_key": f"s3-{where}",
                    "workflow_id": str(COUNT_WORKFLOW_ID),
                    "input": {"uri": "s3://bucket/words.txt", "media_type": "text/plain"},
                }
            ),
            encoding="utf-8",
        )
        status, out, err = said(capsys, "job", "run", str(request), *remote)
        envelopes.append((status, out.replace(f"s3-{where}", "<KEY>"), err))

    assert envelopes[1] == envelopes[0]
    assert '"code": "invalid_input"' in envelopes[0][1]
