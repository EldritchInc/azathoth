"""Contract tests for reading an invocation back (ADR 0120)."""

from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.telemetry.conventions import INVOCATION_SPAN, RUN_SPAN, STEP_SPAN
from azathoth.workflows import create_production_invocation
from tests.api.test_invoke import promote
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    FAIL_STEP_ID,
    FAIL_WORKFLOW_ID,
    stock,
)
from tests.telemetry.fakes import RecordingTelemetry

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")


@pytest.fixture
def promoted(
    instance: api.Azathoth,
    location: str,
) -> api.Azathoth:
    """Return an instance whose word count and failing workflows are in production."""

    stock(instance)
    promote(location, COUNT_WORKFLOW_ID, FAIL_WORKFLOW_ID)

    return instance


def test_a_succeeded_invocation_is_read_back_with_its_run(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(
        COUNT_WORKFLOW_ID,
        input="one two",
        idempotency_key="order-1",
        caller_metadata={"user": "eris"},
    )

    assert outcome.invocation_id is not None

    detail = promoted.invocations.get(outcome.invocation_id)

    assert detail.invocation_id == outcome.invocation_id
    assert detail.workflow_id == COUNT_WORKFLOW_ID
    assert detail.status == "succeeded"
    assert detail.result == {"result": 2}
    assert detail.error is None
    assert detail.idempotency_key == "order-1"
    assert detail.input == "one two"
    assert detail.caller_metadata == {"user": "eris"}
    assert detail.command == f"azathoth invocation show {outcome.invocation_id}"
    assert detail.run is not None
    assert detail.run.finished
    assert detail.run.resumes == 0
    assert detail.run.workflow_revision == 1
    assert detail.run.halted is False
    assert detail.run.steps == (
        api.RunStep(step_id=COUNT_STEP_ID, status="executed", attempts=1, confidence=None),
    )


def test_a_failed_invocation_is_read_back_with_its_error(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(FAIL_WORKFLOW_ID, input="x")

    assert outcome.invocation_id is not None

    detail = promoted.invocations.get(outcome.invocation_id)

    assert detail.status == "failed"
    assert detail.result is None
    assert detail.error == outcome.error
    assert detail.run is not None
    assert tuple(step.status for step in detail.run.steps) == ("failed",)
    assert detail.run.steps[0].step_id == FAIL_STEP_ID


def test_an_invocation_without_a_result_is_incomplete(
    instance: api.Azathoth,
    location: str,
) -> None:
    invocation = create_production_invocation(workflow_id=COUNT_WORKFLOW_ID, payload={"a": 1})
    open_repositories(location).invocations.save(invocation)

    detail = instance.invocations.get(invocation.id)

    assert detail.status == "incomplete"
    assert detail.result is None
    assert detail.error is None
    assert detail.idempotency_key is None
    assert detail.input == {"a": 1}
    assert detail.run is None


def test_an_unknown_invocation_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.invocations.get(MISSING_ID)

    assert str(raised.value) == f"No invocation {MISSING_ID} was found."


def test_an_invocation_is_its_own_json(
    promoted: api.Azathoth,
) -> None:
    outcome = promoted.runs.invoke(COUNT_WORKFLOW_ID, input="a")

    assert outcome.invocation_id is not None

    detail = promoted.invocations.get(outcome.invocation_id)

    assert api.InvocationDetail.model_validate_json(detail.model_dump_json()) == detail


def test_a_closed_instance_reads_no_invocation(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.invocations.get(MISSING_ID)


def test_an_instance_given_telemetry_traces_its_invocations_and_runs(
    location: str,
) -> None:
    telemetry = RecordingTelemetry()

    with api.open(location, telemetry=telemetry) as instance:
        stock(instance)
        promote(location, COUNT_WORKFLOW_ID)
        instance.runs.invoke(COUNT_WORKFLOW_ID, input="a")
        instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="a"))

    names = [span.name for span in telemetry.spans]

    assert names == [INVOCATION_SPAN, RUN_SPAN, STEP_SPAN, RUN_SPAN, STEP_SPAN]
    assert telemetry.spans[1].parent is telemetry.spans[0]
