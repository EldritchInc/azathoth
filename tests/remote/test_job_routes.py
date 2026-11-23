"""Tests of reading, listing and cancelling a remote's jobs, for who may (ADR 0138)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, AuditEventKind, Principal
from azathoth.remote.calling import CallerInstances
from azathoth.remote.job_reading import restricted
from azathoth.remote.jobs import JobSummary, JobView, ServiceJob, ServiceJobStatus
from azathoth.remote.server import AUDIT_UNAVAILABLE_CODE, NO_JOBS_MESSAGE
from azathoth.sensitivity import Sensitivity
from tests.remote.asgi import Answer, call
from tests.remote.test_call_audit import Broken, Watching
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_conditions import Refusing, benchmark_with_a_case

WORKFLOW_ID = UUID("c13b0000-0000-4000-8000-000000000001")

MISSING = UUID("c13b0000-0000-4000-8000-0000000000ff")

DISCORDIA = Principal(name="Discordia", owner=True)

RUN_ID = "c13b0000-0000-4000-8000-0000000000aa"

RESULT = {"run_id": RUN_ID, "succeeded": True}


def get(
    served: Served,
    path: str,
) -> Answer:
    return call(served.app, "GET", path)


def cancel(
    served: Served,
    job_id: UUID,
) -> Answer:
    return call(served.app, "POST", f"/v1/jobs/{job_id}/cancel")


def submitted(
    served: Served,
    *,
    sensitivity: str | None = None,
) -> UUID:
    """Submit a run of a workflow, and return its job's ID."""

    arguments: dict[str, object] = {"workflow_id": str(WORKFLOW_ID), "input": {"payload": "x"}}

    if sensitivity is not None:
        arguments["sensitivity"] = sensitivity

    answer = served.call("runs.run", arguments)
    assert answer.status == 202, answer.json()

    return UUID(answer.json()["job_id"])


def succeeded(
    served: Served,
    job_id: UUID,
) -> None:
    """End a job as a runner would, with a result."""

    claimed = served.jobs.claim("runner-test")
    assert claimed is not None and claimed.job_id == job_id
    served.jobs.finish(
        job_id,
        "runner-test",
        ServiceJobStatus.SUCCEEDED,
        result=json.dumps(RESULT),
    )


@pytest.fixture
def served(
    tmp_path: Path,
) -> Served:
    return Served(tmp_path / "azathoth.db", principal=ERIS)


# Reading a job


def test_a_job_is_answered_to_its_submitter_with_where_it_has_got(
    served: Served,
) -> None:
    job_id = submitted(served)
    answer = get(served, f"/v1/jobs/{job_id}")
    view = JobView.model_validate(answer.json())

    assert answer.status == 200
    assert (view.job_id, view.call, view.principal, view.status) == (
        job_id,
        "runs.run",
        "Eris",
        ServiceJobStatus.QUEUED,
    )
    assert (view.has_result, view.result, view.refusal) == (False, None, None)
    assert view.events == f"/v1/jobs/{job_id}/events"
    assert "arguments" not in answer.json()


def test_a_job_that_succeeded_is_answered_with_its_result(
    served: Served,
) -> None:
    job_id = submitted(served)
    succeeded(served, job_id)
    view = JobView.model_validate(get(served, f"/v1/jobs/{job_id}").json())

    assert (view.status, view.has_result, view.result) == (
        ServiceJobStatus.SUCCEEDED,
        True,
        RESULT,
    )


def test_a_job_that_failed_is_answered_with_its_refusal(
    served: Served,
) -> None:
    job_id = submitted(served)
    served.jobs.claim("runner-test")
    refusal = {"error": "Gone.", "code": "not_found", "kinds": ["not_found", "error"]}
    served.jobs.finish(
        job_id,
        "runner-test",
        ServiceJobStatus.FAILED,
        refusal=json.dumps(refusal),
        refusal_status=404,
    )
    view = JobView.model_validate(get(served, f"/v1/jobs/{job_id}").json())

    assert (view.status, view.refusal, view.refusal_status) == (
        ServiceJobStatus.FAILED,
        refusal,
        404,
    )


def test_reading_a_job_is_not_audited(
    served: Served,
) -> None:
    job_id = submitted(served)
    before = list(served.audit.events)
    get(served, f"/v1/jobs/{job_id}")
    get(served, "/v1/jobs")

    assert served.audit.events == before


