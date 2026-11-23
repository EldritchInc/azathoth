"""Tests of the routes that describe a remote's service API and what a caller may do (ADR 0127)."""

from collections.abc import Iterator
from http import HTTPStatus

import pytest

import azathoth.api.errors as api_errors
from azathoth import __version__
from azathoth.api.errors import (
    ApiError,
    InvalidDocumentError,
    ModelInUseError,
    NotFoundError,
    PermissionDeniedError,
    RevisionNotFoundError,
)
from azathoth.remote import (
    Action,
    AuditEvent,
    AuditEventKind,
    Decision,
    OwnerOnlyPolicy,
    Principal,
    Seams,
)
from azathoth.remote.server import PLUGIN_ERROR_CODE, UNKNOWN_TOKEN_MESSAGE, RemoteServer
from azathoth.remote.service import (
    API_ERROR_STATUSES,
    MAX_PERMISSION_RESOURCES,
    REFUSAL_CODES,
    api_error_status,
    refusal_code,
)
from tests.remote.asgi import call
from tests.remote.test_receiving import Bare

OWNER = Principal(name="laptop", owner=True)

GUEST = Principal(name="guest")


class Named:
    """An authenticator that names every caller one principal, or no one."""

    def __init__(
        self,
        principal: Principal | None,
    ) -> None:
        self._principal = principal

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        return self._principal


class ListAudit:
    """An audit that keeps what it is told."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        self.events.append(event)


class Detailed(OwnerOnlyPolicy):
    """The core's policy, naming an edition of its own with a detail."""

    def __init__(
        self,
        detail: object,
    ) -> None:
        self._detail = detail

    @property
    def edition(
        self,
    ) -> str:
        return "team"

    @property
    def edition_detail(
        self,
    ) -> object:
        return self._detail


