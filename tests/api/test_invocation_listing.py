"""Contract tests for listing and resuming invocations (ADR 0128)."""

import sys
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from tests.api.test_invoke import SLOW_TOOL_ID, SLOW_WORKFLOW_ID, promote
from tests.api.test_runs import (
    COUNT_WORKFLOW_ID,
    FAIL_WORKFLOW_ID,
    MISSING_ID,
    SLEEP_WORKFLOW_ID,
    stock,
    tool_document,
)


@pytest.fixture
def promoted(
    instance: api.Azathoth,
    location: str,
) -> api.Azathoth:
    """Return an instance whose word count and failing workflows are in production."""

    stock(instance)
    promote(location, COUNT_WORKFLOW_ID, FAIL_WORKFLOW_ID)

    return instance


def cancelled_slow_invocation(
    instance: api.Azathoth,
    location: str,
) -> UUID:
    """Promote a workflow with one brief, slow step, cancel an invocation of it, and return it."""

    stock(instance)
    instance.tools.import_document(
        tool_document(
            SLOW_TOOL_ID,
            "brief_count",
            {
                "runtime": "process",
                "command": [sys.executable],
                "source": (
                    "import json\nimport sys\nimport time\n\n"
                    "json.load(sys.stdin)\ntime.sleep(0.5)\njson.dump({'count': 7}, sys.stdout)\n"
                ),
                "timeout_seconds": 60.0,
            },
        )
    )
    document = instance.workflows.get(SLEEP_WORKFLOW_ID).document
    steps = document["steps"]

    assert isinstance(steps, list)
    assert isinstance(steps[0], dict)
    assert isinstance(steps[0]["specification"], dict)

    steps[0]["specification"]["requirement"] = {
        "name": "brief_count",
        "version": "1.0.0",
        "runtime": "process",
    }
    document["metadata"] = {
        "id": str(SLOW_WORKFLOW_ID),
        "name": "brief count",
        "description": "One slow step.",
        "version": "1.0.0",
    }
    instance.workflows.import_document(document)
    promote(location, SLOW_WORKFLOW_ID)

    token = api.CancellationToken()

    def cancel_when_started(event: api.RunEvent) -> None:
        if event.type == "step_started":
            token.cancel()

    with pytest.raises(api.RunCancelledError):
        instance.runs.invoke(
            SLOW_WORKFLOW_ID,
            input="x",
            idempotency_key="slow-1",
            on_event=cancel_when_started,
            cancel=token,
        )

    (incomplete,) = instance.invocations.list(SLOW_WORKFLOW_ID)

    assert incomplete.status == "incomplete"

    return incomplete.invocation_id


# Listing


def test_invocations_are_listed_newest_first_with_their_outcomes(
    promoted: api.Azathoth,
) -> None:
    first = promoted.runs.invoke(
        COUNT_WORKFLOW_ID,
        input="one two",
        caller_metadata={"user": "eris"},
        sensitivity=api.Sensitivity.PUBLIC,
    )
    second = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="three")

    listed = promoted.invocations.list(COUNT_WORKFLOW_ID)

    assert [invocation.invocation_id for invocation in listed] == [
        second.invocation_id,
        first.invocation_id,
    ]

    newest, oldest = listed

    assert newest.status == "succeeded"
    assert newest.workflow_id == COUNT_WORKFLOW_ID
    assert newest.run_id is not None
    assert newest.command == f"azathoth invocation show {second.invocation_id}"
    assert oldest.caller_metadata == {"user": "eris"}
    assert oldest.sensitivity == api.Sensitivity.PUBLIC
    assert newest.sensitivity == api.Sensitivity.INTERNAL


def test_a_failed_invocation_is_listed_as_failed(
    promoted: api.Azathoth,
) -> None:
    promoted.runs.invoke(FAIL_WORKFLOW_ID, input="x")

    (failed,) = promoted.invocations.list(FAIL_WORKFLOW_ID)

    assert failed.status == "failed"


def test_the_limit_keeps_the_newest(
    promoted: api.Azathoth,
) -> None:
    promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")
    newest = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="b")

    (listed,) = promoted.invocations.list(COUNT_WORKFLOW_ID, limit=1)

    assert listed.invocation_id == newest.invocation_id


def test_a_limit_below_one_is_refused(
    promoted: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match=api.LIMIT_MESSAGE):
        promoted.invocations.list(COUNT_WORKFLOW_ID, limit=0)


def test_a_configured_workflow_never_invoked_lists_none(
    promoted: api.Azathoth,
) -> None:
    assert promoted.invocations.list(SLEEP_WORKFLOW_ID) == ()


def test_an_unknown_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Workflow {MISSING_ID} is not configured."):
        instance.invocations.list(MISSING_ID)


def test_a_listed_invocation_is_its_own_json(
    promoted: api.Azathoth,
) -> None:
    promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")

    (listed,) = promoted.invocations.list(COUNT_WORKFLOW_ID)

    assert api.InvocationSummary.model_validate_json(listed.model_dump_json()) == listed


# Resuming


def test_a_cancelled_invocation_is_resumed_by_its_id(
    instance: api.Azathoth,
    location: str,
) -> None:
    invocation_id = cancelled_slow_invocation(instance, location)
    events: list[api.RunEvent] = []

    resumed = instance.invocations.resume(invocation_id, on_event=events.append)

    assert resumed.status == "succeeded"
    assert resumed.result == {"result": 7}
    assert resumed.invocation_id == invocation_id
    assert resumed.idempotency_key == "slow-1"
    assert not resumed.replayed
    assert resumed.command == f"azathoth invocation show {invocation_id}"
    assert events[0] == api.RunStarted(workflow_id=SLOW_WORKFLOW_ID)
    assert events[-1] == api.InvocationFinished(invocation_id=invocation_id, status="succeeded")
    assert instance.invocations.get(invocation_id).status == "succeeded"
    assert len(open_repositories(location).invocations.invocations()) == 1


def test_a_completed_invocation_is_not_resumed(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")

    assert outcome.invocation_id is not None

    with pytest.raises(api.ConflictError) as raised:
        promoted.invocations.resume(outcome.invocation_id)

    assert str(raised.value) == f"Invocation {outcome.invocation_id} has already completed."


def test_an_unknown_invocation_is_not_resumed(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"No invocation {MISSING_ID} was found."):
        instance.invocations.resume(MISSING_ID)


def test_a_closed_instance_lists_and_resumes_nothing(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.invocations.list(COUNT_WORKFLOW_ID)

    with pytest.raises(api.InstanceClosedError):
        opened.invocations.resume(MISSING_ID)
