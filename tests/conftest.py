"""What holds for every test: serving and the worker are tested off Windows (ADR 0142).

Serving a remote and running the queue worker are tested on Linux and
macOS; on Windows they run at their operator's own risk. Their tests are
marked `server` wherever they run, and skipped on Windows, saying why, so
a run lists each one it left out: every test of the modules that test
them, and the few tests of them in modules that test something else.
Every other test, the client's of a remote included, runs on every
platform.
"""

import sys
from pathlib import Path
from typing import Final

import pytest

TESTS: Final = Path(__file__).parent

SERVER_MODULES: Final = frozenset(
    {
        "api/test_connected_job_parity.py",
        "api/test_connected_jobs.py",
        "cli/test_remote_serve_command.py",
        "cli/test_worker_command.py",
        "cli/test_worker_s3_inputs.py",
        "remote/test_call_audit.py",
        "remote/test_call_routes.py",
        "remote/test_concurrent_pushes.py",
        "remote/test_concurrent_server.py",
        "remote/test_conditions.py",
        "remote/test_inspection.py",
        "remote/test_job_events.py",
        "remote/test_job_routes.py",
        "remote/test_job_runners.py",
        "remote/test_job_service.py",
        "remote/test_job_submission.py",
        "remote/test_listings.py",
        "remote/test_plugin_surface.py",
        "remote/test_process_tool_push.py",
        "remote/test_seams.py",
        "remote/test_server.py",
        "remote/test_service_routes.py",
        "remote/test_serving_lock.py",
        "remote/test_thread_safe_seams.py",
        "remote/test_tokens.py",
        "worker/test_heartbeat.py",
        "worker/test_sqs.py",
        "worker/test_worker_loop.py",
        "worker/test_worker_processes.py",
    }
)
"""The modules that test serving a remote or running the queue worker, under `tests`."""

SERVER_TESTS: Final = frozenset(
    {
        "cli/test_content_store_commands.py::"
        "test_a_worker_whose_s3_store_cannot_open_stops_before_it_receives",
    }
)
"""The tests of serving or the worker in modules that test something else, each `module::name`."""

SERVER_REASON: Final = (
    "Serving a remote and running the queue worker are tested on Linux and macOS, and on "
    "Windows are at their operator's own risk (ADR 0142)."
)
"""Why a server test is skipped on Windows, as the run lists it."""

SERVER_MARKER: Final = (
    "server: tests of serving a remote or running the queue worker, skipped on Windows (ADR 0142)."
)


def marks_for(
    path: Path,
    platform: str,
    name: str = "",
) -> list[pytest.MarkDecorator]:
    """Return the marks one test gets on one platform, as `sys.platform` names it.

    `name` is the test function's name, without the parameters a
    parametrized test's runs add.
    """

    if not path.is_relative_to(TESTS):
        return []

    module = path.relative_to(TESTS).as_posix()

    if module not in SERVER_MODULES and f"{module}::{name}" not in SERVER_TESTS:
        return []

    marks = [pytest.mark.server]

    if platform == "win32":
        marks.append(pytest.mark.skip(reason=SERVER_REASON))

    return marks


def pytest_configure(
    config: pytest.Config,
) -> None:
    config.addinivalue_line("markers", SERVER_MARKER)


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    for item in items:
        name = getattr(item, "originalname", item.name)

        for mark in marks_for(item.path, sys.platform, name):
            item.add_marker(mark)
