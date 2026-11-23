"""Tests of how each job travels, and what it tells, read from the call itself (ADR 0138)."""

import inspect
import json
from typing import Any
from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.calls import SERVICE_CALLS
from azathoth.remote.calling import (
    JOB_PARAMETERS,
    NotServedError,
    call_signature,
    job_signature,
    job_signatures,
)
from tests.api.test_calls import functions

WORKFLOW_ID = UUID("c1390000-0000-4000-8000-000000000001")

CASE_ID = UUID("c1390000-0000-4000-8000-000000000002")


def test_every_job_has_a_signature_and_nothing_else_does() -> None:
    assert sorted(job_signatures()) == sorted(call.name for call in SERVICE_CALLS if call.job)

    with pytest.raises(NotServedError, match=r"^workflows\.get is not a job"):
        job_signature("workflows.get")

    with pytest.raises(LookupError):
        job_signature("runs.fly")


def test_a_jobs_arguments_are_the_calls_but_what_its_runner_gives() -> None:
    assert frozenset({"on_event", "cancel"}) == JOB_PARAMETERS

    for name, signature in job_signatures().items():
        taken = list(inspect.signature(functions()[name]).parameters)[1:]

        assert list(signature.arguments.model_fields) == [
            parameter for parameter in taken if parameter not in JOB_PARAMETERS
        ], name
        assert set(taken) >= JOB_PARAMETERS, name


@pytest.mark.parametrize(
    ("name", "event"),
    [
        ("runs.run", api.RunStarted(workflow_id=WORKFLOW_ID)),
        ("runs.resume", api.RunFinished(run_id=WORKFLOW_ID, succeeded=True)),
        (
            "benchmarks.run",
            api.CaseStarted(case_id=CASE_ID, workflow_id=WORKFLOW_ID, index=1, total=2),
        ),
        ("optimization.optimize", api.GenerationStarted(generation=1, candidates=2, final=False)),
    ],
)
def test_a_jobs_events_travel_as_its_callback_hears_them(
    name: str,
    event: Any,
) -> None:
    signature = job_signature(name)
    written = signature.write_event(event)

    assert json.loads(written)["type"] == event.type
    assert signature.read_event(written) == event


def test_a_jobs_arguments_and_result_travel_as_a_calls_do() -> None:
    signature = job_signature("runs.run")
    body = signature.write_arguments(
        workflow_id=WORKFLOW_ID,
        input=api.RunInput(payload="one two"),
    )

    assert json.loads(body) == {"workflow_id": str(WORKFLOW_ID), "input": {"payload": "one two"}}
    assert signature.read_arguments(body)["input"] == api.RunInput(payload="one two")
    assert signature.read_arguments(body)["sensitivity"] is None


def test_a_job_is_still_no_call_answered_while_the_request_waits() -> None:
    with pytest.raises(NotServedError, match=r"^A remote runs runs\.run as a job"):
        call_signature("runs.run")
