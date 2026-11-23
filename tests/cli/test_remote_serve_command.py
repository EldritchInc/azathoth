"""Tests for `azathoth remote serve`, which serves an instance as a remote (ADR 0124)."""

import sys
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.testclient import TestClient

import azathoth.cli.application as application
import azathoth.remote.seams as seams
from azathoth.cli import build_parser, main
from azathoth.cli.remote import runners_line, serving_line
from azathoth.persistence import SQLiteLocation
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MISSING_REMOTE_EXTRA_MESSAGE,
    REMOTE_PLUGIN_GROUP,
    SQLiteRemoteTokenRepository,
)
from azathoth.remote.serving import RemoteAlreadyServedError, serving_lock
from azathoth.revisions import AUTHOR_VARIABLE
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_remote_token_commands import ERIS, run
from tests.cli.test_workflow_run import configure_database


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an empty database, as Eris, with no runtime to load."""

    configured = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTHOR_VARIABLE, str(ERIS))
    forbid_runtime(monkeypatch)

    return configured


class Served:
    """What `remote serve` handed uvicorn."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        app: Any,
        **options: Any,
    ) -> None:
        self.calls.append({"app": app, **options})


@pytest.fixture
def served(
    monkeypatch: pytest.MonkeyPatch,
) -> Served:
    """Stand in for uvicorn, so serving returns at once."""

    stand_in = Served()
    monkeypatch.setattr(uvicorn, "run", stand_in)

    return stand_in


def test_serve_listens_on_this_machine_by_default() -> None:
    parsed = build_parser().parse_args(("remote", "serve"))

    assert (parsed.remote_host, parsed.remote_port, parsed.remote_accept_restricted) == (
        "127.0.0.1",
        8470,
        False,
    )
    assert (DEFAULT_HOST, DEFAULT_PORT) == ("127.0.0.1", 8470)

    told = build_parser().parse_args(
        ("remote", "serve", "--host", "0.0.0.0", "--port", "9000", "--accept-restricted")
    )

    assert (told.remote_host, told.remote_port, told.remote_accept_restricted) == (
        "0.0.0.0",
        9000,
        True,
    )


def test_the_cli_dispatches_serve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def serve(**options: object) -> int:
        calls.append(options)
        return 0

    monkeypatch.setattr(application, "serve_remote", serve)

    assert main(("remote", "serve", "--port", "9000")) == 0
    assert calls == [{"host": "127.0.0.1", "port": 9000, "accept_restricted": False, "jobs": 2}]


@pytest.mark.parametrize("accept", [False, True], ids=["refusing", "accepting"])
def test_serve_serves_the_configured_database_with_its_tokens(
    database: Path,
    served: Served,
    capsys: pytest.CaptureFixture[str],
    accept: bool,
) -> None:
    secret = SQLiteRemoteTokenRepository(database).create("laptop").secret
    options = ("--accept-restricted",) if accept else ()

    status, out, err = run(capsys, "remote", "serve", "--port", "9000", *options)
    (call,) = served.calls

    assert (status, out) == (0, "")
    assert err == (
        f"{serving_line('http://127.0.0.1:9000', accept_restricted=accept)}\n{runners_line(2)}\n"
    )
    assert (call["host"], call["port"], call["log_level"]) == ("127.0.0.1", 9000, "info")
    assert isinstance(call["app"], Starlette)

    client = TestClient(call["app"])
    capabilities = client.get(
        "/v1/capabilities",
        headers={"Authorization": f"Bearer {secret}"},
    ).json()

    assert capabilities["accepts_restricted"] is accept


