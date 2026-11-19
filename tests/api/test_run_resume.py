"""Contract tests for finding and resuming an interrupted run through the service API (ADR 0129).

Each run is interrupted for real: started in a process of its own, and
stopped with SIGTERM while its step runs.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from tests.api.test_models import parses
from tests.cli.test_resume_commands import database, interrupted, marker
from tests.cli.test_termination import SLEEP_WORKFLOW_ID

__all__ = ["database"]

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The run is interrupted with SIGTERM, which only POSIX delivers to a handler.",
)

UNKNOWN = UUID("c1800000-0000-4000-8000-000000000001")


def interrupted_run(
    database: Path,
) -> UUID:
    """Start a run of the sleep-once workflow, stop it mid-step, and return its ID."""

    return interrupted(
        database, "workflow", "run", SLEEP_WORKFLOW_ID, "--input", json.dumps(marker(database))
    )


def test_an_interrupted_run_is_listed_with_the_command_that_resumes_it(
    database: Path,
) -> None:
    run_id = interrupted_run(database)

    with api.open(database) as instance:
        (listed,) = instance.runs.interrupted(UUID(SLEEP_WORKFLOW_ID))

    assert listed.run_id == run_id
    assert listed.workflow_id == UUID(SLEEP_WORKFLOW_ID)
    assert listed.workflow_revision == 1
    assert listed.invocation_id is None
    assert listed.resumes == 0
    assert listed.started_at <= listed.last_recorded_at
    assert listed.command == f"azathoth run resume {run_id}"
    assert parses(listed.command)


def test_an_interrupted_run_resumes_under_its_id_and_is_then_no_longer_interrupted(
    database: Path,
) -> None:
    run_id = interrupted_run(database)
    events: list[api.RunEvent] = []

    with api.open(database) as instance:
        result = instance.runs.resume(run_id, on_event=events.append)

        assert result.run_id == run_id
        assert result.succeeded
        assert result.result == "resumed"
        assert result.command == f"azathoth run show {run_id}"
        assert isinstance(events[0], api.RunStarted)
        assert events[-1] == api.RunFinished(run_id=run_id, succeeded=True)
        assert instance.runs.interrupted(UUID(SLEEP_WORKFLOW_ID)) == ()
        assert instance.runs.get(run_id).resumes == 1

        with pytest.raises(api.RunNotResumableError) as refused:
            instance.runs.resume(run_id)

    assert refused.value.code == "run_not_resumable"
    assert str(refused.value) == f"Run {run_id} has already finished."


def test_a_run_another_process_still_holds_is_not_resumed(
    database: Path,
) -> None:
    run_id = interrupted_run(database)
    now = datetime.now(UTC)

    open_repositories(database).run_leases.acquire(
        run_id,
        holder="killed-process",
        now=now,
        duration=timedelta(seconds=60),
    )

    with api.open(database) as instance, pytest.raises(api.RunNotResumableError) as refused:
        instance.runs.resume(run_id)

    assert str(refused.value).startswith(f"Run {run_id} is still running")
    assert open_repositories(database).runs.get(run_id) is None


def test_an_invocations_run_is_listed_and_resumed_as_its_invocation(
    database: Path,
) -> None:
    run_id = interrupted(
        database, "workflow", "invoke", SLEEP_WORKFLOW_ID, "--input", json.dumps(marker(database))
    )
    (invocation,) = open_repositories(database).invocations.invocations()

    with api.open(database) as instance:
        (listed,) = instance.runs.interrupted(UUID(SLEEP_WORKFLOW_ID))

        with pytest.raises(api.RunNotResumableError) as refused:
            instance.runs.resume(run_id)

    assert listed.invocation_id == invocation.id
    assert listed.command == f"azathoth invocation resume {invocation.id}"
    assert str(refused.value) == (
        f"Run {run_id} executes invocation {invocation.id}; resume it with "
        f"azathoth invocation resume {invocation.id}."
    )


def test_a_run_never_journaled_is_not_found(
    database: Path,
) -> None:
    with api.open(database) as instance, pytest.raises(api.NotFoundError) as refused:
        instance.runs.resume(UNKNOWN)

    assert str(refused.value) == f"Run {UNKNOWN} was not found."


def test_a_workflow_that_is_not_configured_has_no_interrupted_runs_to_list(
    database: Path,
) -> None:
    with api.open(database) as instance:
        assert instance.runs.interrupted(UUID(SLEEP_WORKFLOW_ID)) == ()

        with pytest.raises(api.NotFoundError) as refused:
            instance.runs.interrupted(UNKNOWN)

    assert str(refused.value) == f"Workflow {UNKNOWN} is not configured."


def test_a_cancelled_token_resumes_nothing(
    database: Path,
) -> None:
    token = api.CancellationToken()
    token.cancel()

    with api.open(database) as instance, pytest.raises(api.RunCancelledError):
        instance.runs.resume(UNKNOWN, cancel=token)
