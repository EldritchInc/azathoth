"""What a remote serving the service API says of itself, and of what a caller may do (ADR 0127).

`GET /v1/service` answers a `ServiceDescription`: the Azathoth serving it,
the stability of the service API, the remote protocol, and the edition the
remote's policy names, with its detail. A remote that answers 404 there
serves only the protocol.

`GET /v1/permissions` answers, for the caller, every action with whether
the policy allows it and, when it does not, why. `POST /v1/permissions`
asks the same about each resource a `PermissionsRequest` names. It is
advice for a client deciding what to show; every route still asks the
policy itself.

A refusal from a service route is `{"error": "<MESSAGE>", "code": "<CODE>"}`.
An `ApiError`'s code is its own, and its status is the one `API_ERROR_STATUSES`
gives its kind; a refusal the remote makes itself, before any call, has the
code `REFUSAL_CODES` gives its status.

This module needs no web framework, so a client may read these shapes too.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from azathoth import __version__
from azathoth.api.errors import (
    ApiError,
    CandidateUnavailableError,
    ConflictError,
    ContentUnavailableError,
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
    InvalidArgumentError,
    InvalidDocumentError,
    McpUnavailableError,
    NotFoundError,
    PermissionDeniedError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    RemoteProtocolError,
    RemoteRefusedError,
    RemoteUnreachableError,
    RunCancelledError,
    RunNotStartedError,
    WorkflowResultMissingError,
)
from azathoth.api.models import API_STABILITY, ApiStability
from azathoth.remote.jobs import RUNNER_ALIVE_SECONDS, ServiceJobRepository, ServiceJobSummary
from azathoth.remote.protocol import PROTOCOL_VERSION
from azathoth.remote.seams import Action, Policy, Principal, Seams

SERVICE_ROUTE: Final = "/v1/service"
"""Where a remote describes the service API it serves."""

PERMISSIONS_ROUTE: Final = "/v1/permissions"
"""Where a remote says what a caller may do."""

MAX_PERMISSION_RESOURCES: Final = 100
"""How many resources one `POST /v1/permissions` may ask about."""

API_ERROR_STATUSES: Final[Mapping[type[ApiError], HTTPStatus]] = {
    InvalidArgumentError: HTTPStatus.BAD_REQUEST,
    InvalidDocumentError: HTTPStatus.UNPROCESSABLE_ENTITY,
    WorkflowResultMissingError: HTTPStatus.UNPROCESSABLE_ENTITY,
    RunNotStartedError: HTTPStatus.UNPROCESSABLE_ENTITY,
    PermissionDeniedError: HTTPStatus.FORBIDDEN,
    NotFoundError: HTTPStatus.NOT_FOUND,
    ContentUnavailableError: HTTPStatus.NOT_FOUND,
    ConflictError: HTTPStatus.CONFLICT,
    CandidateUnavailableError: HTTPStatus.CONFLICT,
    RunCancelledError: HTTPStatus.CONFLICT,
    ProviderUnavailableError: HTTPStatus.BAD_GATEWAY,
    McpUnavailableError: HTTPStatus.BAD_GATEWAY,
    RemoteUnreachableError: HTTPStatus.BAD_GATEWAY,
    RemoteProtocolError: HTTPStatus.BAD_GATEWAY,
    RemoteRefusedError: HTTPStatus.BAD_GATEWAY,
    ProviderConfigurationError: HTTPStatus.SERVICE_UNAVAILABLE,
    InstanceNotFoundError: HTTPStatus.SERVICE_UNAVAILABLE,
    InstanceUnavailableError: HTTPStatus.SERVICE_UNAVAILABLE,
    InstanceSchemaError: HTTPStatus.SERVICE_UNAVAILABLE,
    InstanceClosedError: HTTPStatus.SERVICE_UNAVAILABLE,
}
"""The status a service route answers each kind of `ApiError` with.

