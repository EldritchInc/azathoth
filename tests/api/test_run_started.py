"""Tests that a run names itself as it starts, so it is resumed by that name (ADR 0139)."""

import sys
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from tests.api.test_invoke import promote
from tests.api.test_runs import COUNT_WORKFLOW_ID, stock, tool_document, tool_step, workflow

ONCE_TOOL_ID = UUID("c1390000-0000-4000-8000-000000000001")

ONCE_WORKFLOW_ID = UUID("c1390000-0000-4000-8000-000000000003")

ONCE_STEP_ID = UUID("c1390000-0000-4000-8000-000000000031")

ONCE_SOURCE = (
    "import json\nimport os\nimport sys\nimport time\n\n"
    "marker = json.load(sys.stdin)['text']\n"
    "if not os.path.exists(marker):\n"
    "    open(marker, 'w').close()\n"
    "    time.sleep(60)\n"
    "json.dump({'count': 1}, sys.stdout)\n"
)
"""A tool that leaves the file its input names and sleeps the first time, and returns after."""


def stock_once(
    instance: api.Instance,
) -> None:
    """Import a workflow whose one step sleeps the first time it runs, and returns 1 after."""

    instance.tools.import_document(
        tool_document(
            ONCE_TOOL_ID,
            "sleep_once",
            {
                "runtime": "process",
                "command": [sys.executable],
                "source": ONCE_SOURCE,
                "timeout_seconds": 120.0,
            },
        )
    )
    instance.workflows.import_document(
        workflow(ONCE_WORKFLOW_ID, tool_step(ONCE_STEP_ID, "sleep_once", runtime="process"))
    )


def appeared(
    marker: Path,
    *,
    seconds: float = 30.0,
) -> None:
    """Wait for a file to appear, failing once it has not for `seconds`."""

    deadline = time.monotonic() + seconds

    while not marker.exists():
        assert time.monotonic() < deadline, f"{marker} never appeared."
        time.sleep(0.02)


@pytest.fixture
def location(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "azathoth.db"
    path.touch()

    with api.open(path) as instance:
        stock(instance)
        stock_once(instance)

    return path


def test_a_run_names_itself_as_it_starts_and_is_kept_by_that_name(
    location: Path,
) -> None:
    events: list[api.RunEvent] = []

    with api.open(location) as instance:
        result = instance.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two"),
            on_event=events.append,
        )

    assert events[0] == api.RunStarted(workflow_id=COUNT_WORKFLOW_ID, run_id=result.run_id)


def test_a_run_stopped_before_it_finished_is_resumed_by_the_name_it_started_with(
    location: Path,
) -> None:
    marker = location.parent / "slept"
    token = api.CancellationToken()
    started: list[api.RunStarted] = []

    def cancel_once_sleeping() -> None:
        appeared(marker)
        token.cancel()

    stopper = threading.Thread(target=cancel_once_sleeping)
    stopper.start()

    with api.open(location) as instance:
        with pytest.raises(api.RunCancelledError):
            instance.runs.run(
                ONCE_WORKFLOW_ID,
                input=api.RunInput(payload=str(marker)),
                on_event=lambda event: (
                    started.append(event) if isinstance(event, api.RunStarted) else None
                ),
                cancel=token,
            )

        stopper.join()
        (named,) = started

        assert named.run_id is not None
        assert [run.run_id for run in instance.runs.interrupted(ONCE_WORKFLOW_ID)] == [named.run_id]

        resumed: list[api.RunEvent] = []
        result = instance.runs.resume(named.run_id, on_event=resumed.append)

    assert (result.run_id, result.result) == (named.run_id, 1)
    assert resumed[0] == api.RunStarted(workflow_id=ONCE_WORKFLOW_ID, run_id=named.run_id)


def test_an_invocation_names_its_run_through_the_invocation(
    location: Path,
) -> None:
    promote(str(location), COUNT_WORKFLOW_ID)
    events: list[api.RunEvent] = []

    with api.open(location) as instance:
        instance.runs.invoke(COUNT_WORKFLOW_ID, input="one two", on_event=events.append)

    assert events[0] == api.RunStarted(workflow_id=COUNT_WORKFLOW_ID)
    assert events[0].run_id is None


def test_a_run_started_written_without_its_run_still_reads() -> None:
    event = api.parse_run_event(f'{{"type": "run_started", "workflow_id": "{COUNT_WORKFLOW_ID}"}}')

    assert event == api.RunStarted(workflow_id=COUNT_WORKFLOW_ID, run_id=None)
