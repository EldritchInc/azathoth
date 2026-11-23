"""Tests of submitting a job to a remote: asked, told, queued and answered at once (ADR 0138)."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth.api.calls import SERVICE_CALLS
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, AuditEventKind
from azathoth.remote.jobs import (
    JobAccepted,
    ServiceJob,
    ServiceJobStatus,
    SqlServiceJobRepository,
    job_path,
)
from azathoth.remote.server import AUDIT_UNAVAILABLE_CODE, JOB_KEY_PREFIX
from tests.remote.test_call_audit import Broken, Watching
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_conditions import Refusing
from tests.remote.test_service_routes import GUEST

WORKFLOW_ID = UUID("c13a0000-0000-4000-8000-000000000001")

BENCHMARK_ID = UUID("c13a0000-0000-4000-8000-000000000002")

RUN_ID = UUID("c13a0000-0000-4000-8000-000000000003")

INVOCATION_ID = UUID("c13a0000-0000-4000-8000-000000000004")

STEP_ID = UUID("c13a0000-0000-4000-8000-000000000005")

STEP_DOCUMENT = json.dumps({"metadata": {}})

ARGUMENTS: dict[str, dict[str, Any]] = {
    "runs.run": {"workflow_id": str(WORKFLOW_ID), "input": {"payload": "one two"}},
    "runs.try_step": {"document": STEP_DOCUMENT, "step_id": str(STEP_ID)},
    "runs.invoke": {"workflow_id": str(WORKFLOW_ID), "input": "one two"},
    "runs.resume": {"run_id": str(RUN_ID)},
    "invocations.resume": {"invocation_id": str(INVOCATION_ID)},
    "benchmarks.run": {"benchmark_id": str(BENCHMARK_ID), "workflow_id": str(WORKFLOW_ID)},
    "benchmarks.compare": {
        "benchmark_id": str(BENCHMARK_ID),
        "workflow_ids": [str(WORKFLOW_ID)],
        "target_latency_seconds": 10.0,
        "target_cost_usd": 0.5,
    },
    "optimization.optimize": {
        "workflow_id": str(WORKFLOW_ID),
        "benchmark_id": str(BENCHMARK_ID),
        "target_latency_seconds": 10.0,
        "target_cost_usd": 0.5,
    },
}
"""Arguments each job may be submitted with; nothing runs them here."""


def only(
    served: Served,
) -> ServiceJob:
    (job,) = served.jobs.jobs()

    return job


@pytest.fixture
def served(
    tmp_path: Path,
) -> Served:
    return Served(tmp_path / "azathoth.db", principal=ERIS)


def test_every_job_has_arguments_to_be_submitted_with() -> None:
    assert sorted(ARGUMENTS) == sorted(call.name for call in SERVICE_CALLS if call.job)


@pytest.mark.parametrize("name", sorted(ARGUMENTS))
def test_a_job_is_queued_as_its_caller_and_answered_at_once_with_where_to_follow_it(
    served: Served,
    name: str,
) -> None:
    answer = served.call(name, ARGUMENTS[name])
    job = only(served)
    accepted = JobAccepted.model_validate(answer.json())

    assert answer.status == 202
    assert accepted == JobAccepted.of(job)
    assert accepted.job == job_path(job.job_id) == f"/v1/jobs/{job.job_id}"
    assert accepted.events == f"/v1/jobs/{job.job_id}/events"
    assert (job.call, job.principal, job.status) == (name, "Eris", ServiceJobStatus.QUEUED)


def test_a_job_is_answered_with_where_it_is(
    served: Served,
) -> None:
    answer = served.call("runs.resume", ARGUMENTS["runs.resume"])

    assert answer.headers["location"] == f"/v1/jobs/{only(served).job_id}"


def test_a_job_keeps_only_the_arguments_given_and_what_it_names(
    served: Served,
) -> None:
    served.call("runs.run", ARGUMENTS["runs.run"])
    job = only(served)

    assert json.loads(job.arguments) == ARGUMENTS["runs.run"]
    assert job.resource == f"workflow {WORKFLOW_ID}"


def test_an_invocation_submitted_without_a_key_is_given_one_so_it_resumes(
    served: Served,
) -> None:
    served.call("runs.invoke", ARGUMENTS["runs.invoke"])
    job = only(served)

    assert json.loads(job.arguments)["idempotency_key"] == f"{JOB_KEY_PREFIX}{job.job_id}"


def test_an_invocation_submitted_with_a_key_keeps_it(
    served: Served,
) -> None:
    served.call("runs.invoke", {**ARGUMENTS["runs.invoke"], "idempotency_key": "order-412"})

    assert json.loads(only(served).arguments)["idempotency_key"] == "order-412"


# What a job asks, and tells


def test_a_job_asks_the_policy_its_actions_about_what_it_names(
    served: Served,
) -> None:
    served.call("runs.resume", ARGUMENTS["runs.resume"])

    assert served.policy.asked == [("Eris", Action.ANNOTATE_RUN, f"run {RUN_ID}")]


def test_a_job_the_policy_refuses_is_never_queued(
    tmp_path: Path,
) -> None:
    refused = Served(tmp_path / "azathoth.db", principal=GUEST)
    answer = refused.call("runs.run", ARGUMENTS["runs.run"])

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")
    assert refused.jobs.jobs() == ()
    assert [event.kind for event in refused.audit.events] == [AuditEventKind.REQUEST_DENIED]


def test_a_job_is_told_to_the_audit_before_it_is_queued(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    seen: list[Served] = []
    audit = Watching(lambda: len(seen[0].jobs.jobs()))
    served = Served(path, principal=ERIS, audit=audit)
    seen.append(served)

    served.call("runs.run", ARGUMENTS["runs.run"])
    (event,) = audit.events

    assert (event.kind, event.principal, event.resource, event.detail) == (
        AuditEventKind.WORKFLOW_RUN,
        "Eris",
        f"workflow {WORKFLOW_ID}",
        "runs.run",
    )
    assert audit.seen == [0]


def test_a_job_the_audit_cannot_be_told_of_is_never_queued(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS, audit=Broken())
    answer = served.call("runs.run", ARGUMENTS["runs.run"])

    assert (answer.status, answer.json()["code"]) == (503, AUDIT_UNAVAILABLE_CODE)
    assert served.jobs.jobs() == ()


def test_a_job_whose_arguments_are_not_its_calls_is_refused_and_never_queued(
    served: Served,
) -> None:
    answer = served.call("runs.run", {"workflow": str(WORKFLOW_ID)})

    assert (answer.status, answer.json()["code"]) == (400, "invalid_argument")
    assert answer.json()["error"].startswith("These are not the arguments runs.run takes at")
    assert served.jobs.jobs() == ()


def test_a_job_that_could_not_be_queued_is_told_to_have_failed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"

    class Full(SqlServiceJobRepository):
        def submit(
            self,
            job_id: UUID,
            *,
            call: str,
            principal: str,
            arguments: str,
            resource: str | None = None,
        ) -> ServiceJob:
            raise RuntimeError("The jobs' table is full.")

    served = Served(path, principal=ERIS, jobs=Full(open_repositories(path).database))
    answer = served.call("runs.run", ARGUMENTS["runs.run"])

    assert (answer.status, answer.json()["error"]) == (
        500,
        "This remote failed to answer runs.run; its log says why.",
    )
    assert [event.kind for event in served.audit.events] == [
        AuditEventKind.WORKFLOW_RUN,
        AuditEventKind.REQUEST_FAILED,
    ]


def test_a_job_is_submitted_only_by_a_caller_its_actions_are_allowed(
    tmp_path: Path,
) -> None:
    refused = Served(tmp_path / "azathoth.db", principal=ERIS, policy=Refusing(Action.OPTIMIZE))
    answer = refused.call("optimization.optimize", ARGUMENTS["optimization.optimize"])

    assert (answer.status, answer.json()["error"]) == (403, "Eris may not optimize.")
    assert refused.jobs.jobs() == ()