@pytest.mark.parametrize("named", [str(MISSING), "not-a-job"])
def test_a_job_the_remote_does_not_have_is_not_found(
    served: Served,
    named: str,
) -> None:
    answer = get(served, f"/v1/jobs/{named}")

    assert (answer.status, answer.json()) == (
        404,
        {
            "error": f"This remote has no job {named}.",
            "code": "not_found",
            "kinds": ["not_found", "error"],
        },
    )


def test_a_remote_that_runs_no_jobs_has_none_to_answer_about(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS, runs_jobs=False)

    for answer in (
        get(served, "/v1/jobs"),
        get(served, f"/v1/jobs/{MISSING}"),
        cancel(served, MISSING),
    ):
        assert (answer.status, answer.json()) == (
            404,
            {"error": NO_JOBS_MESSAGE, "code": "not_found"},
        )


def test_a_job_needs_a_caller_the_remote_knows(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=None)

    assert call(served.app, "GET", "/v1/jobs", authorization=None).status == 401


# Another's job


def test_another_callers_job_is_answered_to_who_may_read_runs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    job_id = submitted(Served(path, principal=ERIS))
    other = Served(path, principal=DISCORDIA)

    assert get(other, f"/v1/jobs/{job_id}").status == 200
    assert other.policy.asked == [("Discordia", Action.READ_RUNS, f"job {job_id}")]


def test_another_callers_job_is_refused_to_who_may_not_read_runs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    job_id = submitted(Served(path, principal=ERIS))
    refused = Served(path, principal=DISCORDIA, policy=Refusing(Action.READ_RUNS))
    answer = get(refused, f"/v1/jobs/{job_id}")

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")
    assert [event.kind for event in refused.audit.events] == [AuditEventKind.REQUEST_DENIED]


def test_a_submitters_own_job_asks_the_policy_nothing(
    served: Served,
) -> None:
    job_id = submitted(served)
    asked = len(served.policy.asked)
    get(served, f"/v1/jobs/{job_id}")

    assert len(served.policy.asked) == asked


# Restricted results


def test_a_restricted_result_is_sent_only_to_who_may_read_restricted_and_told_first(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    served = Served(path, principal=ERIS)
    job_id = submitted(served, sensitivity="restricted")
    succeeded(served, job_id)
    refused = Served(path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED))
    answer = get(refused, f"/v1/jobs/{job_id}")

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")
    assert RUN_ID not in answer.body.decode()

    allowed = Served(path, principal=ERIS)
    view = JobView.model_validate(get(allowed, f"/v1/jobs/{job_id}").json())

    assert view.result == RESULT
    assert [(event.kind, event.resource, event.detail) for event in allowed.audit.events] == [
        (AuditEventKind.RESTRICTED_READ, f"job {job_id}", "runs.run")
    ]


def test_a_restricted_result_the_audit_cannot_be_told_of_is_not_sent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    served = Served(path, principal=ERIS)
    job_id = submitted(served, sensitivity="restricted")
    succeeded(served, job_id)
    answer = get(Served(path, principal=ERIS, audit=Broken()), f"/v1/jobs/{job_id}")

    assert (answer.status, answer.json()["code"]) == (503, AUDIT_UNAVAILABLE_CODE)
    assert RUN_ID not in answer.body.decode()


def test_a_restricted_job_without_a_result_yet_asks_nothing_of_it(
    served: Served,
) -> None:
    job_id = submitted(served, sensitivity="restricted")
    asked = len(served.policy.asked)

    assert get(served, f"/v1/jobs/{job_id}").status == 200
    assert len(served.policy.asked) == asked


# Listing