A kind not listed takes its nearest listed ancestor's: a `ModelInUseError`
is a `ConflictError`, so 409. What the caller sent is 400 or 422; what the
policy refuses, 403; what is not there, 404; what clashes with what is
there, 409; a provider, an MCP server or another remote that failed, 502;
and the remote's own database or configuration, 503.
"""

REFUSAL_CODES: Final[Mapping[HTTPStatus, str]] = {
    HTTPStatus.BAD_REQUEST: InvalidArgumentError.code,
    HTTPStatus.UNAUTHORIZED: "unauthenticated",
    HTTPStatus.FORBIDDEN: PermissionDeniedError.code,
    HTTPStatus.NOT_FOUND: NotFoundError.code,
    HTTPStatus.CONFLICT: ConflictError.code,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "too_large",
    HTTPStatus.UNPROCESSABLE_ENTITY: InvalidDocumentError.code,
    HTTPStatus.INTERNAL_SERVER_ERROR: ApiError.code,
    HTTPStatus.SERVICE_UNAVAILABLE: "unavailable",
}
"""The code of a refusal the remote makes itself, before any call, by its status."""


def api_error_status(
    error: ApiError,
) -> HTTPStatus:
    """Return the status a service route answers an `ApiError` with.

    An error of a kind neither listed nor descended from a listed one is the
    remote's own failure, 500.
    """

    for kind in type(error).__mro__:
        if kind in API_ERROR_STATUSES:
            return API_ERROR_STATUSES[kind]

    return HTTPStatus.INTERNAL_SERVER_ERROR


def refusal_code(
    status: HTTPStatus,
) -> str:
    """Return the code of a refusal the remote makes itself with a status."""

    return REFUSAL_CODES.get(status, ApiError.code)


class ServiceDescription(BaseModel):
    """What a remote says of the service API it serves, at `GET /v1/service`."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    azathoth_version: str = Field(
        min_length=1,
    )

    api_stability: ApiStability

    protocol: int = Field(
        ge=1,
    )

    edition: str = Field(
        min_length=1,
    )

    edition_detail: str | None = None

    jobs: ServiceJobSummary | None = Field(
        default=None,
        description=(
            "How the remote's jobs stand: how many wait and run, and its runners alive; "
            "absent when it runs no jobs (ADR 0138)."
        ),
    )


class ActionPermission(BaseModel):
    """Whether a caller may take one action, and why not when they may not."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    action: Action

    allowed: bool

    reason: str | None = None


class PermissionsResponse(BaseModel):
    """Every action, and whether the caller may take it, at `GET /v1/permissions`."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    principal: str = Field(
        min_length=1,
    )

    actions: tuple[ActionPermission, ...]


class PermissionsRequest(BaseModel):
    """The resources a `POST /v1/permissions` asks about, as the policy names them."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    resources: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_PERMISSION_RESOURCES,
    )


class ResourcePermissions(BaseModel):
    """Every action, and whether the caller may take it, on one resource."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    resource: str

    actions: tuple[ActionPermission, ...]


class ResourcePermissionsResponse(BaseModel):
    """What a caller may do to each resource a `POST /v1/permissions` asked about."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    principal: str = Field(
        min_length=1,
    )

    resources: tuple[ResourcePermissions, ...]


def service_description(
    seams: Seams,
    jobs: ServiceJobRepository | None = None,
    *,
    now: datetime | None = None,
) -> ServiceDescription:
    """Return what a remote served by these seams says of its service API.

    With `jobs`, it says how they stand, counting as alive the runners
    that beat within `RUNNER_ALIVE_SECONDS` of `now`.

    Raises:
        RemotePluginError: The policy's edition detail is not one it may give.
    """

    moment = datetime.now(UTC) if now is None else now
    summary = (
        None if jobs is None else jobs.summary(moment - timedelta(seconds=RUNNER_ALIVE_SECONDS))
    )

    return ServiceDescription(
        azathoth_version=__version__,
        api_stability=API_STABILITY,
        protocol=PROTOCOL_VERSION,
        edition=seams.policy.edition,
        edition_detail=seams.edition_detail,
        jobs=summary,
    )


def action_permissions(
    policy: Policy,
    principal: Principal,
    resource: str | None = None,
) -> tuple[ActionPermission, ...]:
    """Return whether the policy allows a principal each action, on one resource or none."""

    permissions = []

    for action in Action:
        decision = policy.decide(principal, action, resource)
        permissions.append(
            ActionPermission(
                action=action,
                allowed=decision.allowed,
                reason=None if decision.allowed else decision.reason,
            )
        )

    return tuple(permissions)


def permissions(
    policy: Policy,
    principal: Principal,
) -> PermissionsResponse:
    """Return what the policy allows a principal to do on the remote as a whole."""

    return PermissionsResponse(
        principal=principal.name,
        actions=action_permissions(policy, principal),
    )


def resource_permissions(
    policy: Policy,
    principal: Principal,
    resources: Sequence[str],
) -> ResourcePermissionsResponse:
    """Return what the policy allows a principal to do to each resource, in the order asked."""

    return ResourcePermissionsResponse(
        principal=principal.name,
        resources=tuple(
            ResourcePermissions(
                resource=resource,
                actions=action_permissions(policy, principal, resource),
            )
            for resource in dict.fromkeys(resources)
        ),
    )


__all__ = [
    "API_ERROR_STATUSES",
    "MAX_PERMISSION_RESOURCES",
    "PERMISSIONS_ROUTE",
    "REFUSAL_CODES",
    "SERVICE_ROUTE",
    "ActionPermission",
    "PermissionsRequest",
    "PermissionsResponse",
    "ResourcePermissions",
    "ResourcePermissionsResponse",
    "ServiceDescription",
    "action_permissions",
    "api_error_status",
    "permissions",
    "refusal_code",
    "resource_permissions",
    "service_description",
]