def test_a_second_server_on_one_sqlite_database_is_refused_and_serves_nothing(
    database: Path,
    served: Served,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with serving_lock(SQLiteLocation(path=database)):
        refused = run(capsys, "remote", "serve")

    assert refused == (1, "", f"{RemoteAlreadyServedError(database)}\n")
    assert served.calls == []


def test_a_server_holds_the_lock_for_as_long_as_it_serves(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusals: list[RemoteAlreadyServedError] = []

    def serve(
        app: Any,
        **options: Any,
    ) -> None:
        try:
            with serving_lock(SQLiteLocation(path=database)):
                pass
        except RemoteAlreadyServedError as refusal:
            refusals.append(refusal)

    monkeypatch.setattr(uvicorn, "run", serve)

    assert run(capsys, "remote", "serve")[0] == 0
    assert len(refusals) == 1

    with serving_lock(SQLiteLocation(path=database)):
        pass


def test_other_commands_go_on_working_beside_a_server(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with serving_lock(SQLiteLocation(path=database)):
        assert run(capsys, "remote", "token", "list") == (0, "", "")


def test_the_serving_line_says_whether_restricted_data_is_taken() -> None:
    assert serving_line("http://127.0.0.1:8470", accept_restricted=False) == (
        "Serving remote protocol 1 at http://127.0.0.1:8470; it refuses restricted data."
    )
    assert serving_line("http://0.0.0.0:8470", accept_restricted=True) == (
        "Serving remote protocol 1 at http://0.0.0.0:8470; it accepts restricted data."
    )


@pytest.mark.parametrize("missing", ["uvicorn", "starlette.applications"])
def test_without_the_remote_extra_nothing_is_served(
    database: Path,
    served: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    monkeypatch.setitem(sys.modules, missing, None)
    monkeypatch.delitem(sys.modules, "azathoth.remote.server", raising=False)

    assert run(capsys, "remote", "serve") == (1, "", f"{MISSING_REMOTE_EXTRA_MESSAGE}\n")
    assert served.calls == []
    assert MISSING_REMOTE_EXTRA_MESSAGE == (
        "azathoth remote serve needs starlette and uvicorn, which are not installed; install "
        "azathoth-ai[remote]."
    )


def test_plugins_the_remote_cannot_use_serve_nothing(
    database: Path,
    served: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed = (
        EntryPoint(name="policy", value="first:policy", group=REMOTE_PLUGIN_GROUP),
        EntryPoint(name="policy", value="second:policy", group=REMOTE_PLUGIN_GROUP),
    )
    monkeypatch.setattr(seams, "entry_points", lambda group: installed)

    assert run(capsys, "remote", "serve") == (
        1,
        "",
        "Two plugins fill the remote's policy seam, first:policy and second:policy; uninstall "
        "one of them.\n",
    )
    assert served.calls == []


def test_the_guides_quote_serving_exactly() -> None:
    root = Path(__file__).parents[2]
    readme = (root / "src" / "azathoth" / "cli" / "README.md").read_text(encoding="utf-8")
    install = (root / "docs" / "install.md").read_text(encoding="utf-8")

    for accept in (False, True):
        line = serving_line(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}", accept_restricted=accept)

        assert f"\n{line}\n" in readme

    assert f"\n{MISSING_REMOTE_EXTRA_MESSAGE}\n" in readme
    assert f"\n{MISSING_REMOTE_EXTRA_MESSAGE}\n" in install


# Running jobs


def test_serve_runs_two_jobs_at_once_unless_told_otherwise() -> None:
    assert build_parser().parse_args(("remote", "serve")).remote_jobs == 2
    assert build_parser().parse_args(("remote", "serve", "--jobs", "5")).remote_jobs == 5
    assert build_parser().parse_args(("remote", "serve", "--jobs", "0")).remote_jobs == 0


@pytest.mark.parametrize("count", ["-1", "many"])
def test_a_count_of_jobs_that_is_no_number_from_0_is_refused(
    capsys: pytest.CaptureFixture[str],
    count: str,
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(("remote", "serve", "--jobs", count))

    assert f"A server runs a number of jobs at once from 0, not {count}." in (
        capsys.readouterr().err
    )


class Watching:
    """A stand-in for uvicorn that asks the app it is handed how its jobs stand."""

    def __init__(
        self,
        secret: str,
    ) -> None:
        self.secret = secret
        self.service: dict[str, Any] = {}

    def __call__(
        self,
        app: Any,
        **options: Any,
    ) -> None:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {self.secret}"}
        self.service = client.get("/v1/service", headers=headers).json()
        self.submitted = client.post(
            "/v1/calls/runs.resume",
            json={"run_id": "c13d0000-0000-4000-8000-000000000001"},
            headers=headers,
        ).status_code


@pytest.mark.parametrize("jobs", [1, 3])
def test_serve_runs_its_jobs_while_it_serves_and_forgets_its_runners_after(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    jobs: int,
) -> None:
    secret = SQLiteRemoteTokenRepository(database).create("laptop").secret
    watching = Watching(secret)
    monkeypatch.setattr(uvicorn, "run", watching)

    status, _, err = run(capsys, "remote", "serve", "--jobs", str(jobs))

    assert status == 0
    assert err.endswith(f"{runners_line(jobs)}\n")
    assert watching.service["jobs"]["runners"] == jobs
    assert watching.submitted == 202
    assert open_repositories(database).service_jobs.runners() == ()


def test_serve_with_no_jobs_queues_them_for_another_server(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = SQLiteRemoteTokenRepository(database).create("laptop").secret
    watching = Watching(secret)
    monkeypatch.setattr(uvicorn, "run", watching)

    status, _, err = run(capsys, "remote", "serve", "--jobs", "0")
    (queued,) = open_repositories(database).service_jobs.jobs()

    assert status == 0
    assert err.endswith(
        "It runs no jobs; it queues them for another server over its database to run.\n"
    )
    assert (watching.service["jobs"]["runners"], watching.submitted) == (0, 202)
    assert (queued.call, queued.status.value) == ("runs.resume", "queued")


def test_the_runners_line_says_how_many_jobs_run_at_once() -> None:
    assert runners_line(1) == "It runs 1 job at once."
    assert runners_line(2) == "It runs 2 jobs at once."