def test_a_caller_lists_only_their_own_jobs_newest_first(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    eris = Served(path, principal=ERIS)
    first = submitted(eris)
    second = submitted(eris)
    submitted(Served(path, principal=DISCORDIA))
    answer = get(eris, "/v1/jobs")
    listed = [JobSummary.model_validate(each) for each in answer.json()]

    assert answer.status == 200
    assert [summary.job_id for summary in listed] == [second, first]
    assert [
        JobSummary.model_validate(each).job_id for each in get(eris, "/v1/jobs?limit=1").json()
    ] == [second]


@pytest.mark.parametrize("limit", ["0", "1001", "many"])
def test_a_listing_asks_for_1_to_1000_jobs(
    served: Served,
    limit: str,
) -> None:
    answer = get(served, f"/v1/jobs?limit={limit}")

    assert (answer.status, answer.json()["error"]) == (
        400,
        f"A listing of jobs asks for 1 to 1000 of them, not {limit}.",
    )


# Cancelling


def test_a_waiting_job_cancelled_by_its_submitter_is_cancelled_and_told_first(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    seen: list[Served] = []
    audit = Watching(lambda: [job.status for job in seen[0].jobs.jobs()])
    served = Served(path, principal=ERIS, audit=audit)
    seen.append(served)
    job_id = submitted(served)
    answer = cancel(served, job_id)
    summary = JobSummary.model_validate(answer.json())

    assert answer.status == 200
    assert (summary.status, summary.cancelled_by) == (ServiceJobStatus.CANCELLED, "Eris")
    assert [(event.kind, event.resource, event.detail) for event in audit.events[1:]] == [
        (AuditEventKind.JOB_CANCELLED, f"job {job_id}", "runs.run")
    ]
    assert audit.seen == [[], [ServiceJobStatus.QUEUED]]


def test_a_running_job_cancelled_is_asked_to_stop(
    served: Served,
) -> None:
    job_id = submitted(served)
    served.jobs.claim("runner-test")
    summary = JobSummary.model_validate(cancel(served, job_id).json())

    assert summary.status is ServiceJobStatus.RUNNING
    assert summary.cancel_requested_at is not None


def test_a_finished_job_cancelled_is_left_as_it_ended(
    served: Served,
) -> None:
    job_id = submitted(served)
    succeeded(served, job_id)

    assert JobSummary.model_validate(cancel(served, job_id).json()).status is (
        ServiceJobStatus.SUCCEEDED
    )


def test_another_callers_job_is_cancelled_by_who_may_do_what_it_does(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    job_id = submitted(Served(path, principal=ERIS))
    refused = Served(path, principal=DISCORDIA, policy=Refusing(Action.RUN_WORKFLOW))
    answer = cancel(refused, job_id)

    left = refused.jobs.get(job_id)

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")
    assert left is not None and left.status is ServiceJobStatus.QUEUED

    allowed = Served(path, principal=DISCORDIA)
    summary = JobSummary.model_validate(cancel(allowed, job_id).json())

    assert (summary.status, summary.cancelled_by) == (ServiceJobStatus.CANCELLED, "Discordia")
    assert allowed.policy.asked == [("Discordia", Action.RUN_WORKFLOW, f"job {job_id}")]


def test_a_job_the_audit_cannot_be_told_is_cancelled_is_not(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    job_id = submitted(Served(path, principal=ERIS))
    answer = cancel(Served(path, principal=ERIS, audit=Broken()), job_id)
    still = Served(path, principal=ERIS).jobs.get(job_id)

    assert (answer.status, answer.json()["code"]) == (503, AUDIT_UNAVAILABLE_CODE)
    assert still is not None and still.status is ServiceJobStatus.QUEUED


# What a job's label is


def a_job(
    call: str,
    **arguments: object,
) -> ServiceJob:
    return ServiceJob(
        job_id=MISSING,
        call=call,
        principal="Eris",
        arguments=json.dumps(arguments),
        status=ServiceJobStatus.SUCCEEDED,
        submitted_at=datetime(2026, 11, 23, tzinfo=UTC),
    )


def test_a_job_is_labelled_by_its_input_or_by_what_it_names(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    served = Served(path, principal=ERIS)
    hidden = benchmark_with_a_case(served, Sensitivity.RESTRICTED)
    shown = benchmark_with_a_case(served, None)
    instance = CallerInstances(open_repositories(path)).instance("Eris")

    assert restricted(instance, a_job("runs.run", sensitivity="restricted"))
    assert not restricted(instance, a_job("runs.invoke", sensitivity="internal"))
    assert not restricted(instance, a_job("runs.try_step"))
    assert restricted(instance, a_job("benchmarks.run", benchmark_id=hidden))
    assert not restricted(instance, a_job("optimization.optimize", benchmark_id=shown))
    assert not restricted(instance, a_job("runs.resume", run_id=str(MISSING)))
    assert not restricted(instance, a_job("invocations.resume", invocation_id=str(MISSING)))

    with pytest.raises(LookupError, match="does not run as a job"):
        restricted(instance, a_job("workflows.get"))
