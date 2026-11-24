"""Tests that ADR 0138 and the READMEs say what a remote's jobs do, exactly."""

import re
from pathlib import Path

import pytest

from azathoth import api
from azathoth.api import connected as connected_module
from azathoth.api.calls import SERVICE_CALLS
from azathoth.cli.remote import runners_line
from azathoth.persistence.repositories import open_repositories
from azathoth.remote.calling import CallerInstances
from azathoth.remote.jobs import DEFAULT_RUNNERS
from azathoth.remote.runners import (
    BEAT_SECONDS,
    INTERRUPTED_CODE,
    STALL_SECONDS,
    JobRunners,
    failed_message,
    interrupted_message,
)
from azathoth.remote.server import (
    DEFAULT_JOBS_LISTED,
    FINISHED_EVENT,
    JOB_EVENT,
    JOB_KEY_PREFIX,
    KEEP_ALIVE_SECONDS,
    MAX_JOBS_LISTED,
    NO_JOBS_MESSAGE,
)
from tests.api.test_connected_jobs import Cutting
from tests.api.test_runs import SLEEP_WORKFLOW_ID, stock
from tests.remote.test_call_routes import ERIS, Served

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0138-jobs-on-a-remote.md"

REMOTE = ROOT / "src" / "azathoth" / "remote" / "README.md"

API = ROOT / "src" / "azathoth" / "api" / "README.md"

CLI = ROOT / "src" / "azathoth" / "cli" / "README.md"

GUIDE = ROOT / "docs" / "remote.md"

ADRS = ROOT / "docs" / "adrs"

URL = "http://remote.test"


def documented(
    readme: Path,
    message: str,
) -> None:
    """Require a document to quote one message, as a line of its own."""

    assert f"\n{message}\n" in readme.read_text(encoding="utf-8")


def flat(
    document: Path,
) -> str:
    """Return a document with its lines joined, as prose reads across them."""

    return " ".join(document.read_text(encoding="utf-8").split())


def dropped_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Return what a connected instance raises when a job's stream drops too often."""

    path = tmp_path / "azathoth.db"
    path.touch()

    with api.open(path) as instance:
        stock(instance)

    served = Served(path, principal=ERIS)
    monkeypatch.setattr(connected_module, "RECONNECT_SECONDS", 0.0)
    runners = JobRunners(
        served.jobs,
        CallerInstances(open_repositories(path)),
        count=1,
        poll_seconds=0.02,
        beat_seconds=0.05,
    )

    with (
        runners,
        api.connect(URL, token="azr_test", http=Cutting(served.app, events=0, times=100)) as remote,
        pytest.raises(api.RemoteUnreachableError) as caught,
    ):
        remote.runs.run(SLEEP_WORKFLOW_ID, input=api.RunInput(payload="x"))

    (job,) = served.jobs.jobs()
    served.jobs.request_cancel(job.job_id, ERIS.name)

    return str(caught.value).replace(URL, "<URL>").replace(str(job.job_id), "<JOB_ID>")


def test_the_adr_quotes_what_a_job_says_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (job, *_) = [call.name for call in SERVICE_CALLS if call.job]
    refused = Served(tmp_path / "refused.db", principal=ERIS, runs_jobs=False).call(job)

    for message in (
        failed_message("<CALL>"),
        interrupted_message("<CALL>"),
        refused.json()["error"].replace(job, "<NAME>", 1),
        NO_JOBS_MESSAGE,
        dropped_message(tmp_path, monkeypatch),
    ):
        documented(ADR, message)


def test_the_remote_readme_quotes_what_a_job_says_exactly() -> None:
    for message in (
        failed_message("<CALL>"),
        interrupted_message("<CALL>"),
        NO_JOBS_MESSAGE,
        f"event: {JOB_EVENT}",
        f"event: {FINISHED_EVENT}",
    ):
        documented(REMOTE, message)


def test_the_service_api_readme_quotes_a_stream_given_up_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documented(API, dropped_message(tmp_path, monkeypatch))


def test_the_command_line_and_the_guide_quote_the_runners_line_exactly() -> None:
    documented(CLI, runners_line(DEFAULT_RUNNERS))
    documented(CLI, runners_line(0))
    documented(GUIDE, runners_line(DEFAULT_RUNNERS))


def test_the_numbers_the_documents_give_are_the_remotes() -> None:
    remote = flat(REMOTE)
    adr = flat(ADR)

    assert f"{DEFAULT_JOBS_LISTED} by default and up to {MAX_JOBS_LISTED}" in remote
    assert f"{DEFAULT_JOBS_LISTED} by default and up to {MAX_JOBS_LISTED}" in adr
    assert f"quiet for {KEEP_ALIVE_SECONDS:g} seconds" in remote
    assert f"quiet for {KEEP_ALIVE_SECONDS:g} seconds" in adr
    assert f"every {BEAT_SECONDS:g} seconds" in remote
    assert f"in {STALL_SECONDS:g} seconds" in remote
    assert f"after {STALL_SECONDS:g} seconds" in flat(CLI)
    assert f"`{JOB_KEY_PREFIX}<JOB_ID>`" in remote
    assert f"`{JOB_KEY_PREFIX}<JOB_ID>`" in adr
    assert f"up to {connected_module.RECONNECTS} more times" in flat(API)
    assert f"`--jobs` runners, {DEFAULT_RUNNERS} by default" in adr


def test_the_refusal_table_names_an_interrupted_job_by_its_code() -> None:
    (row,) = re.findall(r"^\| 409 \|.*$", REMOTE.read_text(encoding="utf-8"), re.MULTILINE)

    assert f"`{INTERRUPTED_CODE}`" in row


def status_of(
    number: str,
) -> str:
    """Return the status line of the decision with a number."""

    (path,) = ADRS.glob(f"{number}-*.md")

    return next(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("- Status:")
    )


def test_the_decisions_the_jobs_amend_say_so() -> None:
    for number in ("0127", "0136", "0137"):
        status = status_of(number)

        assert status.startswith("- Status: Accepted; amended by ")
        assert "ADR 0138" in status.split("amended by ", 1)[1].split(", ")

    assert "(0138-jobs-on-a-remote.md)" in (ADRS / "README.md").read_text(encoding="utf-8")


def test_the_decision_a_run_job_names_its_run_amends_the_jobs() -> None:
    assert status_of("0138") == "- Status: Accepted; amended by ADR 0139"
    assert status_of("0139") == "- Status: Accepted"
    assert "(0139-a-run-job-names-its-run.md)" in (ADRS / "README.md").read_text(encoding="utf-8")

    adr = flat(ADRS / "0139-a-run-job-names-its-run.md")

    assert f"not beaten in {STALL_SECONDS:g} seconds" in adr
    assert f"{BEAT_SECONDS:g} seconds each" in adr
