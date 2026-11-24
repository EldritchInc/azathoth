"""Tests that serving a remote and running the queue worker are tested off Windows (ADR 0142).

Their tests are marked `server` wherever they run, and skipped on Windows,
saying why, so a run lists each one it left out. Every other test, the
client's of a remote included, runs on every platform.
"""

import ast
import re
from pathlib import Path

import pytest

from tests.conftest import SERVER_MODULES, SERVER_REASON, SERVER_TESTS, TESTS, marks_for

CLIENT_MODULES = (
    "remote/test_client.py",
    "remote/test_syncing.py",
    "remote/test_pulling.py",
    "remote/test_status.py",
    "remote/test_status_of.py",
    "remote/test_protocol.py",
    "remote/test_token_commands.py",
    "remote/test_refusals.py",
    "remote/test_sse.py",
    "api/test_connected_instance.py",
    "api/test_connected_parity.py",
    "api/test_remote_connect.py",
    "api/test_remote_names.py",
    "cli/test_remote_name_commands.py",
    "cli/test_remote_option.py",
    "cli/test_running_on_a_remote.py",
    "cli/test_benchmarks_on_a_remote.py",
    "cli/test_untested_platforms.py",
)
"""Tests of reaching a remote, which Windows does, and of the warnings it is given."""

EXEMPT_MODULES = ("cli/test_untested_platforms.py", "test_platforms.py")
"""The modules that serve and run the worker as Windows would, faking which platform it is,
and this one, whose examples of serving and running the worker are only text."""

NAMES_SERVING_OR_THE_WORKER = re.compile(r'"worker",\s*"run"|"remote",\s*"serve"')
"""How a test names serving a remote or running the worker on the command line."""

RUNS_A_COMMAND = re.compile(r"\bmain\(|\brun\(capsys|\bserve\(capsys")
"""How a test runs a command line, rather than only parsing it."""

CALLS_SERVING_OR_THE_WORKER = re.compile(r"\brun_worker\(|\bserve_remote\(")
"""How a test serves a remote or runs the worker by calling it."""


def serves_or_runs_the_worker(
    source: str,
) -> bool:
    """Return whether a test's source serves a remote or runs the worker."""

    return bool(CALLS_SERVING_OR_THE_WORKER.search(source)) or bool(
        NAMES_SERVING_OR_THE_WORKER.search(source) and RUNS_A_COMMAND.search(source)
    )


def functions_of(
    module: Path,
) -> dict[str, str]:
    """Return each test function in a module, by name, with its source."""

    source = module.read_text(encoding="utf-8")

    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def names(
    marks: list[pytest.MarkDecorator],
) -> list[str]:
    return [mark.name for mark in marks]


def test_every_server_module_is_a_test_module_here() -> None:
    assert SERVER_MODULES
    assert all((TESTS / module).is_file() for module in SERVER_MODULES), sorted(
        module for module in SERVER_MODULES if not (TESTS / module).is_file()
    )


def test_every_single_server_test_is_a_test_here() -> None:
    for test in SERVER_TESTS:
        module, name = test.split("::")

        assert module not in SERVER_MODULES, test
        assert name in functions_of(TESTS / module), test


def test_every_test_that_serves_or_runs_the_worker_is_left_out_on_windows() -> None:
    unmarked = [
        f"{module}::{name}"
        for path in sorted(TESTS.rglob("test_*.py"))
        if (module := path.relative_to(TESTS).as_posix()) not in SERVER_MODULES
        and module not in EXEMPT_MODULES
        for name, source in functions_of(path).items()
        if serves_or_runs_the_worker(source) and f"{module}::{name}" not in SERVER_TESTS
    ]

    assert unmarked == []


def test_running_the_worker_counts_and_only_parsing_its_options_does_not() -> None:
    assert serves_or_runs_the_worker('main(("worker", "run", "--queue-url", URL))')
    assert serves_or_runs_the_worker('run(capsys, "remote", "serve")')
    assert serves_or_runs_the_worker("cli_worker.run_worker(URL)")
    assert not serves_or_runs_the_worker('build_parser().parse_args(("worker", "run"))')


def test_a_single_server_test_is_marked_and_skipped_on_windows_its_neighbours_not() -> None:
    module = TESTS / "cli" / "test_content_store_commands.py"
    worker = "test_a_worker_whose_s3_store_cannot_open_stops_before_it_receives"

    assert names(marks_for(module, "linux", worker)) == ["server"]
    assert names(marks_for(module, "win32", worker)) == ["server", "skip"]
    assert marks_for(module, "win32", "test_content_already_in_s3_is_not_written_again") == []


def test_no_test_of_reaching_a_remote_is_left_out_on_windows() -> None:
    assert all((TESTS / module).is_file() for module in CLIENT_MODULES)
    assert not SERVER_MODULES & set(CLIENT_MODULES)


def test_no_documentation_or_mcp_test_is_left_out_on_windows() -> None:
    assert not [module for module in SERVER_MODULES if "documented" in module]
    assert not [module for module in SERVER_MODULES if module.endswith("_docs.py")]
    assert not [module for module in SERVER_MODULES if module.endswith("_adr.py")]
    assert not [module for module in SERVER_MODULES if module.startswith("mcp/")]


def test_the_servers_and_the_workers_tests_are_the_ones_left_out() -> None:
    assert {
        "remote/test_job_runners.py",
        "remote/test_server.py",
        "remote/test_serving_lock.py",
        "remote/test_concurrent_server.py",
        "api/test_connected_job_parity.py",
        "cli/test_remote_serve_command.py",
        "worker/test_worker_processes.py",
        "cli/test_worker_command.py",
    } <= SERVER_MODULES


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_server_test_is_marked_and_runs_off_windows(
    platform: str,
) -> None:
    assert names(marks_for(TESTS / "remote" / "test_job_runners.py", platform)) == ["server"]


def test_a_server_test_is_marked_and_skipped_on_windows_saying_why() -> None:
    marks = marks_for(TESTS / "remote" / "test_job_runners.py", "win32")

    assert names(marks) == ["server", "skip"]
    assert marks[1].kwargs == {"reason": SERVER_REASON}
    assert SERVER_REASON == (
        "Serving a remote and running the queue worker are tested on Linux and macOS, and "
        "on Windows are at their operator's own risk (ADR 0142)."
    )


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_every_other_test_runs_everywhere_unmarked(
    platform: str,
) -> None:
    for module in CLIENT_MODULES:
        assert marks_for(TESTS / module, platform) == [], module

    assert marks_for(Path(__file__), platform) == []
    assert marks_for(Path("/elsewhere/test_job_runners.py"), platform) == []


def test_this_run_marks_the_server_tests(
    request: pytest.FixtureRequest,
) -> None:
    config = request.config

    assert any(line.startswith("server:") for line in config.getini("markers"))
