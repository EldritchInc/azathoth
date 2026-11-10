"""Contract tests for invoking promoted workflows under idempotency keys (ADR 0120)."""

import sys
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    PRODUCTION_RESULT_EMISSION,
    WorkflowProductionEmission,
    WorkflowProductionRevision,
    WorkflowProductionState,
)
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    FAIL_WORKFLOW_ID,
    SLEEP_WORKFLOW_ID,
    stock,
    tool_document,
)

SLOW_TOOL_ID = UUID("c0000000-0000-4000-8000-000000000006")

SLOW_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000007")


def promote(
    location: str,
    *workflow_ids: UUID,
) -> None:
    """Promote each workflow's latest revision, emitting its declared result as promotion does."""

    repositories = open_repositories(location)

    for workflow_id in workflow_ids:
        revision = repositories.workflows.latest_revision(workflow_id)

        assert revision is not None
        assert revision.specification.result is not None

        state = WorkflowProductionState(
            specification=revision.specification,
            specification_revision=revision.number,
            emissions=(
                WorkflowProductionEmission(
                    name=PRODUCTION_RESULT_EMISSION,
                    source=revision.specification.result,
                ),
            ),
        )

        repositories.production_revisions.save(WorkflowProductionRevision(state=state))
        repositories.production_states.set(state)


@pytest.fixture
def promoted(
    instance: api.Azathoth,
    location: str,
) -> api.Azathoth:
    """Return an instance whose word count and failing workflows are in production."""

    stock(instance)
    promote(location, COUNT_WORKFLOW_ID, FAIL_WORKFLOW_ID)

    return instance


def test_an_invocation_returns_its_result_under_its_key(
    promoted: api.Azathoth,
    location: str,
) -> None:
    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="one two", idempotency_key="order-1")

    assert outcome.status == "succeeded"
    assert not outcome.replayed
    assert outcome.idempotency_key == "order-1"
    assert outcome.result == {"result": 2}
    assert outcome.error is None
    assert outcome.invocation_id is not None
    assert outcome.command == f"azathoth invocation show {outcome.invocation_id}"
    assert open_repositories(location).invocations.get(outcome.invocation_id) is not None


def test_an_invocation_without_a_key_is_given_one(
    promoted: api.Azathoth,
) -> None:
    first = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")
    second = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")

    assert first.idempotency_key.startswith(api.GENERATED_KEY_PREFIX)
    assert first.idempotency_key != second.idempotency_key
    assert first.invocation_id != second.invocation_id


def test_the_same_request_again_replays_its_result(
    promoted: api.Azathoth,
    location: str,
) -> None:
    first = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="one two", idempotency_key="order-1")
    again = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="one two", idempotency_key="order-1")

    assert again.replayed
    assert again.invocation_id == first.invocation_id
    assert again.result == {"result": 2}
    assert len(open_repositories(location).invocations.invocations()) == 1


def test_another_request_under_a_used_key_is_rejected(
    promoted: api.Azathoth,
) -> None:
    promoted.runs.invoke(COUNT_WORKFLOW_ID, input="one two", idempotency_key="order-1")

    conflict = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="three", idempotency_key="order-1")

    assert conflict.status == "rejected"
    assert conflict.invocation_id is None
    assert conflict.command is None
    assert conflict.error is not None
    assert conflict.error.code == "idempotency_conflict"


def test_a_failed_invocation_carries_its_production_error(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(FAIL_WORKFLOW_ID, input="x")

    assert outcome.status == "failed"
    assert outcome.result is None
    assert outcome.error is not None
    assert outcome.error.code == "workflow_execution_failed"


def test_a_workflow_not_in_production_fails_as_not_deployed(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(SLEEP_WORKFLOW_ID, input="x")

    assert outcome.status == "failed"
    assert outcome.error is not None
    assert outcome.error.code == "workflow_not_deployed"


def test_an_idempotency_key_that_is_not_one_is_refused(
    promoted: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as raised:
        promoted.runs.invoke(COUNT_WORKFLOW_ID, input="x", idempotency_key="")

    assert str(raised.value) == "An idempotency key must not be empty."


def test_caller_metadata_is_recorded_with_the_invocation(
    promoted: api.Azathoth,
    location: str,
) -> None:
    outcome = promoted.runs.invoke(
        COUNT_WORKFLOW_ID,
        input="x",
        caller_metadata={"user": "eris"},
    )

    assert outcome.invocation_id is not None

    invocation = open_repositories(location).invocations.get(outcome.invocation_id)

    assert invocation is not None
    assert invocation.caller_metadata == {"user": "eris"}


def test_an_invocation_reports_its_run_as_it_happens(
    promoted: api.Azathoth,
) -> None:
    events: list[api.RunEvent] = []

    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="one two", on_event=events.append)

    assert tuple(event.type for event in events) == (
        "run_started",
        "step_started",
        "step_finished",
        "context_changed",
        "invocation_finished",
    )
    assert events[3] == api.ContextChanged(step_id=COUNT_STEP_ID, values={"count": 2})
    assert events[4] == api.InvocationFinished(
        invocation_id=outcome.invocation_id,
        status="succeeded",
    )


def test_an_invocation_names_a_callback_that_raised(
    promoted: api.Azathoth,
) -> None:
    def fragile(event: api.RunEvent) -> None:
        raise RuntimeError("display broke")

    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a b", on_event=fragile)

    assert outcome.status == "succeeded"
    assert outcome.warnings == (
        "The event callback raised RuntimeError: display broke, and was detached.",
    )


def test_a_replayed_invocation_runs_nothing_and_reports_only_its_end(
    promoted: api.Azathoth,
) -> None:
    promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a", idempotency_key="order-1")
    events: list[api.RunEvent] = []

    promoted.runs.invoke(
        COUNT_WORKFLOW_ID,
        input="a",
        idempotency_key="order-1",
        on_event=events.append,
    )

    assert tuple(event.type for event in events) == ("invocation_finished",)


def test_a_cancelled_invocation_resumes_under_its_key(
    instance: api.Azathoth,
    location: str,
) -> None:
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

    resumed = instance.runs.invoke(SLOW_WORKFLOW_ID, input="x", idempotency_key="slow-1")

    assert resumed.status == "succeeded"
    assert resumed.result == {"result": 7}
    assert len(open_repositories(location).invocations.invocations()) == 1


def test_a_closed_instance_invokes_nothing(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.runs.invoke(COUNT_WORKFLOW_ID, input="x")


def test_a_file_is_an_invocations_input(
    promoted: api.Azathoth,
) -> None:
    request = api.RunFile(content=b"one two three", media_type="text/plain")

    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input=request, idempotency_key="file-1")
    again = promoted.runs.invoke(COUNT_WORKFLOW_ID, input=request, idempotency_key="file-1")

    assert outcome.status == "succeeded"
    assert outcome.result == {"result": 3}
    assert again.replayed


def test_a_file_that_is_not_its_media_type_invokes_nothing(
    promoted: api.Azathoth,
    location: str,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as refused:
        promoted.runs.invoke(
            COUNT_WORKFLOW_ID,
            input=api.RunFile(content=b"not a pdf", media_type="application/pdf"),
            idempotency_key="file-2",
        )

    assert str(refused.value) == (
        "Content is not application/pdf: no PDF header in its first 1024 bytes."
    )
    assert open_repositories(location).invocations.invocation_for_idempotency_key("file-2") is None