class ByResource(OwnerOnlyPolicy):
    """A policy that lets anyone read the catalog of one workflow only, noting each question."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, Action, str | None]] = []

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        self.asked.append((principal.name, action, resource))

        if action is Action.READ_CATALOG and resource == "workflow open":
            return Decision(allowed=True)

        return Decision(allowed=False, reason=f"{principal.name} may not {action.description}.")


def app(
    *,
    principal: Principal | None = OWNER,
    policy: OwnerOnlyPolicy | None = None,
    audit: ListAudit | None = None,
) -> object:
    held = Bare()

    return RemoteServer(
        workflows=held.workflows,
        tools=held.tools,
        benchmarks=held.benchmarks,
        content=held.content,
        production_states=held.production_states,
        portfolio=held.portfolio,
        seams=Seams(
            authenticator=Named(principal),
            policy=policy if policy is not None else OwnerOnlyPolicy(),
            audit=audit if audit is not None else ListAudit(),
        ),
        accepts_restricted=False,
        environ={},
    ).app()


# The service description


def test_the_service_says_which_azathoth_serves_it_and_its_edition() -> None:
    answer = call(app(), "GET", "/v1/service")

    assert answer.status == 200
    assert answer.json() == {
        "azathoth_version": __version__,
        "api_stability": "stable",
        "protocol": 1,
        "edition": "community",
        "edition_detail": None,
        "jobs": None,
    }


def test_the_service_shows_the_policys_edition_detail() -> None:
    detailed = Detailed("Licensed to Example Co. until 2027-11-22.")
    answer = call(app(policy=detailed), "GET", "/v1/service")

    assert (answer.json()["edition"], answer.json()["edition_detail"]) == (
        "team",
        "Licensed to Example Co. until 2027-11-22.",
    )


def test_an_edition_detail_a_policy_may_not_give_fails_the_request_saying_so() -> None:
    answer = call(app(policy=Detailed("two\nlines")), "GET", "/v1/service")

    assert answer.status == 500
    assert answer.json()["code"] == PLUGIN_ERROR_CODE == "plugin_error"
    assert "one printable line" in answer.json()["error"]


def test_the_service_asks_the_policy_for_read_capabilities_and_says_why_it_refuses() -> None:
    audit = ListAudit()
    answer = call(app(principal=GUEST, audit=audit), "GET", "/v1/service")

    assert answer.status == 403
    assert answer.json() == {
        "error": "guest may not read capabilities on this remote: only its owner may.",
        "code": "permission_denied",
    }
    assert [(event.kind, event.principal, event.resource) for event in audit.events] == [
        (AuditEventKind.REQUEST_DENIED, "guest", "GET /v1/service")
    ]


def test_a_service_route_without_a_known_token_says_so_with_a_code() -> None:
    answer = call(app(principal=None), "GET", "/v1/service", authorization=None)

    assert answer.status == 401
    assert answer.json() == {"error": UNKNOWN_TOKEN_MESSAGE, "code": "unauthenticated"}


def test_a_protocol_route_still_refuses_with_no_code() -> None:
    answer = call(app(principal=None), "GET", "/v1/capabilities", authorization=None)

    assert answer.status == 401
    assert answer.json() == {"error": UNKNOWN_TOKEN_MESSAGE}


# Permissions


def test_the_owner_is_told_they_may_take_every_action() -> None:
    answer = call(app(), "GET", "/v1/permissions")

    assert answer.status == 200
    assert answer.json()["principal"] == "laptop"
    assert answer.json()["actions"] == [
        {"action": action.value, "allowed": True, "reason": None} for action in Action
    ]


def test_anyone_the_remote_knows_may_ask_and_is_told_why_not() -> None:
    audit = ListAudit()
    answer = call(app(principal=GUEST, audit=audit), "GET", "/v1/permissions")

    assert answer.status == 200
    assert answer.json()["actions"] == [
        {
            "action": action.value,
            "allowed": False,
            "reason": f"guest may not {action.description} on this remote: only its owner may.",
        }
        for action in Action
    ]
    assert audit.events == []


def test_permissions_need_a_caller_the_remote_knows() -> None:
    answer = call(app(principal=None), "GET", "/v1/permissions", authorization=None)

    assert (answer.status, answer.json()["code"]) == (401, "unauthenticated")


def test_permissions_on_resources_are_decided_for_each_once_in_the_order_asked() -> None:
    policy = ByResource()
    answer = call(
        app(principal=GUEST, policy=policy),
        "POST",
        "/v1/permissions",
        body={"resources": ["workflow open", "workflow closed", "workflow open"]},
    )
    (open_, closed) = answer.json()["resources"]

    assert answer.status == 200
    assert (open_["resource"], closed["resource"]) == ("workflow open", "workflow closed")
    assert [entry["action"] for entry in open_["actions"] if entry["allowed"]] == ["read_catalog"]
    assert not any(entry["allowed"] for entry in closed["actions"])
    assert closed["actions"][0]["reason"] == "guest may not read capabilities."
    assert {resource for _, _, resource in policy.asked} == {"workflow open", "workflow closed"}
    assert len(policy.asked) == 2 * len(Action)


@pytest.mark.parametrize(
    "body",
    [
        {"resources": []},
        {"resources": [f"workflow {index}" for index in range(MAX_PERMISSION_RESOURCES + 1)]},
        {"resource": ["workflow open"]},
    ],
    ids=["none", "too-many", "misnamed"],
)
def test_a_permissions_request_that_is_not_one_is_refused_saying_where(
    body: object,
) -> None:
    answer = call(app(), "POST", "/v1/permissions", body=body)

    assert answer.status == 400
    assert answer.json()["code"] == "invalid_argument"
    assert answer.json()["error"].startswith("This request is not a PermissionsRequest")


def test_a_permissions_request_that_is_not_json_is_refused() -> None:
    answer = call(app(), "POST", "/v1/permissions", raw=b"resources=workflow")

    assert (answer.status, answer.json()["code"]) == (400, "invalid_argument")


def test_at_most_a_hundred_resources_are_asked_about_at_once() -> None:
    assert MAX_PERMISSION_RESOURCES == 100


# Statuses and codes


def api_error_kinds() -> Iterator[type[ApiError]]:
    """Return every kind of `ApiError` the service API defines."""

    pending: list[type[ApiError]] = [ApiError]

    while pending:
        kind = pending.pop()
        yield kind
        pending.extend(kind.__subclasses__())


def test_every_kind_of_api_error_has_a_status_of_its_own_or_its_kinds() -> None:
    unmapped = [
        kind.__name__
        for kind in api_error_kinds()
        if kind is not ApiError
        and not any(ancestor in API_ERROR_STATUSES for ancestor in kind.__mro__)
    ]

    assert unmapped == []


def test_every_kind_of_api_error_the_service_api_defines_is_seen() -> None:
    defined = {
        value
        for value in vars(api_errors).values()
        if isinstance(value, type) and issubclass(value, ApiError)
    }

    assert defined <= set(api_error_kinds())


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PermissionDeniedError("guest may not."), HTTPStatus.FORBIDDEN),
        (NotFoundError("No workflow."), HTTPStatus.NOT_FOUND),
        (RevisionNotFoundError("No revision."), HTTPStatus.NOT_FOUND),
        (InvalidDocumentError("Not a workflow."), HTTPStatus.UNPROCESSABLE_ENTITY),
        (ApiError("Something else."), HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_an_api_error_is_answered_with_its_kinds_status(
    error: ApiError,
    status: HTTPStatus,
) -> None:
    assert api_error_status(error) == status


def test_a_kind_not_listed_takes_its_nearest_listed_kinds_status() -> None:
    assert ModelInUseError not in API_ERROR_STATUSES
    in_use = ModelInUseError("The model is in use.", dependents=())

    assert api_error_status(in_use) == HTTPStatus.CONFLICT


def test_a_refusal_the_remote_makes_itself_has_the_code_of_its_status() -> None:
    assert refusal_code(HTTPStatus.UNAUTHORIZED) == "unauthenticated"
    assert refusal_code(HTTPStatus.FORBIDDEN) == PermissionDeniedError.code == "permission_denied"
    assert refusal_code(HTTPStatus.BAD_REQUEST) == "invalid_argument"
    assert refusal_code(HTTPStatus.REQUEST_ENTITY_TOO_LARGE) == "too_large"
    assert refusal_code(HTTPStatus.IM_A_TEAPOT) == "error"
    assert set(REFUSAL_CODES) >= {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    }
