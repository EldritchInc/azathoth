"""Tests that a refusal of the service API travels back as the error it was (ADR 0137)."""

from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.errors import (
    CANCELLED_MESSAGE,
    CLOSED_MESSAGE,
    ApiError,
    ModelInUseError,
    NotFoundError,
    RemoteRefusedError,
    RemoteUnavailableError,
    RevisionNotFoundError,
)
from azathoth.api.models import ProductionDependent, ProductionStepUsage
from azathoth.remote.calling import CallArgumentsError
from azathoth.remote.refusals import (
    REFUSED_KINDS,
    Refusal,
    api_error,
    refusal,
    refusal_body,
)

WORKFLOW_ID = UUID("c1100000-0000-4000-8000-000000000001")

STEP_ID = UUID("c1100000-0000-4000-8000-000000000002")

FIXED_MESSAGES = {
    "run_cancelled": CANCELLED_MESSAGE,
    "instance_closed": CLOSED_MESSAGE,
}
"""The kinds that always say the same, whatever a remote sent."""


def public_kinds() -> dict[str, type[ApiError]]:
    """Return every kind of error the service API exports but `ApiError`, by its code."""

    return {
        kind.code: kind
        for name in api.__all__
        if isinstance(kind := getattr(api, name), type)
        and issubclass(kind, ApiError)
        and kind is not ApiError
    }


def travelled(
    error: ApiError,
) -> ApiError:
    """Return an error as a client reads it back from the body a remote refused with."""

    body = refusal_body(error)

    return api_error(409, Refusal.model_validate(body))


# Which kinds travel


def test_every_kind_the_service_api_exports_is_one_a_client_rebuilds() -> None:
    assert dict(REFUSED_KINDS) == public_kinds()
    assert "error" not in REFUSED_KINDS


@pytest.mark.parametrize("code", sorted(public_kinds()))
def test_every_kind_is_rebuilt_as_itself_with_the_remotes_message(
    code: str,
) -> None:
    rebuilt = api_error(409, Refusal(error="As the remote said.", code=code))

    assert type(rebuilt) is REFUSED_KINDS[code]
    assert rebuilt.code == code
    assert str(rebuilt) == FIXED_MESSAGES.get(code, "As the remote said.")


# What a refusal says


def test_a_refusal_names_its_kind_and_each_it_descends_from_nearest_first() -> None:
    assert refusal(RevisionNotFoundError("Workflow X has no revision 3.")) == Refusal(
        error="Workflow X has no revision 3.",
        code="revision_not_found",
        kinds=("revision_not_found", "not_found", "error"),
    )


def test_a_kind_sharing_its_parents_code_names_it_once() -> None:
    assert refusal(CallArgumentsError("Not these.")).kinds == ("invalid_argument", "error")


def test_a_refusal_writes_no_dependents_unless_it_has_them() -> None:
    assert refusal_body(NotFoundError("Gone.")) == {
        "error": "Gone.",
        "code": "not_found",
        "kinds": ["not_found", "error"],
    }


def test_a_models_dependents_travel_with_it() -> None:
    dependents = (
        ProductionDependent(
            workflow_id=WORKFLOW_ID,
            workflow_name="charts",
            steps=(ProductionStepUsage(step_id=STEP_ID, role="primary"),),
        ),
    )
    error = ModelInUseError("Model 'x' is used by active production.", dependents=dependents)
    rebuilt = travelled(error)

    assert isinstance(rebuilt, ModelInUseError)
    assert rebuilt.dependents == dependents
    assert str(rebuilt) == str(error)


@pytest.mark.parametrize(
    "error",
    [
        api.PermissionDeniedError("guest may not edit benchmark on this remote."),
        api.RevisionNotFoundError("Workflow X has no revision 3."),
        api.InvalidDocumentError("Workflow document must declare a result."),
        api.RunCancelledError(),
        api.InstanceClosedError(),
        api.RemoteDivergedError("Workflow X diverged; pull first."),
    ],
    ids=lambda error: type(error).__name__,
)
def test_an_error_travels_back_as_its_own_kind_with_its_message(
    error: ApiError,
) -> None:
    rebuilt = travelled(error)

    assert type(rebuilt) is type(error)
    assert str(rebuilt) == str(error)


# Kinds a client does not know


def test_a_kind_a_newer_remote_adds_is_read_as_the_nearest_known() -> None:
    newer = Refusal.model_validate(
        {
            "error": "Workflow X has no draft.",
            "code": "draft_not_found",
            "kinds": ["draft_not_found", "not_found", "error"],
            "added_by_a_newer_remote": True,
        }
    )
    rebuilt = api_error(404, newer)

    assert type(rebuilt) is NotFoundError
    assert str(rebuilt) == "Workflow X has no draft."


def test_a_refusal_the_remote_makes_itself_is_read_by_its_code() -> None:
    rebuilt = api_error(403, Refusal(error="guest may not.", code="permission_denied"))

    assert type(rebuilt) is api.PermissionDeniedError


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthenticated"),
        (501, "job"),
        (500, "plugin_error"),
        (500, "error"),
        (413, "too_large"),
    ],
)
def test_a_refusal_of_no_known_kind_is_the_remotes_refusal_with_its_status_and_code(
    status: int,
    code: str,
) -> None:
    rebuilt = api_error(status, Refusal(error="As the remote said.", code=code))

    assert type(rebuilt) is RemoteRefusedError
    assert isinstance(rebuilt, RemoteRefusedError)
    assert (rebuilt.status, rebuilt.refusal, str(rebuilt)) == (status, code, "As the remote said.")


@pytest.mark.parametrize("code", ["audit_unavailable", "unavailable"])
def test_a_503_of_no_known_kind_is_a_remote_that_may_answer_later(
    code: str,
) -> None:
    rebuilt = api_error(503, Refusal(error="Its audit is down.", code=code))

    assert type(rebuilt) is RemoteUnavailableError
    assert isinstance(rebuilt, RemoteRefusedError)
    assert (rebuilt.status, rebuilt.refusal) == (503, code)
    assert rebuilt.code == "remote_unavailable"


def test_a_remote_refused_error_raised_locally_carries_no_status() -> None:
    raised = RemoteRefusedError("This push carries restricted data.")

    assert (raised.status, raised.refusal) == (None, None)
