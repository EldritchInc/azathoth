"""Tests that serving a remote and running the worker on Windows say they are untested (ADR 0142).

Each still runs there, at its operator's own risk, after one warning. Which
platform it is is faked, so these run, and say the same, everywhere.
"""

import sys
from pathlib import Path

import pytest

import azathoth.cli.platforms as platforms
import azathoth.cli.worker as cli_worker
from azathoth.cli.platforms import SERVING_ON_WINDOWS_WARNING, WORKER_ON_WINDOWS_WARNING
from azathoth.cli.remote import runners_line, serving_line
from azathoth.remote import DEFAULT_HOST, DEFAULT_PORT
from azathoth.remote.runners import DEFAULT_RUNNERS
from tests.cli.test_remote_serve_command import Served, database, served
from tests.cli.test_remote_token_commands import run

__all__ = ["database", "served"]

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-jobs"


def windows(
    monkeypatch: pytest.MonkeyPatch,
    on: bool,
) -> None:
    """Make Azathoth take this platform for Windows, or for any other."""

    monkeypatch.setattr(platforms, "on_windows", lambda: on)


def test_the_warnings_say_what_is_untested_and_whose_risk_it_is() -> None:
    assert SERVING_ON_WINDOWS_WARNING == (
        "Serving a remote on Windows is untested and at your own risk; Azathoth tests "
        "serving on Linux and macOS (ADR 0142)."
    )
    assert WORKER_ON_WINDOWS_WARNING == (
        "Running the queue worker on Windows is untested and at your own risk; Azathoth "
        "tests it on Linux and macOS (ADR 0142)."
    )


def test_windows_is_what_python_says_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    assert platforms.on_windows()

    monkeypatch.setattr(sys, "platform", "linux")

    assert not platforms.on_windows()


def test_serving_on_windows_warns_first_and_then_serves_as_anywhere(
    database: Path,
    served: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lines = [
        serving_line(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}", accept_restricted=False),
        runners_line(DEFAULT_RUNNERS),
    ]

    windows(monkeypatch, True)

    assert run(capsys, "remote", "serve") == (
        0,
        "",
        "".join(f"{line}\n" for line in [SERVING_ON_WINDOWS_WARNING, *lines]),
    )

    windows(monkeypatch, False)

    assert run(capsys, "remote", "serve") == (0, "", "".join(f"{line}\n" for line in lines))
    assert len(served.calls) == 2


def test_running_the_worker_on_windows_warns_and_then_runs_as_anywhere(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ran: list[object] = []

    def traced(
        run_worker: object,
    ) -> int:
        ran.append(run_worker)

        return 0

    monkeypatch.setattr(cli_worker, "run_traced", traced)

    def worker() -> int:
        return cli_worker.run_worker(
            QUEUE_URL,
            result_queue_url=None,
            wait_seconds=0,
            visibility_timeout_seconds=60,
            extend_every_seconds=30,
            heartbeat_file=None,
        )

    windows(monkeypatch, True)

    assert worker() == 0
    assert capsys.readouterr().err == f"{WORKER_ON_WINDOWS_WARNING}\n"

    windows(monkeypatch, False)

    assert worker() == 0
    assert capsys.readouterr().err == ""
    assert len(ran) == 2


def test_a_worker_whose_settings_are_refused_warns_of_nothing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    windows(monkeypatch, True)

    status = cli_worker.run_worker(
        QUEUE_URL,
        result_queue_url=None,
        wait_seconds=-1,
        visibility_timeout_seconds=60,
        extend_every_seconds=30,
        heartbeat_file=None,
    )

    assert status == 1
    assert WORKER_ON_WINDOWS_WARNING not in capsys.readouterr().err
